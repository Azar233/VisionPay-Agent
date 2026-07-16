"""Supervisor that routes a request to one scoped domain Agent."""

from __future__ import annotations

from typing import AsyncGenerator, Callable

from app.agent.agents import CatalogAgent, DatasetAgent, KnowledgeAgent, TrainingAgent
from app.agent.detection_agent import DetectionAgent
from app.agent.routing import AgentRouter, RouteDecision
from app.core.logger import get_logger
from app.memory import LongTermMemoryStore

logger = get_logger(__name__)


class MultiAgentOrchestrator:
    def __init__(
        self,
        *,
        user_id: int,
        scene_id: int | None,
        session_uuid: str,
        detection_agent_factory: Callable = DetectionAgent,
    ) -> None:
        self.user_id = user_id
        self.scene_id = scene_id
        self.session_uuid = session_uuid
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

    def _runtime_context(self, message: str) -> str:
        try:
            items = LongTermMemoryStore().recall(
                user_id=self.user_id,
                query=message,
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

    async def stream(
        self,
        message: str,
        attachment_paths: list[str],
        history: list[dict[str, str]] | None = None,
        decision: RouteDecision | None = None,
    ) -> AsyncGenerator[dict, None]:
        selected = decision or self.route(message, has_attachments=bool(attachment_paths))
        yield selected.event()
        if selected.agent == "detection":
            agent = self.detection_agent_factory(user_id=self.user_id, scene_id=self.scene_id)
            async for event in agent.stream(message, attachment_paths, history):
                event.setdefault("agent", "detection")
                yield event
            return

        agent = self._management_agent(selected.agent)
        context = self._runtime_context(message)
        async for event in agent.stream(message, history, context):
            yield event
