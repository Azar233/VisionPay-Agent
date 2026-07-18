import json

import pytest

from app.agent.agents.knowledge_agent import KnowledgeAgent
from app.agent.routing import RouteDecision
from app.agent.scoped_agent import ScopedToolAgent
from app.entity.db_models import ChatMessage, ChatSession
from app.rag.grounding import (
    FAULT_TOOL,
    KNOWLEDGE_TOOL,
    forced_retrieval_tools,
    merge_retrieval_results,
    structured_retrieval_result,
)


class _FakeTool:
    def __init__(self, name, payload, calls):
        self.name = name
        self.payload = payload
        self.calls = calls

    def invoke(self, tool_input):
        self.calls.append((self.name, tool_input))
        return json.dumps(self.payload, ensure_ascii=False)


def _retrieval_payload(source="dataset/dataset_lifecycle.md"):
    return {
        "original_query": "数据集冻结有什么影响",
        "rewritten_query": "Dataset 数据集版本冻结条件和影响范围",
        "domain": "dataset",
        "purpose": "dataset.freeze",
        "context_used": True,
        "items": [
            {
                "id": "chunk-1",
                "content": "冻结后数据集内容只读，必须派生新草稿后继续修改。",
                "similarity": 0.87654,
                "rank": 1,
                "metadata": {"source": source, "domain": "dataset"},
            }
        ],
    }


def test_forced_retrieval_policy_distinguishes_knowledge_fault_and_memory():
    assert forced_retrieval_tools("冻结数据集版本有什么影响？") == (KNOWLEDGE_TOOL,)
    assert forced_retrieval_tools("页面输入数字后崩溃并报错") == (
        FAULT_TOOL,
        KNOWLEDGE_TOOL,
    )
    assert forced_retrieval_tools("记住我默认使用中文回答") == ()
    assert forced_retrieval_tools("你好") == ()


def test_structured_sources_are_stable_and_deduplicated():
    first = structured_retrieval_result(
        tool_name=KNOWLEDGE_TOOL,
        result=_retrieval_payload(),
    )
    second = structured_retrieval_result(
        tool_name=KNOWLEDGE_TOOL,
        result=_retrieval_payload(),
    )
    merged = merge_retrieval_results("冻结有什么影响", [first, second])

    assert merged["forced"] is True
    assert merged["has_knowledge"] is True
    assert len(merged["sources"]) == 1
    assert merged["sources"][0] == {
        "id": "chunk-1",
        "collection": "knowledge",
        "source": "dataset/dataset_lifecycle.md",
        "title": "dataset lifecycle",
        "domain": "dataset",
        "similarity": 0.8765,
        "rank": 1,
        "excerpt": "冻结后数据集内容只读，必须派生新草稿后继续修改。",
    }


@pytest.mark.asyncio
async def test_knowledge_agent_retrieves_before_generation(monkeypatch):
    calls = []
    captured = {}

    async def fake_parent_stream(self, message, history=None, runtime_context="无"):
        captured["history"] = history
        yield {"type": "text_chunk", "agent": self.name, "content": "基于检索结果回答"}

    monkeypatch.setattr(ScopedToolAgent, "stream", fake_parent_stream)
    agent = KnowledgeAgent.__new__(KnowledgeAgent)
    agent.name = "knowledge"
    agent.tools = [_FakeTool(KNOWLEDGE_TOOL, _retrieval_payload(), calls)]

    events = [event async for event in agent.stream("冻结数据集版本有什么影响？")]

    assert [event["type"] for event in events] == [
        "tool_call",
        "tool_result",
        "knowledge_sources",
        "text_chunk",
    ]
    assert calls[0][0] == KNOWLEDGE_TOOL
    assert events[0]["forced"] is True
    assert events[2]["has_knowledge"] is True
    assert events[2]["sources"][0]["source"] == "dataset/dataset_lifecycle.md"
    assert "系统已经在本轮强制执行知识检索" in captured["history"][-1]["content"]
    assert "dataset/dataset_lifecycle.md" in captured["history"][-1]["content"]


def test_chat_persists_and_restores_structured_knowledge_sources(
    client, db_session, monkeypatch
):
    from app.api import chat as chat_api

    client.post(
        "/api/auth/register",
        json={
            "username": "grounding_user",
            "email": "grounding@example.com",
            "password": "123456",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "grounding_user", "password": "123456"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    session_uuid = client.post(
        "/api/chat/sessions", headers=headers, json={"title": "grounding"}
    ).json()["session_uuid"]
    source_event = {
        "type": "knowledge_sources",
        "agent": "knowledge",
        "query": "冻结有什么影响",
        "forced": True,
        "has_knowledge": True,
        "retrievals": [],
        "sources": [
            {
                "id": "chunk-1",
                "collection": "knowledge",
                "source": "dataset/dataset_lifecycle.md",
                "title": "dataset lifecycle",
                "domain": "dataset",
                "similarity": 0.88,
                "rank": 1,
                "excerpt": "冻结后只读。",
            }
        ],
    }

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def route(self, message, **kwargs):
            return RouteDecision("knowledge", "test", 1.0, "grounding test")

        async def stream(self, message, attachment_paths, history, decision=None):
            yield decision.event()
            yield source_event
            yield {"type": "text_chunk", "agent": "knowledge", "content": "冻结后只读。"}

    monkeypatch.setattr(chat_api, "MultiAgentOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(chat_api.settings, "DEEPSEEK_API_KEY", "test-key")
    response = client.post(
        "/api/chat/stream",
        headers=headers,
        json={
            "message": "冻结有什么影响",
            "attachment_paths": [],
            "attachment_names": [],
            "session_uuid": session_uuid,
        },
    )

    assert response.status_code == 200
    assert '"type": "knowledge_sources"' in response.text
    db_session.expire_all()
    session = db_session.query(ChatSession).filter_by(session_uuid=session_uuid).one()
    assistant = (
        db_session.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id, ChatMessage.role == "assistant")
        .one()
    )
    assert assistant.tool_calls["knowledge_sources"]["sources"][0]["id"] == "chunk-1"

    restored = client.get(f"/api/chat/sessions/{session_uuid}", headers=headers)
    assert restored.status_code == 200
    restored_assistant = [
        item for item in restored.json()["messages"] if item["role"] == "assistant"
    ][0]
    assert restored_assistant["knowledge_sources"]["forced"] is True
