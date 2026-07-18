"""Deterministic-first, LLM/embedding-assisted routing for management agents."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field

from app.config.settings import settings
from app.core.logger import get_logger
from app.embeddings import DashScopeEmbeddingClient
from app.vectorstore import ChromaStore

logger = get_logger(__name__)

AGENT_NAMES = {"detection", "dataset", "training", "catalog", "knowledge"}

ROUTE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "detection": (
        "检测", "识别", "图片", "视频", "置信度", "漏检", "误检", "推理", "盘点",
    ),
    "dataset": (
        "数据集", "版本", "草稿", "派生", "冻结", "归档", "样品", "样本", "标注", "检测框",
    ),
    "training": (
        "训练", "epoch", "loss", "map", "precision", "recall", "模型", "评估", "日志",
    ),
    "catalog": (
        "价格", "价目", "单价", "商品目录", "sku", "条码", "未定价", "改价",
    ),
}

ROUTE_EXAMPLES: dict[str, tuple[str, ...]] = {
    "detection": (
        "检测这张商品图片", "用当前模型测试一段视频", "为什么这张图出现漏检", "调高置信度再识别",
    ),
    "dataset": (
        "查看当前数据集版本", "从冻结版本派生一个草稿", "给数据集添加新商品样品", "归档旧数据集版本",
    ),
    "training": (
        "查看最近训练任务进度", "分析模型的 mAP 和 Recall", "查看训练日志", "比较两个训练模型",
    ),
    "catalog": (
        "查看当前价目表", "哪些商品还没有价格", "把这个商品价格改为十元", "按条码查询商品单价",
    ),
    "knowledge": (
        "这个平台应该怎么操作", "解释一个系统概念", "查询故障处理手册", "根据知识库回答问题",
    ),
}


@dataclass(frozen=True)
class RouteDecision:
    agents: list[str]
    method: str
    confidence: float
    reason: str
    # "single"：单 Agent；"parallel"：多个 Agent 相互独立，并发执行；
    # "pipeline"：多个 Agent 存在依赖，按顺序执行并把前序结果注入后续输入。
    execution_mode: str = "single"
    # LLM 路由拆分出的各 Agent 子任务；为空时各 Agent 收到原始消息。
    tasks: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_agents_normalized", sorted({a.strip().lower() for a in self.agents if a.strip()})
        )

    @property
    def agent(self) -> str:
        """Primary agent for backward compatibility."""
        return self.agents[0] if self.agents else "knowledge"

    @property
    def is_parallel(self) -> bool:
        return self.execution_mode == "parallel" or (
            self.execution_mode == "single" and len(self._agents_normalized) > 1
        )

    @property
    def is_pipeline(self) -> bool:
        return self.execution_mode == "pipeline"

    @property
    def parallel_key(self) -> str:
        return ",".join(self._agents_normalized)

    def task_for(self, agent: str, fallback: str) -> str:
        """Return the scoped sub-task for an agent, falling back to the raw message."""
        task = self.tasks.get(agent, "").strip()
        return task or fallback

    def event(self) -> dict:
        payload = {
            "type": "routing",
            "agents": self.agents,
            "agent": self.agent,
            "method": self.method,
            "confidence": self.confidence,
            "reason": self.reason,
            "is_parallel": self.is_parallel,
            "execution_mode": self.execution_mode,
        }
        if self.tasks:
            payload["tasks"] = self.tasks
        return payload

    @classmethod
    def single(cls, agent: str, method: str, confidence: float, reason: str) -> "RouteDecision":
        return cls(agents=[agent], method=method, confidence=confidence, reason=reason, execution_mode="single")

    @classmethod
    def parallel(cls, agents: list[str], method: str, confidence: float, reason: str) -> "RouteDecision":
        return cls(agents=agents, method=method, confidence=confidence, reason=reason, execution_mode="parallel")

    @classmethod
    def pipeline(cls, agents: list[str], method: str, confidence: float, reason: str) -> "RouteDecision":
        return cls(agents=agents, method=method, confidence=confidence, reason=reason, execution_mode="pipeline")

    @classmethod
    def multi(
        cls,
        agents: list[str],
        mode: str,
        tasks: dict[str, str],
        method: str,
        confidence: float,
        reason: str,
    ) -> "RouteDecision":
        return cls(
            agents=agents,
            method=method,
            confidence=confidence,
            reason=reason,
            execution_mode=mode,
            tasks=tasks,
        )


LLM_ROUTER_PROMPT = """你是 VisionPay 多智能体系统的路由器。根据用户消息、是否带有图片/视频附件，以及对话上下文，决定由哪些领域 Agent 处理，并把用户意图拆分成每个 Agent 的独立子任务。

可选 Agent 及职责：
- detection：对聊天附件执行商品检测（识别商品、数量、置信度、计价清单）；也负责检测任务的统计与历史查询（如"今天检测了多少任务""识别了多少东西""查询检测情况"），这类统计问题即使没有附件也应交给 detection，而不是 knowledge。
- dataset：数据集版本与样品工作流（查询/创建/派生/冻结/归档/删除版本，添加商品样品与标注）。
- training：训练任务、进度、指标与默认模型管理。
- catalog：商品目录、条码、价格、缺价状态查询与改价。
- knowledge：平台能力与通用概念解释、操作知识、故障案例；也接收一切无法归入其他领域的意图。

只输出一行严格 JSON，不要输出任何其他文字：
{"agents": ["agent名"], "mode": "single|parallel|pipeline", "tasks": {"agent名": "子任务"}, "reason": "一句话理由"}

规则：
1. agents 只能来自上述 5 个；只有一个 Agent 时 mode 必须是 single。
2. 多个 Agent 相互独立（例如"检测图片并解释什么是 mAP"）→ parallel；后一个 Agent 依赖前一个的输出（例如"识别图中商品并查询它们的价格"，查价依赖检测结果）→ pipeline，agents 按执行顺序排列。
3. tasks 必须覆盖 agents 中的每个 Agent；子任务用简洁、自包含的中文，只保留该 Agent 职责范围内的意图，不要包含其他 Agent 的内容。
4. 用户消息中的每一个意图都必须分配给某个 Agent，不得遗漏；无法归类的意图交给 knowledge。
5. 有附件且用户表达检测、识别、盘点或结算意图时，agents 必须包含 detection。
6. 用户明确要求切换、转交或点名某个 Agent（如"切换 detection""让 Catalog 来处理"）时，直接路由到该 Agent，该指令优先于上下文延续。
7. 如果用户意图是在延续上一轮的领域工作流，优先保持该 Agent。
8. 拿不准时只返回 ["knowledge"]，mode 为 single。"""

LLM_ROUTER_TIMEOUT_SECONDS = 20


class AgentRouter:
    COLLECTION = "visionpay_agent_routes"

    @staticmethod
    def _keyword_route(message: str) -> RouteDecision | None:
        lowered = message.lower()
        scores = {
            agent: sum(1 for keyword in keywords if keyword.lower() in lowered)
            for agent, keywords in ROUTE_KEYWORDS.items()
        }
        best_score = max(scores.values(), default=0)
        winners = [agent for agent, score in scores.items() if score == best_score and score > 0]
        if len(winners) != 1:
            return None
        winner = winners[0]
        confidence = min(0.98, 0.72 + best_score * 0.08)
        return RouteDecision.single(winner, "keyword", confidence, f"命中 {best_score} 个领域关键词")

    def _ensure_examples(
        self, store: ChromaStore, embedding: DashScopeEmbeddingClient
    ) -> None:
        expected = sum(len(items) for items in ROUTE_EXAMPLES.values())
        if store.count >= expected:
            return
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []
        for agent, examples in ROUTE_EXAMPLES.items():
            for index, example in enumerate(examples):
                ids.append(f"route-{agent}-{index}")
                documents.append(example)
                metadatas.append({"agent": agent, "kind": "route_example"})
        store.upsert(
            ids=ids,
            documents=documents,
            embeddings=embedding.embed_documents(documents),
            metadatas=metadatas,
        )

    def _embedding_route(self, message: str) -> RouteDecision | None:
        try:
            embedding = DashScopeEmbeddingClient()
            store = ChromaStore(self.COLLECTION)
            self._ensure_examples(store, embedding)
            results = store.query(embedding=embedding.embed_query(message), top_k=3)
        except Exception as exc:  # noqa: BLE001 - routing must degrade safely
            logger.warning("向量路由不可用，降级到默认路由: %s", exc)
            return None
        votes: dict[str, float] = {}
        for item in results:
            agent = str(item["metadata"].get("agent") or "")
            if agent in AGENT_NAMES:
                votes[agent] = votes.get(agent, 0.0) + max(0.0, item["similarity"])
        if not votes:
            return None
        agent = max(votes, key=votes.get)
        best = next(
            (item for item in results if item["metadata"].get("agent") == agent),
            None,
        )
        similarity = float(best["similarity"] if best else 0.0)
        if similarity < float(settings.ROUTER_MIN_SIMILARITY):
            return None
        return RouteDecision.single(agent, "embedding", similarity, "DashScope + Chroma 模糊路由")

    @staticmethod
    def _explicit_detection_intent(message: str) -> bool:
        lowered = message.lower()
        return any(
            phrase in lowered
            for phrase in (
                "检测这张", "检测附件", "识别这张", "识别附件", "商品检测",
                "检测图片", "识别图片", "检测图像", "识别图像", "检测照片", "识别照片",
                "检测图中", "识别图中", "检测下图", "识别下图",
                "批量检测", "批量识别", "检测下面", "识别下面", "开始检测", "开始识别",
                "用模型检测", "推理这张",
            )
        )

    @staticmethod
    def _explicit_management_intent(message: str) -> RouteDecision | None:
        lowered = message.lower()
        price_terms = ("价格", "价目", "单价", "定价")
        price_actions = ("改", "修改", "更新", "设置", "清除", "取消", "查询", "查看", "多少", "未定价")
        if any(term in lowered for term in price_terms) and any(
            action in lowered for action in price_actions
        ):
            return RouteDecision.single("catalog", "explicit_intent", 0.99, "明确的价目表操作")

        if "训练" in lowered and any(
            action in lowered
            for action in ("启动", "开始", "停止", "取消", "查看", "查询", "进度", "指标", "日志")
        ):
            return RouteDecision.single("training", "explicit_intent", 0.99, "明确的训练操作")
        if any(term in lowered for term in ("默认模型", "切换模型", "发布模型")):
            return RouteDecision.single("training", "explicit_intent", 0.99, "明确的模型管理操作")
        return None

    @staticmethod
    def _strong_intent_decision(
        decision: RouteDecision, semantic: RouteDecision | None
    ) -> RouteDecision:
        """Keep deterministic safety/workflow decisions ahead of semantic routing."""
        if semantic and semantic.agent != decision.agent:
            logger.info(
                "强意图覆盖向量路由: final=%s(%s), semantic=%s(%.3f)",
                decision.agent,
                decision.method,
                semantic.agent,
                semantic.confidence,
            )
        return decision

    @staticmethod
    def _dataset_edit_intent(
        message: str, preferred_agent: str | None
    ) -> RouteDecision | None:
        """Keep sample authoring in Dataset even when users call it a training set."""
        lowered = message.lower()
        add_actions = ("添加", "新增", "增加", "加入", "录入", "导入")
        sample_targets = (
            "商品", "样品", "样本", "训练图", "训练集", "训练样品", "标注",
        )
        is_sample_edit = any(action in lowered for action in add_actions) and any(
            target in lowered for target in sample_targets
        )
        if not is_sample_edit:
            return None
        # 商品、样品和标注只能在数据集版本中编辑。这里不依赖“版本”字样，
        # 因为用户常直接引用版本名（例如 mutation-smoke-v2），而错误的上一轮
        # Agent 也不能把该领域意图污染成 Training 会话。
        return RouteDecision.single("dataset", "explicit_intent", 0.99, "明确的数据集样品编辑操作")

    @staticmethod
    def _dataset_lifecycle_intent(message: str) -> RouteDecision | None:
        """Route dataset creation/version lifecycle operations deterministically."""
        lowered = message.lower()
        dataset_terms = ("数据集", "dataset", "数据版本", "数据草稿", "基线版本")
        lifecycle_actions = (
            "创建",
            "新建",
            "建立",
            "导入",
            "派生",
            "冻结",
            "归档",
            "删除",
            "校验",
            "查看",
            "查询",
            "列出",
            "详情",
        )
        if any(term in lowered for term in dataset_terms) and any(
            action in lowered for action in lifecycle_actions
        ):
            return RouteDecision.single(
                "dataset", "explicit_intent", 0.99, "明确的数据集生命周期操作"
            )
        return None

    @staticmethod
    def _general_knowledge_intent(message: str) -> RouteDecision | None:
        """Keep conceptual questions out of a stale domain-Agent conversation."""
        normalized = message.strip().lower()
        if not normalized:
            return None

        identity_cues = (
            "你是做什么",
            "你是什么工作",
            "你是做什么工作",
            "你是干什么",
            "你负责什么",
            "你的职责",
            "你能做什么",
            "平台能做什么",
            "系统能做什么",
        )
        if any(cue in normalized for cue in identity_cues):
            return RouteDecision.single(
                "knowledge", "general_knowledge", 0.98, "通用的平台或 Agent 能力说明"
            )

        agent_scope_terms = (
            "detection agent",
            "dataset agent",
            "training agent",
            "catalog agent",
            "knowledge agent",
            "检测智能体",
            "数据集智能体",
            "训练智能体",
            "价目表智能体",
            "知识智能体",
        )
        scope_cues = ("职责", "负责", "功能", "做什么", "干什么", "能做什么", "工作")
        if any(term in normalized for term in agent_scope_terms) and any(
            cue in normalized for cue in scope_cues
        ):
            return RouteDecision.single(
                "knowledge", "general_knowledge", 0.98, "领域 Agent 职责说明"
            )

        explanation_cues = (
            "什么是",
            "什么叫",
            "是什么意思",
            "解释一下",
            "解释",
            "讲讲",
            "定义",
            "原理",
        )
        runtime_cues = (
            "当前",
            "这次",
            "本次",
            "最近",
            "具体任务",
            "训练任务",
            "日志",
            "进度",
            "曲线",
            "数值",
            "指标",
        )
        if any(cue in normalized for cue in explanation_cues) and not any(
            cue in normalized for cue in runtime_cues
        ):
            return RouteDecision.single(
                "knowledge", "general_knowledge", 0.97, "通用概念解释"
            )
        return None

    def _parallel_intent(
        self,
        message: str,
        has_attachments: bool,
        explicit_detection: bool,
        explicit_management: RouteDecision | None,
        dataset_edit: RouteDecision | None,
        dataset_lifecycle: RouteDecision | None,
        general_knowledge: RouteDecision | None,
    ) -> RouteDecision | None:
        """Detect whether detection + another management agent should run in parallel or pipeline.

        - **parallel**：两个任务相互独立（如“检测图片并查看数据集版本”）。
        - **pipeline**：后一个任务依赖前一个的输出（如“识别图片里的商品并查询它们的价格”）。
        """
        if not has_attachments or not explicit_detection:
            return None

        secondary = None
        if explicit_management:
            secondary = explicit_management
        elif dataset_edit:
            secondary = dataset_edit
        elif dataset_lifecycle:
            secondary = dataset_lifecycle
        elif general_knowledge:
            secondary = general_knowledge

        if not secondary or secondary.agent == "detection":
            return None

        # 依赖检测输出的关键词：这些/它们/他们/识别结果/检测到的商品等。
        dependency_cues = (
            "它们", "他们", "这些", "这些商品", "那些商品", "识别结果", "检测结果",
            "检测到的商品", "识别到的商品", "图中商品", "图片里的商品", "图片中的商品",
        )
        is_dependent = any(cue in message.lower() for cue in dependency_cues)

        if is_dependent and secondary.agent == "catalog":
            return RouteDecision.pipeline(
                agents=["detection", secondary.agent],
                method="pipeline",
                confidence=round(min(0.99, secondary.confidence), 3),
                reason=f"先检测附件商品，再由 {secondary.agent} 查询价格",
            )

        return RouteDecision.parallel(
            agents=["detection", secondary.agent],
            method="parallel",
            confidence=round(min(0.99, secondary.confidence), 3),
            reason=f"附件检测与 {secondary.reason} 可并行执行",
        )

    def deterministic_safety(
        self,
        message: str,
        *,
        has_attachments: bool = False,
        preferred_agent: str | None = None,
        active_workflow_agent: str | None = None,
    ) -> RouteDecision | None:
        """Return a decision for strong, auditable business intents, else ``None``.

        Write operations and dataset lifecycle flows must stay deterministic so they
        remain auditable; everything else can be delegated to the LLM router.
        """
        preferred = preferred_agent if preferred_agent in AGENT_NAMES else None
        explicit_detection = self._explicit_detection_intent(message)
        # 附件 + 明确检测意图意味着消息很可能是多意图组合（如“检测商品并查看数据集”），
        # 此时任何单领域确定性规则都会吞掉其余意图，统一交给 LLM 路由器拆分。
        defer_combo = has_attachments and explicit_detection

        explicit_management = self._explicit_management_intent(message)
        if explicit_management and not defer_combo:
            return explicit_management

        dataset_edit = self._dataset_edit_intent(message, preferred)
        if dataset_edit and not defer_combo:
            return dataset_edit

        dataset_lifecycle = self._dataset_lifecycle_intent(message)
        if dataset_lifecycle and not defer_combo:
            return dataset_lifecycle

        if preferred == "dataset" and any(
            cue in message.lower()
            for cue in ("商品名", "商品名称", "类别名", "类别英文名", "class_name", "train_new", "train_existing")
        ):
            return RouteDecision.single("dataset", "conversation_context", 0.96, "继续补充数据集样品字段")

        return None

    async def route_llm(
        self,
        message: str,
        *,
        has_attachments: bool = False,
        preferred_agent: str | None = None,
        active_workflow_agent: str | None = None,
    ) -> RouteDecision | None:
        """Use an LLM to pick agents, execution mode and per-agent sub-tasks.

        Returns ``None`` when the LLM is unavailable, times out, or produces an
        invalid payload so callers can degrade to the deterministic/embedding chain.
        """
        if not settings.DEEPSEEK_API_KEY or settings.DEEPSEEK_API_KEY.startswith("sk-your-"):
            return None

        context_hints = []
        if has_attachments:
            context_hints.append("本轮用户带有图片/视频附件。")
        if active_workflow_agent in AGENT_NAMES:
            context_hints.append(f"上一轮未完成的领域工作流属于 {active_workflow_agent}。")
        elif preferred_agent in AGENT_NAMES:
            context_hints.append(f"上一轮对话由 {preferred_agent} 处理。")
        hints = "\n".join(context_hints) or "无额外上下文。"

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model=settings.DEEPSEEK_MODEL,
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
                temperature=0,
                streaming=False,
            )
            response = await asyncio.wait_for(
                llm.ainvoke(
                    [
                        SystemMessage(content=LLM_ROUTER_PROMPT),
                        HumanMessage(content=f"上下文：{hints}\n用户消息：{message}"),
                    ]
                ),
                timeout=LLM_ROUTER_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - LLM routing must degrade safely
            logger.warning("LLM 路由不可用，降级到确定性/向量路由: %s", exc)
            return None

        return self._parse_llm_decision(response.content, message)

    @staticmethod
    def _parse_llm_decision(content: str, message: str) -> RouteDecision | None:
        """Validate the LLM router JSON payload into a ``RouteDecision``."""
        text = (content or "").strip()
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()
        try:
            payload = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            logger.warning("LLM 路由返回非 JSON 内容: %s", text[:200])
            return None
        if not isinstance(payload, dict):
            return None

        agents = [
            str(a).strip().lower()
            for a in (payload.get("agents") or [])
            if str(a).strip().lower() in AGENT_NAMES
        ]
        agents = list(dict.fromkeys(agents))
        if not agents:
            return None

        mode = str(payload.get("mode") or "single").strip().lower()
        if mode not in ("single", "parallel", "pipeline"):
            mode = "single"
        if len(agents) == 1:
            mode = "single"
        elif mode == "single":
            mode = "parallel"

        raw_tasks = payload.get("tasks") if isinstance(payload.get("tasks"), dict) else {}
        tasks = {agent: str(raw_tasks.get(agent) or "").strip() for agent in agents}
        # 覆盖兜底：缺失的子任务用原始消息补齐，保证每个 Agent 都有输入。
        for agent, task in tasks.items():
            if not task:
                tasks[agent] = message

        reason = str(payload.get("reason") or "LLM 语义路由").strip() or "LLM 语义路由"
        return RouteDecision.multi(
            agents=agents,
            mode=mode,
            tasks=tasks,
            method="llm",
            confidence=0.9,
            reason=reason,
        )

    def route(
        self,
        message: str,
        *,
        has_attachments: bool = False,
        preferred_agent: str | None = None,
        active_workflow_agent: str | None = None,
    ) -> RouteDecision:
        preferred = preferred_agent if preferred_agent in AGENT_NAMES else None
        active = active_workflow_agent if active_workflow_agent in AGENT_NAMES else None
        explicit_detection = self._explicit_detection_intent(message)
        # Every message obtains a semantic second opinion. Strong, auditable business
        # intents below still win; otherwise this is the primary routing signal.
        semantic = self._embedding_route(message)

        if str(settings.AGENT_ROUTING_MODE).strip().lower() == "embedding_only":
            if semantic:
                return semantic
            return RouteDecision.single(
                "knowledge",
                "embedding_unavailable",
                0.0,
                "纯向量路由测试中 Embedding 不可用或相似度不足，安全降级到 Knowledge Agent",
            )

        explicit_management = self._explicit_management_intent(message)
        dataset_edit = self._dataset_edit_intent(message, preferred)
        dataset_lifecycle = self._dataset_lifecycle_intent(message)
        general_knowledge = self._general_knowledge_intent(message)

        if has_attachments:
            parallel = self._parallel_intent(
                message,
                has_attachments,
                explicit_detection,
                explicit_management,
                dataset_edit,
                dataset_lifecycle,
                general_knowledge,
            )
            if parallel:
                return self._strong_intent_decision(parallel, semantic)

            if explicit_detection:
                return self._strong_intent_decision(
                    RouteDecision.single("detection", "attachment_intent", 1.0, "用户明确要求检测附件"),
                    semantic,
                )
            if explicit_management:
                return self._strong_intent_decision(explicit_management, semantic)
            if dataset_edit:
                return self._strong_intent_decision(dataset_edit, semantic)
            if dataset_lifecycle:
                return self._strong_intent_decision(dataset_lifecycle, semantic)
            if active:
                return self._strong_intent_decision(
                    RouteDecision.single(active, "active_workflow", 0.99, "附件延续未完成的领域工作流"),
                    semantic,
                )
            # Dataset may legitimately continue an add-samples handoff. Other
            # management Agents cannot consume chat attachment paths, so a stale
            # conversation context must not capture a new image-detection turn.
            if preferred == "dataset":
                return self._strong_intent_decision(
                    RouteDecision.single(preferred, "conversation_context", 0.96, "附件延续上一领域对话"),
                    semantic,
                )
            return self._strong_intent_decision(
                RouteDecision.single("detection", "attachment", 1.0, "本轮包含检测附件"),
                semantic,
            )

        if explicit_detection:
            return self._strong_intent_decision(
                RouteDecision.single("detection", "explicit_intent", 0.99, "明确的商品检测操作"),
                semantic,
            )

        if preferred == "dataset" and any(
            cue in message.lower()
            for cue in ("商品名", "商品名称", "类别名", "类别英文名", "class_name", "train_new", "train_existing")
        ):
            return self._strong_intent_decision(
                RouteDecision.single("dataset", "conversation_context", 0.96, "继续补充数据集样品字段"),
                semantic,
            )

        if explicit_management:
            return self._strong_intent_decision(explicit_management, semantic)

        if dataset_edit:
            return self._strong_intent_decision(dataset_edit, semantic)

        if dataset_lifecycle:
            return self._strong_intent_decision(dataset_lifecycle, semantic)

        if general_knowledge:
            return self._strong_intent_decision(general_knowledge, semantic)

        if active:
            return self._strong_intent_decision(
                RouteDecision.single(active, "active_workflow", 0.94, "继续未完成的领域工作流"),
                semantic,
            )

        if semantic:
            return semantic

        keyword = self._keyword_route(message)
        if keyword:
            return keyword
        if preferred:
            return RouteDecision.single(preferred, "conversation_context", 0.86, "延续上一领域对话")
        return RouteDecision.single("knowledge", "fallback", 0.35, "未识别明确业务域，交由知识 Agent 澄清")
