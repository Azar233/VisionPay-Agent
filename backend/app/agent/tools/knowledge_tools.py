"""Shared knowledge, fault-case and explicit long-term-memory tools."""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from app.agent.tools.common import json_text
from app.memory import LongTermMemoryStore
from app.rag import KnowledgeRetriever


def build_knowledge_tools(user_id: int, session_uuid: str | None = None) -> list:
    def search_management_knowledge(query: str, domain: str = "") -> str:
        """检索 VisionPay 操作规范和领域知识；domain 可为 dataset/training/detection/catalog。"""
        try:
            results = KnowledgeRetriever().search(query, domain=domain or None)
            return json_text({"query": query, "results": results})
        except Exception as exc:  # noqa: BLE001 - tool returns diagnosable error
            return json_text({"error": f"知识库当前不可用：{exc}"})

    def search_fault_cases(query: str) -> str:
        """根据现象或错误信息检索历史故障案例和解决方案。"""
        try:
            retriever = KnowledgeRetriever(KnowledgeRetriever.FAULT_COLLECTION)
            return json_text({"query": query, "results": retriever.search(query)})
        except Exception as exc:  # noqa: BLE001
            return json_text({"error": f"故障案例库当前不可用：{exc}"})

    def remember_management_preference(content: str, category: str = "preference") -> str:
        """仅当用户明确要求记住长期偏好或稳定事实时调用；不得保存密码、Token、价格或临时任务状态。"""
        try:
            item = LongTermMemoryStore().remember(
                user_id=user_id,
                content=content,
                category=category,
                session_uuid=session_uuid,
            )
            return json_text(item)
        except Exception as exc:  # noqa: BLE001
            return json_text({"error": f"长期记忆保存失败：{exc}"})

    def recall_management_memory(query: str) -> str:
        """检索当前经营者过去明确保存的偏好和稳定事实。"""
        try:
            items = LongTermMemoryStore().recall(user_id=user_id, query=query)
            return json_text({"query": query, "results": items})
        except Exception as exc:  # noqa: BLE001
            return json_text({"error": f"长期记忆检索失败：{exc}"})

    return [
        StructuredTool.from_function(
            search_management_knowledge, name="search_management_knowledge"
        ),
        StructuredTool.from_function(search_fault_cases, name="search_fault_cases"),
        StructuredTool.from_function(
            remember_management_preference, name="remember_management_preference"
        ),
        StructuredTool.from_function(
            recall_management_memory, name="recall_management_memory"
        ),
    ]
