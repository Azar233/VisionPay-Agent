"""Deterministic retrieval-query rewriting from structured conversation state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


PURPOSE_PHRASES = {
    "dataset.detail": "Dataset 数据集版本详情、状态和适用条件",
    "dataset.add_samples": "Dataset 数据集版本添加商品样品、人工标注和交接流程",
    "dataset.derive": "Dataset 数据集版本派生条件、复制范围和操作流程",
    "dataset.freeze": "Dataset 数据集版本冻结条件、影响范围和操作流程",
    "dataset.archive": "Dataset 数据集版本归档条件、影响范围和操作流程",
    "dataset.delete_product": "Dataset 删除商品样品的影响范围和操作流程",
    "dataset.delete_draft": "Dataset 删除数据集草稿的风险、影响范围和操作流程",
    "training.start": "Training 模型训练启动条件、参数和操作流程",
    "training.stop": "Training 停止训练任务的影响和操作流程",
    "training.status": "Training 训练任务状态、进度和日志说明",
    "training.metrics": "Training 训练指标、loss、Precision、Recall 和 mAP 说明",
    "training.set_default_model": "Training 切换默认模型的条件、影响范围和操作流程",
    "catalog.list_prices": "Catalog 商品价目表、缺失价格和查询流程",
    "catalog.update_price": "Catalog 修改商品价格的影响范围和操作流程",
    "catalog.clear_price": "Catalog 清除商品价格的结算影响和操作流程",
    "detection.parameters": "Detection 商品检测参数、置信度和操作流程",
    "knowledge.remember": "Knowledge 长期记忆保存范围和敏感信息限制",
}

PURPOSE_CUES = (
    ("dataset.freeze", ("冻结",)),
    ("dataset.archive", ("归档",)),
    ("dataset.derive", ("派生", "复制版本")),
    ("dataset.add_samples", ("添加样品", "新增样品", "添加商品", "训练图", "标注")),
    ("dataset.delete_product", ("删除商品", "删除样品")),
    ("dataset.delete_draft", ("删除草稿",)),
    ("training.metrics", ("mAP", "map", "precision", "recall", "loss", "指标")),
    ("training.status", ("训练进度", "训练状态", "训练日志")),
    ("training.start", ("启动训练", "开始训练")),
    ("training.stop", ("停止训练", "取消训练")),
    ("training.set_default_model", ("默认模型", "切换模型")),
    ("catalog.update_price", ("改价", "修改价格", "更新价格")),
    ("catalog.clear_price", ("清除价格", "删除价格")),
    ("catalog.list_prices", ("价目表", "查询价格", "价格列表")),
    ("detection.parameters", ("置信度", "检测参数", "识别参数")),
)

REFERENCE_CUES = (
    "这个",
    "该版本",
    "它",
    "刚才",
    "上面",
    "当前",
    "继续",
    "怎么",
    "如何",
    "哪些影响",
)

ENTITY_LABELS = {
    "dataset_id": "数据集 ID",
    "dataset_version_id": "数据集版本 ID",
    "dataset_version": "数据集版本",
    "version": "版本",
    "product_id": "商品 ID",
    "product_name": "商品",
    "model_version_id": "模型版本 ID",
    "model_name": "模型",
    "task_id": "任务 ID",
    "scene_id": "场景 ID",
}

DOMAIN_CUES = {
    "dataset": ("数据集", "数据版本", "样品", "样本", "标注"),
    "training": ("训练", "模型", "epoch", "loss", "map", "precision", "recall"),
    "catalog": ("价格", "价目表", "商品目录", "条码"),
    "detection": ("检测", "识别", "置信度", "检测框"),
}


@dataclass(frozen=True)
class RewrittenQuery:
    original_query: str
    rewritten_query: str
    domain: str | None
    purpose: str | None
    context_used: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class RetrievalQueryRewriter:
    @staticmethod
    def _infer_purpose(query: str) -> str | None:
        lowered = query.lower()
        for purpose, cues in PURPOSE_CUES:
            if any(cue.lower() in lowered for cue in cues):
                return purpose
        return None

    @staticmethod
    def _domain_for_purpose(purpose: str | None) -> str | None:
        if not purpose:
            return None
        domain = purpose.split(".", 1)[0]
        return domain if domain in {"dataset", "training", "catalog", "detection", "knowledge"} else None

    @staticmethod
    def _infer_domain(query: str) -> str | None:
        lowered = query.lower()
        for domain, cues in DOMAIN_CUES.items():
            if any(cue.lower() in lowered for cue in cues):
                return domain
        return None

    def rewrite(
        self,
        query: str,
        *,
        context_state: dict[str, Any] | None = None,
        domain: str | None = None,
    ) -> RewrittenQuery:
        original = str(query or "").strip()
        state = context_state if isinstance(context_state, dict) else {}
        explicit_purpose = self._infer_purpose(original)
        explicit_domain = self._infer_domain(original)
        workflow = state.get("active_workflow") if isinstance(state.get("active_workflow"), dict) else {}
        state_purpose = str(workflow.get("purpose") or "") or None
        uses_reference = any(cue in original for cue in REFERENCE_CUES)
        is_concept_definition = any(cue in original for cue in ("什么是", "定义", "原理"))
        purpose = explicit_purpose
        if (
            purpose is None
            and explicit_domain is None
            and uses_reference
            and not is_concept_definition
        ):
            purpose = state_purpose

        resolved_domain = (
            domain
            or self._domain_for_purpose(purpose)
            or explicit_domain
            or ""
        ).strip().lower() or None
        if resolved_domain is None and uses_reference:
            candidate = state.get("active_agent")
            if candidate in {"dataset", "training", "catalog", "detection", "knowledge"}:
                resolved_domain = str(candidate)

        context_parts = []
        entities = state.get("entities") if isinstance(state.get("entities"), dict) else {}
        state_domain = workflow.get("agent") or state.get("active_agent")
        purpose_domain = self._domain_for_purpose(explicit_purpose)
        use_state_entities = (
            explicit_purpose is not None and state_domain == purpose_domain
        ) or (
            explicit_purpose is None
            and explicit_domain is None
            and uses_reference
        )
        if use_state_entities:
            for key, label in ENTITY_LABELS.items():
                value = entities.get(key)
                if value not in {None, ""}:
                    context_parts.append(f"{label} {value}")

        canonical = PURPOSE_PHRASES.get(purpose or "")
        if canonical:
            parts = [canonical]
            if context_parts:
                parts.append("当前对象：" + "，".join(context_parts[:4]))
            parts.append("用户问题：" + original)
            rewritten = "；".join(parts)
        elif context_parts:
            rewritten = original + "；当前任务对象：" + "，".join(context_parts[:4])
        else:
            rewritten = original

        return RewrittenQuery(
            original_query=original,
            rewritten_query=rewritten,
            domain=resolved_domain,
            purpose=purpose,
            context_used=rewritten != original,
        )


retrieval_query_rewriter = RetrievalQueryRewriter()
