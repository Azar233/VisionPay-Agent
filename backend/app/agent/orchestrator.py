"""Supervisor that routes a request to one or more scoped domain Agents."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, Callable

from app.agent.agents import CatalogAgent, DatasetAgent, KnowledgeAgent, TrainingAgent
from app.agent.custom_instructions import (
    CUSTOM_INSTRUCTIONS_PROMPT,
    render_custom_instructions,
)
from app.agent.detection_agent import DetectionAgent
from app.agent.prompts import SUPERVISOR_SUMMARY_PROMPT
from app.agent.routing import AgentRouter, RouteDecision
from app.agent.usage import usage_metadata
from app.config.settings import settings
from app.core.logger import get_logger
from app.memory import LongTermMemoryStore
from app.rag.query_rewriter import retrieval_query_rewriter

logger = get_logger(__name__)

# 单个 Agent 在并行/流水线执行中的最大等待时间（秒）。
PARALLEL_AGENT_TIMEOUT_SECONDS = 120

# 执行阶段产生的交互类事件：流水线中出现时中断下游执行；汇总不受其影响，
# 卡片与其余 Agent 的文字回答会同时呈现。
_INTERACTIVE_EVENT_TYPES = {"input_form", "handoff_required", "confirmation_required"}

# 检测结果中携带二进制图片的字段：仅供前端卡片展示，绝不能作为文本喂给 LLM。
_BINARY_RESULT_KEYS = {"annotated_image", "annotated_frame", "annotated_frames"}
# 喂给 LLM 的单个字符串字段的最大长度，超出部分截断。
_MAX_MATERIAL_FIELD_CHARS = 4000

# 多 Agent 协作时注入管理类 Agent 的运行上下文：表单/确认卡会中断整条
# 并行/流水线，协作模式下一律改用文字说明，由 Supervisor 统一向用户解释。
COLLABORATION_CONTEXT = (
    "本次为多 Agent 协作执行：你只负责分配给你的子任务。"
    "禁止调用 request_user_input_form 生成参数表单；缺少参数时直接在回复中用文字说明缺口，"
    "由 Supervisor 汇总时统一向用户解释。上游 Agent 的结果中已经包含的信息（例如检测结果"
    "及其价格清单）直接使用，不要重复调用工具查询。"
)


def sanitize_result_payload(value):
    """Recursively strip binary image fields and cap long strings before LLM use.

    The raw detection result keeps its ``annotated_image`` data URL for the
    frontend card and the database; only the copy sent to the LLM is sanitized.
    """
    if isinstance(value, dict):
        return {
            key: sanitize_result_payload(item)
            for key, item in value.items()
            if key not in _BINARY_RESULT_KEYS
        }
    if isinstance(value, list):
        return [sanitize_result_payload(item) for item in value]
    if isinstance(value, str):
        if value.startswith("data:image"):
            return "[图片数据已省略]"
        if len(value) > _MAX_MATERIAL_FIELD_CHARS:
            return value[:_MAX_MATERIAL_FIELD_CHARS] + "...[截断]"
    return value


class MultiAgentOrchestrator:
    """Route user requests to domain agents and run them in single, parallel or pipeline mode."""

    def __init__(
        self,
        *,
        user_id: int,
        scene_id: int | None,
        session_uuid: str,
        context_state: dict | None = None,
        custom_instructions: str = "",
        detection_agent_factory: Callable = DetectionAgent,
    ) -> None:
        self.user_id = user_id
        self.scene_id = scene_id
        self.session_uuid = session_uuid
        self.context_state = context_state or {}
        self.custom_instructions = str(custom_instructions or "")
        self.detection_agent_factory = detection_agent_factory
        self.router = AgentRouter()

    def route(
        self,
        message: str,
        *,
        has_attachments: bool = False,
        preferred_agent: str | None = None,
        active_workflow_agent: str | None = None,
    ) -> RouteDecision:
        return self.router.route(
            message,
            has_attachments=has_attachments,
            preferred_agent=preferred_agent,
            active_workflow_agent=active_workflow_agent,
        )

    async def aroute(
        self,
        message: str,
        *,
        has_attachments: bool = False,
        preferred_agent: str | None = None,
        active_workflow_agent: str | None = None,
    ) -> RouteDecision:
        """Async routing: session-continuation intents → LLM router → hybrid fallback."""
        decision = self.router.deterministic_safety(
            message,
            has_attachments=has_attachments,
            preferred_agent=preferred_agent,
            active_workflow_agent=active_workflow_agent,
        )
        if decision:
            logger.info(
                "会话延续路由: agents=%s method=%s reason=%s",
                decision.agents,
                decision.method,
                decision.reason,
            )
            return decision

        if str(settings.AGENT_ROUTING_MODE).strip().lower() != "embedding_only":
            llm_decision = await self.router.route_llm(
                message,
                has_attachments=has_attachments,
                preferred_agent=preferred_agent,
                active_workflow_agent=active_workflow_agent,
            )
            if llm_decision:
                logger.info(
                    "LLM 路由: agents=%s mode=%s reason=%s",
                    llm_decision.agents,
                    llm_decision.execution_mode,
                    llm_decision.reason,
                )
                return llm_decision

        fallback = self.router.route(
            message,
            has_attachments=has_attachments,
            preferred_agent=preferred_agent,
            active_workflow_agent=active_workflow_agent,
        )
        logger.info(
            "降级路由: agents=%s mode=%s method=%s reason=%s",
            fallback.agents,
            fallback.execution_mode,
            fallback.method,
            fallback.reason,
        )
        return fallback

    def _runtime_context(self, message: str) -> str:
        try:
            rewritten = retrieval_query_rewriter.rewrite(
                message,
                context_state=self.context_state,
            )
            items = LongTermMemoryStore().recall(
                user_id=self.user_id,
                query=rewritten.rewritten_query,
            )
        except Exception as exc:  # noqa: BLE001 - memory must not block a request
            logger.info("长期记忆未注入: %s", exc)
            return "无"
        if not items:
            return "无"
        return "\n".join(f"- {item['content']}" for item in items)

    def _management_agent(self, agent: str):
        kwargs = {"user_id": self.user_id, "session_uuid": self.session_uuid}
        if agent == "dataset":
            return DatasetAgent(**kwargs)
        if agent == "training":
            return TrainingAgent(**kwargs)
        if agent == "catalog":
            return CatalogAgent(**kwargs)
        return KnowledgeAgent(**kwargs)

    def _agent_stream(
        self,
        agent_name: str,
        message: str,
        attachment_paths: list[str],
        history: list[dict[str, str]] | None,
        extra_context: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Return the async event stream for a single agent.

        User-scoped custom instructions (from main) are forwarded to agents that
        support them, in both single and multi-agent paths.
        """
        if agent_name == "detection":
            agent = self.detection_agent_factory(user_id=self.user_id, scene_id=self.scene_id)
            if self.custom_instructions:
                return agent.stream(
                    message, attachment_paths, history, self.custom_instructions
                )
            return agent.stream(message, attachment_paths, history)
        agent = self._management_agent(agent_name)
        context = self._runtime_context(message)
        if extra_context:
            context = f"{context}\n\n{extra_context}" if context != "无" else extra_context
        if self.custom_instructions:
            return agent.stream(message, history, context, self.custom_instructions)
        return agent.stream(message, history, context)

    async def stream(
        self,
        message: str,
        attachment_paths: list[str],
        history: list[dict[str, str]] | None = None,
        decision: RouteDecision | None = None,
    ) -> AsyncGenerator[dict, None]:
        selected = decision or await self.aroute(message, has_attachments=bool(attachment_paths))
        yield selected.event()

        if selected.is_pipeline:
            async for event in self._pipeline_stream(message, attachment_paths, history, selected):
                yield event
            return

        if selected.is_parallel:
            async for event in self._parallel_stream(message, attachment_paths, history, selected):
                yield event
            return

        async for event in self._agent_stream(selected.agent, message, attachment_paths, history):
            event.setdefault("agent", selected.agent)
            yield event

    async def _pipeline_stream(
        self,
        message: str,
        attachment_paths: list[str],
        history: list[dict[str, str]] | None,
        decision: RouteDecision,
    ) -> AsyncGenerator[dict, None]:
        """Execute agents sequentially, feeding upstream results downstream, then summarize."""
        agents = list(dict.fromkeys(a.strip().lower() for a in decision.agents if a.strip()))
        if len(agents) < 2:
            async for event in self._agent_stream(agents[0], message, attachment_paths, history):
                event.setdefault("agent", agents[0])
                yield event
            return

        yield {
            "type": "parallel_progress",
            "agent": "supervisor",
            "status": "pipeline_started",
            "agents": agents,
            "content": f"开始执行流水线：{' → '.join(agents)}",
        }

        drafts: dict[str, str] = {name: "" for name in agents}
        structural: dict[str, list[dict]] = {name: [] for name in agents}
        interactive = False
        upstream_context = ""

        for index, agent_name in enumerate(agents):
            sub_message = decision.task_for(agent_name, message)
            if index > 0:
                yield {
                    "type": "parallel_progress",
                    "agent": "supervisor",
                    "status": "pipeline_step",
                    "agents": agents,
                    "current": agent_name,
                    "completed": agents[:index],
                    "content": f"{agents[index - 1]} 完成，正在执行 {agent_name}...",
                }
            step_context = COLLABORATION_CONTEXT
            if upstream_context:
                step_context = f"{COLLABORATION_CONTEXT}\n\n{upstream_context}"
            try:
                async for event in self._agent_stream(
                    agent_name,
                    sub_message,
                    attachment_paths,
                    history,
                    extra_context=step_context,
                ):
                    event.setdefault("agent", agent_name)
                    event_type = event.get("type")
                    if event_type == "text_chunk":
                        drafts[agent_name] += event.get("content", "")
                        continue
                    if event_type in ("tool_result", "detection_result", "error"):
                        structural[agent_name].append(dict(event))
                    if event_type in _INTERACTIVE_EVENT_TYPES:
                        interactive = True
                    yield event
            except Exception as exc:  # noqa: BLE001
                logger.exception("流水线 Agent %s 执行失败: %s", agent_name, exc)
                structural[agent_name].append(
                    {"type": "error", "agent": agent_name, "content": f"{agent_name} Agent 执行失败：{exc}"}
                )
                yield {
                    "type": "error",
                    "agent": agent_name,
                    "content": f"{agent_name} Agent 执行失败：{exc}",
                }
                # 主 Agent 失败时不再继续下游，交由汇总说明情况。
                break

            # 出现表单/确认卡等交互事件时，本轮以卡片收尾，不再继续下游 Agent；
            # 已完成 Agent 的结果仍会在下方汇总呈现。
            if interactive:
                break

            upstream_context = self._upstream_context(agent_name, drafts[agent_name], structural[agent_name])

        async for event in self._supervisor_summary(drafts, structural, agents, message, history):
            yield event

        yield {
            "type": "parallel_progress",
            "agent": "supervisor",
            "status": "completed",
            "agents": agents,
            "completed": agents,
            "failed": [],
            "content": "流水线执行完成。",
        }

    async def _parallel_stream(
        self,
        message: str,
        attachment_paths: list[str],
        history: list[dict[str, str]] | None,
        decision: RouteDecision,
    ) -> AsyncGenerator[dict, None]:
        """Execute agents concurrently, stream structural events live, then summarize.

        Free-text chunks are collected as drafts and merged by the supervisor into a
        single voice instead of being shown per agent.
        """
        agents = list(dict.fromkeys(a.strip().lower() for a in decision.agents if a.strip()))
        if not agents:
            agents = ["knowledge"]

        yield {
            "type": "parallel_progress",
            "agent": "supervisor",
            "status": "started",
            "agents": agents,
            "content": f"正在协调 {', '.join(agents)} Agent 并行执行...",
        }

        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        drafts: dict[str, str] = {name: "" for name in agents}
        structural: dict[str, list[dict]] = {name: [] for name in agents}

        async def run_agent(agent_name: str) -> None:
            sub_message = decision.task_for(agent_name, message)
            try:
                async for event in self._agent_stream(
                    agent_name,
                    sub_message,
                    attachment_paths,
                    history,
                    extra_context=COLLABORATION_CONTEXT,
                ):
                    await queue.put((agent_name, dict(event)))
            except Exception as exc:  # noqa: BLE001
                logger.exception("并行 Agent %s 执行异常: %s", agent_name, exc)
                await queue.put(
                    (
                        agent_name,
                        {
                            "type": "error",
                            "agent": agent_name,
                            "content": f"{agent_name} Agent 执行出错：{exc}",
                        },
                    )
                )
            finally:
                await queue.put((agent_name, {"type": "__agent_done__"}))

        tasks = [asyncio.create_task(run_agent(agent_name)) for agent_name in agents]
        done_count = 0
        while done_count < len(agents):
            agent_name, event = await queue.get()
            event_type = event.get("type")
            if event_type == "__agent_done__":
                done_count += 1
                continue
            event.setdefault("agent", agent_name)
            if event_type == "text_chunk":
                drafts[agent_name] += event.get("content", "")
                continue
            if event_type in ("tool_result", "detection_result", "error"):
                structural[agent_name].append(dict(event))
            yield event

        await asyncio.gather(*tasks, return_exceptions=True)

        # 确认卡/表单等交互卡片已实时推给前端；其余 Agent 的结果照常汇总，
        # 卡片与文字汇总在界面上共存，不再因出现卡片而丢弃其他 Agent 的回答。
        async for event in self._supervisor_summary(drafts, structural, agents, message, history):
            yield event

        yield {
            "type": "parallel_progress",
            "agent": "supervisor",
            "status": "completed",
            "agents": agents,
            "completed": agents,
            "failed": [],
            "content": f"并行执行完成：{len(agents)} 个 Agent 全部返回。",
        }

    @staticmethod
    def _upstream_context(agent_name: str, draft: str, events: list[dict]) -> str:
        """Build the context injected into downstream pipeline agents."""
        parts = []
        for event in events:
            if event.get("type") == "detection_result":
                parts.append(
                    f"上一步 {agent_name} Agent 的检测结果：\n"
                    f"{json.dumps(sanitize_result_payload(event.get('result') or {}), ensure_ascii=False, default=str)}"
                )
        if draft:
            parts.append(f"上一步 {agent_name} Agent 的回复：\n{draft}")
        return "\n\n".join(parts)

    async def _supervisor_summary(
        self,
        drafts: dict[str, str],
        structural: dict[str, list[dict]],
        agents: list[str],
        message: str,
        history: list[dict[str, str]] | None,
    ) -> AsyncGenerator[dict, None]:
        """Merge agent drafts and structural results into one streamed supervisor reply.

        The summary receives the original user message, so intents that no agent
        covered can be honestly flagged instead of silently dropped. On LLM failure
        the raw drafts are concatenated as a fallback.
        """
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        from app.agent.history import build_chat_history

        material: list[str] = []
        for agent_name in agents:
            draft = drafts.get(agent_name, "")
            if draft:
                material.append(f"[{agent_name} 的回复草稿]\n{draft}")
            for event in structural.get(agent_name, []):
                event_type = event.get("type")
                if event_type == "detection_result":
                    material.append(
                        f"[{agent_name} 检测结果]\n"
                        f"{json.dumps(sanitize_result_payload(event.get('result') or {}), ensure_ascii=False, default=str)}"
                    )
                elif event_type == "tool_result":
                    content = str(sanitize_result_payload(event.get("content", "")))
                    material.append(
                        f"[{agent_name} 工具 {event.get('tool', 'tool')} 结果]\n{content}"
                    )
                elif event_type == "error":
                    material.append(f"[{agent_name} 执行错误]\n{event.get('content', '')}")

        if not material:
            yield {
                "type": "text_chunk",
                "agent": "supervisor",
                "content": "各 Agent 未返回可汇总的内容，请稍后重试。",
            }
            return

        yield {
            "type": "parallel_progress",
            "agent": "supervisor",
            "status": "summarizing",
            "agents": agents,
            "content": "各 Agent 执行完毕，正在汇总结果...",
        }

        chat_history = build_chat_history(history)

        prompt = SUPERVISOR_SUMMARY_PROMPT.format(
            user_message=message,
            context="\n\n".join(material),
        )
        system_content = (
            "你是 VisionPay 的多智能体调度中枢。请根据用户问题以及各 Agent 的执行结果，"
            "整合成一段简洁、连贯、专业的中文回复。不要编造数据中不存在的信息。"
        )
        if self.custom_instructions:
            # 与各 Agent 相同的安全渲染：用户偏好只影响表达风格，不改变事实与安全边界。
            system_content += CUSTOM_INSTRUCTIONS_PROMPT.format(
                custom_instructions=render_custom_instructions(self.custom_instructions)
            )
        messages = [
            SystemMessage(content=system_content),
            *chat_history,
            HumanMessage(content=prompt),
        ]

        try:
            llm = ChatOpenAI(
                model=settings.DEEPSEEK_MODEL,
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
                temperature=settings.DEEPSEEK_TEMPERATURE,
                streaming=True,
                stream_usage=True,
            )
            async for event in llm.astream_events(messages, version="v2"):
                if event.get("event") != "on_chat_model_stream":
                    continue
                chunk = event.get("data", {}).get("chunk")
                usage = usage_metadata(chunk)
                if usage:
                    yield {
                        "type": "model_usage",
                        "agent": "supervisor",
                        "run_id": str(event.get("run_id") or ""),
                        "usage": usage,
                    }
                content = getattr(chunk, "content", "")
                if isinstance(content, list):
                    content = "".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in content
                    )
                if content:
                    yield {"type": "text_chunk", "agent": "supervisor", "content": content}
        except Exception as exc:  # noqa: BLE001 - summary failure must not kill the stream
            logger.exception("Supervisor 汇总失败，降级为直接拼接结果: %s", exc)
            yield {
                "type": "text_chunk",
                "agent": "supervisor",
                "content": self._fallback_summary(drafts, structural, agents),
            }

    @staticmethod
    def _fallback_summary(
        drafts: dict[str, str],
        structural: dict[str, list[dict]],
        agents: list[str],
    ) -> str:
        """Concatenate raw agent outputs when the summary LLM is unavailable."""
        parts = ["当前各 Agent 执行结果如下："]
        for agent_name in agents:
            draft = drafts.get(agent_name, "")
            if draft:
                parts.append(f"\n【{agent_name}】\n{draft}")
            for event in structural.get(agent_name, []):
                event_type = event.get("type")
                if event_type == "detection_result":
                    parts.append(
                        f"\n【{agent_name} 检测结果】\n"
                        f"{json.dumps(sanitize_result_payload(event.get('result') or {}), ensure_ascii=False, default=str)}"
                    )
                elif event_type == "tool_result":
                    content = str(sanitize_result_payload(event.get("content", "")))
                    parts.append(
                        f"\n【{agent_name} 工具 {event.get('tool', 'tool')}】\n{content}"
                    )
                elif event_type == "error":
                    parts.append(f"\n【{agent_name} 错误】\n{event.get('content', '')}")
        if len(parts) == 1:
            return "各 Agent 未返回可汇总的内容，请稍后重试。"
        return "\n".join(parts)

    async def _execute_parallel_agents(
        self,
        message: str,
        attachment_paths: list[str],
        history: list[dict[str, str]] | None,
        agents: list[str],
    ) -> list[tuple[str, list[dict], str]]:
        """Run each agent concurrently and collect their raw events and produced text.

        Kept for unit tests and potential batch use; the streaming path uses
        ``_parallel_stream`` instead.
        """

        async def run_one(agent_name: str) -> tuple[str, list[dict], str]:
            events: list[dict] = []
            text = ""
            async for event in self._agent_stream(agent_name, message, attachment_paths, history):
                events.append(dict(event))
                if event.get("type") == "text_chunk":
                    text += event.get("content", "")
            return agent_name, events, text

        async def run_one_safe(agent_name: str) -> tuple[str, list[dict], str]:
            try:
                return await asyncio.wait_for(
                    run_one(agent_name),
                    timeout=PARALLEL_AGENT_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning("并行 Agent %s 执行超时（>%ss）", agent_name, PARALLEL_AGENT_TIMEOUT_SECONDS)
                return (
                    agent_name,
                    [
                        {
                            "type": "error",
                            "agent": agent_name,
                            "content": f"{agent_name} Agent 执行超时，未能在 {PARALLEL_AGENT_TIMEOUT_SECONDS} 秒内返回结果。",
                        }
                    ],
                    "",
                )
            except Exception as exc:  # noqa: BLE001 - must not break parallel pipeline
                logger.exception("并行 Agent %s 执行异常: %s", agent_name, exc)
                return (
                    agent_name,
                    [
                        {
                            "type": "error",
                            "agent": agent_name,
                            "content": f"{agent_name} Agent 执行出错：{exc}",
                        }
                    ],
                    "",
                )

        tasks = [asyncio.create_task(run_one_safe(agent_name)) for agent_name in agents]
        return list(await asyncio.gather(*tasks))
