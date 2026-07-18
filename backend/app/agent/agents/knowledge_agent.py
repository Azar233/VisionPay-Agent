"""Knowledge, fault-case and explicit-memory specialist."""

import json
from typing import AsyncGenerator

from app.agent.prompts import KNOWLEDGE_PROMPT
from app.agent.scoped_agent import ScopedToolAgent
from app.agent.tools import build_interaction_tools, build_knowledge_tools
from app.rag.grounding import (
    KNOWLEDGE_TOOL,
    forced_retrieval_tools,
    merge_retrieval_results,
    structured_retrieval_result,
)


class KnowledgeAgent(ScopedToolAgent):
    def __init__(self, *, user_id: int, session_uuid: str) -> None:
        super().__init__(
            name="knowledge",
            system_prompt=KNOWLEDGE_PROMPT,
            tools=build_knowledge_tools(user_id, session_uuid)
            + build_interaction_tools("knowledge"),
        )

    @staticmethod
    def _capability_target(message: str) -> str | None:
        normalized = message.strip().lower()
        scope_cues = ("职责", "负责", "功能", "做什么", "干什么", "能做什么", "工作")
        count_cues = ("多少个智能体", "几个智能体", "多少个 agent", "几个 agent", "agent 数量")
        if any(cue in normalized for cue in count_cues):
            return "all"
        aliases = {
            "detection": ("detection agent", "检测 agent", "检测智能体"),
            "dataset": ("dataset agent", "数据集 agent", "数据集智能体"),
            "training": ("training agent", "训练 agent", "训练智能体"),
            "catalog": ("catalog agent", "价目表 agent", "商品目录 agent"),
            "knowledge": ("knowledge agent", "知识 agent", "知识智能体"),
        }
        if not any(cue in normalized for cue in scope_cues):
            return None
        for agent_name, names in aliases.items():
            if any(name in normalized for name in names):
                return agent_name
        return None

    async def stream(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
        runtime_context: str = "无",
    ) -> AsyncGenerator[dict, None]:
        target = self._capability_target(message)
        if target:
            tool = next(
                item for item in self.tools if item.name == "get_platform_agent_capabilities"
            )
            tool_input = {"agent_name": target}
            yield {
                "type": "tool_call",
                "agent": self.name,
                "tool": tool.name,
                "input": tool_input,
            }
            content = tool.invoke(tool_input)
            yield {
                "type": "tool_result",
                "agent": self.name,
                "tool": tool.name,
                "content": content,
            }
            payload = json.loads(content)
            yield {
                "type": "text_chunk",
                "agent": self.name,
                "content": payload["answer"],
            }
            return

        retrievals = []
        for tool_name in forced_retrieval_tools(message):
            tool = next((item for item in self.tools if item.name == tool_name), None)
            if tool is None:
                continue
            tool_input = {"query": message}
            if tool_name == KNOWLEDGE_TOOL:
                tool_input["domain"] = ""
            yield {
                "type": "tool_call",
                "agent": self.name,
                "tool": tool_name,
                "input": tool_input,
                "forced": True,
            }
            content = tool.invoke(tool_input)
            yield {
                "type": "tool_result",
                "agent": self.name,
                "tool": tool_name,
                "content": content,
                "forced": True,
            }
            try:
                parsed = json.loads(content)
            except (TypeError, json.JSONDecodeError):
                parsed = {"error": "检索工具返回了无法解析的结果"}
            retrievals.append(
                structured_retrieval_result(tool_name=tool_name, result=parsed)
            )

        augmented_history = list(history or [])
        if retrievals:
            grounding = merge_retrieval_results(message, retrievals)
            yield {
                "type": "knowledge_sources",
                "agent": self.name,
                **grounding,
            }
            augmented_history.append(
                {
                    "role": "system",
                    "content": (
                        "系统已经在本轮强制执行知识检索。请直接依据下列结构化检索结果回答，"
                        "不要重复调用 search_management_knowledge 或 search_fault_cases。"
                        "如果 has_knowledge=false，必须明确说明没有检索到满足阈值的可靠资料；"
                        "不要把模型自身推断表述为平台事实。\n"
                        + json.dumps(grounding, ensure_ascii=False)
                    ),
                }
            )

        async for event in super().stream(message, augmented_history, runtime_context):
            yield event
