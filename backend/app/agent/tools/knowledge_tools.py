"""Shared knowledge, fault-case and explicit long-term-memory tools."""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from app.agent.tools.common import json_text
from app.memory import LongTermMemoryStore
from app.rag import KnowledgeRetriever


PLATFORM_AGENT_CAPABILITIES = {
    "detection": "Detection Agent：对聊天附件执行单图、批量图片或视频商品检测，返回类别、置信度、检测框和计价结果。",
    "dataset": "Dataset Agent：查询数据集版本与详情；预览派生、冻结、归档、删除等写操作；收集添加样品所需字段，并交接到数据集页面由用户选图和人工绘框。",
    "training": "Training Agent：查询训练任务列表、实时状态和训练指标；发起带参数的训练启动、停止任务和切换默认模型。写操作必须先展示影响预览并由确认卡执行；当前不开放训练结果导入、模型发布、暂停/恢复任务，也不直接修改运行中任务的参数。",
    "catalog": "Catalog Agent：实时查询商品目录、条码、价格和缺价状态；发起改价或清除价格，写操作必须通过影响预览与确认卡。",
    "knowledge": "Knowledge Agent：解释平台能力和通用概念，检索操作知识与故障案例，并仅在经营者明确要求时保存或召回稳定偏好。",
}


def platform_agent_capabilities_payload(agent_name: str = "all") -> dict:
    target = (agent_name or "all").strip().lower()
    if target in PLATFORM_AGENT_CAPABILITIES:
        return {
            "agent": target,
            "answer": PLATFORM_AGENT_CAPABILITIES[target],
            "source": "platform_runtime_capabilities",
        }
    overview = "\n".join(
        ["系统共有 5 个领域 Agent："]
        + [f"- {description}" for description in PLATFORM_AGENT_CAPABILITIES.values()]
        + ["Supervisor 只负责路由与编排，不计入 5 个领域 Agent。"]
    )
    return {
        "agent": "all",
        "count": 5,
        "answer": overview,
        "source": "platform_runtime_capabilities",
    }


def build_knowledge_tools(user_id: int, session_uuid: str | None = None) -> list:
    def get_platform_agent_capabilities(agent_name: str = "all") -> str:
        """查询固定的平台 Agent 数量、职责和权限边界；不依赖 Embedding、RAG 或外部知识库。"""
        return json_text(platform_agent_capabilities_payload(agent_name))

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
            get_platform_agent_capabilities, name="get_platform_agent_capabilities"
        ),
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
