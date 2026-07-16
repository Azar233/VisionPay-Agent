import json

import pytest

from app.agent.agents.knowledge_agent import KnowledgeAgent
from app.agent.tools.knowledge_tools import build_knowledge_tools


@pytest.mark.asyncio
async def test_training_capability_question_uses_runtime_fact_without_rag():
    agent = KnowledgeAgent.__new__(KnowledgeAgent)
    agent.name = "knowledge"
    agent.tools = build_knowledge_tools(1, "session")

    events = [
        event
        async for event in agent.stream("Training agent 的主要职责是什么？")
    ]

    assert [event["type"] for event in events] == [
        "tool_call",
        "tool_result",
        "text_chunk",
    ]
    assert events[0]["tool"] == "get_platform_agent_capabilities"
    payload = json.loads(events[1]["content"])
    assert payload["source"] == "platform_runtime_capabilities"
    assert "暂停/恢复" in events[2]["content"]
    assert "知识库" not in events[2]["content"]
    assert "API" not in events[2]["content"]


@pytest.mark.asyncio
async def test_agent_count_question_uses_runtime_fact_without_rag():
    agent = KnowledgeAgent.__new__(KnowledgeAgent)
    agent.name = "knowledge"
    agent.tools = build_knowledge_tools(1, "session")

    events = [event async for event in agent.stream("系统一共有多少个智能体？")]

    payload = json.loads(events[1]["content"])
    assert payload["count"] == 5
    assert "Supervisor 只负责路由与编排" in events[2]["content"]
