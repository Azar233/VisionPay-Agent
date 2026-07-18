from app.agent.routing import RouteDecision
from app.entity.db_models import ChatMessage, ChatSession, User
from app.services.conversation_context_service import conversation_context_service


def _user(db_session, suffix="context"):
    user = User(
        username=f"{suffix}_user",
        email=f"{suffix}@example.com",
        hashed_password="test",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_history_uses_incremental_summary_and_recent_verbatim_messages(
    db_session, monkeypatch
):
    from app.config.settings import settings

    monkeypatch.setattr(settings, "AGENT_CONTEXT_RECENT_MESSAGES", 4)
    monkeypatch.setattr(settings, "AGENT_CONTEXT_HISTORY_TOKENS", 6000)
    monkeypatch.setattr(settings, "AGENT_CONTEXT_SUMMARY_TOKENS", 180)
    user = _user(db_session, "summary")
    session = ChatSession(
        user_id=user.id,
        session_uuid="summary-session",
        title="summary",
        context_state={
            "active_agent": "dataset",
            "entities": {"dataset_id": 17},
        },
    )
    db_session.add(session)
    db_session.flush()
    for index in range(10):
        db_session.add(
            ChatMessage(
                session_id=session.id,
                role="user" if index % 2 == 0 else "assistant",
                agent_used="dataset",
                content=f"第 {index} 条消息 " + ("上下文" * 12),
                tool_calls={"tools": ["get_dataset_version_detail"]}
                if index == 3
                else None,
                tool_result='{"dataset_id": 17, "version": "v17"}'
                if index == 3
                else None,
            )
        )
    db_session.commit()
    db_session.refresh(session)

    history, token_count = conversation_context_service.prepare_history(session)

    assert history[0]["role"] == "system"
    assert "较早对话增量摘要" in history[0]["content"]
    assert any("结构化会话状态" in item["content"] for item in history)
    assert any("dataset_id" in item["content"] for item in history)
    assert [item["role"] for item in history[-4:]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert session.summarized_message_id is not None
    assert token_count <= settings.AGENT_CONTEXT_HISTORY_TOKENS


def test_history_trims_oversized_recent_message_to_token_budget(db_session, monkeypatch):
    from app.config.settings import settings

    monkeypatch.setattr(settings, "AGENT_CONTEXT_RECENT_MESSAGES", 12)
    monkeypatch.setattr(settings, "AGENT_CONTEXT_HISTORY_TOKENS", 1000)
    user = _user(db_session, "budget")
    session = ChatSession(
        user_id=user.id,
        session_uuid="budget-session",
        title="budget",
        context_state={},
    )
    db_session.add(session)
    db_session.flush()
    db_session.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content="非常长的上下文" * 3000,
        )
    )
    db_session.commit()
    db_session.refresh(session)

    history, token_count = conversation_context_service.prepare_history(session)

    assert history[-1]["role"] == "user"
    assert token_count <= settings.AGENT_CONTEXT_HISTORY_TOKENS


def test_structured_state_tracks_form_tool_handoff_and_confirmation(db_session):
    user = _user(db_session, "state")
    session = ChatSession(
        user_id=user.id,
        session_uuid="state-session",
        title="state",
        context_state={},
    )
    db_session.add(session)
    db_session.flush()

    state = conversation_context_service.apply_turn(
        session,
        agent="dataset",
        input_form={
            "form_id": "form-1",
            "purpose": "dataset.add_samples",
            "known_values": {"dataset_id": 8},
            "fields": [
                {"name": "dataset_id", "required": True},
                {"name": "class_name", "required": True},
            ],
        },
        tool_events=[
            {
                "tool": "get_dataset_version_detail",
                "input": {"dataset_id": 8},
                "result": '{"dataset_id": 8, "version": "draft-v8"}',
            }
        ],
    )
    assert state["active_agent"] == "dataset"
    assert state["active_workflow"]["status"] == "awaiting_input"
    assert state["entities"]["dataset_id"] == 8
    assert state["entities"]["version"] == "draft-v8"
    assert state["missing_fields"] == ["class_name"]
    assert state["pending"]["form_id"] == "form-1"

    state = conversation_context_service.apply_turn(
        session,
        agent="dataset",
        form_submission={
            "form_id": "form-1",
            "purpose": "dataset.add_samples",
            "values": {"dataset_id": 8, "class_name": "cola"},
        },
        handoff={
            "handoff_id": "handoff-1",
            "status": "ready_for_handoff",
            "context": {"dataset_id": 8},
        },
        confirmation={
            "operation_uuid": "operation-1",
            "action": "dataset.freeze",
            "status": "pending",
            "parameters": {"dataset_id": 8},
            "confirmation_token": "must-not-be-persisted",
        },
    )
    assert state["known_values"]["class_name"] == "cola"
    assert "form_id" not in state["pending"]
    assert state["pending"]["handoff_id"] == "handoff-1"
    assert state["pending"]["operation_uuid"] == "operation-1"
    assert state["active_workflow"]["status"] == "awaiting_confirmation"
    assert "must-not-be-persisted" not in conversation_context_service.render_state(state)


def test_chat_route_and_model_history_receive_structured_workflow_state(
    client, db_session, monkeypatch
):
    from app.api import chat as chat_api

    client.post(
        "/api/auth/register",
        json={
            "username": "context_route_user",
            "email": "context_route@example.com",
            "password": "123456",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "context_route_user", "password": "123456"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    session_uuid = client.post(
        "/api/chat/sessions", headers=headers, json={"title": "context route"}
    ).json()["session_uuid"]
    session = (
        db_session.query(ChatSession)
        .filter(ChatSession.session_uuid == session_uuid)
        .one()
    )
    session.context_state = {
        "schema_version": 1,
        "active_agent": "dataset",
        "active_workflow": {
            "agent": "dataset",
            "purpose": "dataset.add_samples",
            "status": "awaiting_input",
        },
        "entities": {"dataset_id": 21},
        "known_values": {},
        "missing_fields": ["class_name"],
        "pending": {"form_id": "persisted-form"},
    }
    db_session.commit()
    captured = {}

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        async def aroute(self, message, **kwargs):
            captured["route"] = kwargs
            return RouteDecision.single(
                kwargs["active_workflow_agent"],
                "active_workflow",
                0.94,
                "structured context",
            )

        async def stream(self, message, attachment_paths, history, decision=None):
            captured["history"] = history
            yield decision.event()
            yield {"type": "text_chunk", "agent": decision.agent, "content": "继续处理数据集"}

    monkeypatch.setattr(chat_api, "MultiAgentOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(chat_api.settings, "DEEPSEEK_API_KEY", "test-key")
    response = client.post(
        "/api/chat/stream",
        headers=headers,
        json={
            "message": "继续刚才的操作",
            "attachment_paths": [],
            "attachment_names": [],
            "session_uuid": session_uuid,
        },
    )

    assert response.status_code == 200
    assert captured["route"]["active_workflow_agent"] == "dataset"
    assert captured["route"]["preferred_agent"] == "dataset"
    assert any(
        item["role"] == "system"
        and "dataset.add_samples" in item["content"]
        and "dataset_id" in item["content"]
        for item in captured["history"]
    )


def test_chat_persists_real_usage_across_multiple_model_runs(
    client, db_session, monkeypatch
):
    from app.api import chat as chat_api

    client.post(
        "/api/auth/register",
        json={
            "username": "usage_user",
            "email": "usage_user@example.com",
            "password": "123456",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "usage_user", "password": "123456"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    session_uuid = client.post(
        "/api/chat/sessions", headers=headers, json={"title": "usage"}
    ).json()["session_uuid"]

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        async def aroute(self, message, **kwargs):
            return RouteDecision.single("knowledge", "test", 1.0, "usage test")

        async def stream(self, message, attachment_paths, history, decision=None):
            yield decision.event()
            yield {
                "type": "model_usage",
                "agent": "knowledge",
                "run_id": "run-1",
                "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
            }
            yield {
                "type": "model_usage",
                "agent": "knowledge",
                "run_id": "run-2",
                "usage": {"input_tokens": 8, "output_tokens": 3, "total_tokens": 11},
            }
            yield {"type": "text_chunk", "agent": "knowledge", "content": "完成"}

    monkeypatch.setattr(chat_api, "MultiAgentOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(chat_api.settings, "DEEPSEEK_API_KEY", "test-key")
    response = client.post(
        "/api/chat/stream",
        headers=headers,
        json={
            "message": "记录 token",
            "attachment_paths": [],
            "attachment_names": [],
            "session_uuid": session_uuid,
        },
    )
    assert response.status_code == 200
    db_session.expire_all()
    session = (
        db_session.query(ChatSession)
        .filter(ChatSession.session_uuid == session_uuid)
        .one()
    )
    assistant = [item for item in session.messages if item.role == "assistant"][-1]
    assert assistant.tokens_used == 23
    assert assistant.tool_calls["model_usage"] == {
        "input_tokens": 18,
        "output_tokens": 5,
        "total_tokens": 23,
    }
    assert assistant.tool_calls["context_tokens"] > 0
