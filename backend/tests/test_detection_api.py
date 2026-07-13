from io import BytesIO

from PIL import Image


def _auth_headers(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "detection_user",
            "email": "detection_user@example.com",
            "password": "123456",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "detection_user", "password": "123456"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _image_bytes():
    stream = BytesIO()
    Image.new("RGB", (24, 24), color=(220, 40, 30)).save(stream, format="JPEG")
    return stream.getvalue()


def test_detection_and_chat_routes_require_auth(client):
    assert client.post("/api/detection/single").status_code == 401
    assert client.get("/api/chat/status").status_code == 401


def test_agent_status_does_not_expose_api_key(client):
    response = client.get("/api/chat/status", headers=_auth_headers(client))
    assert response.status_code == 200
    assert set(response.json()) == {"configured", "provider", "model"}


def test_single_detection_passes_user_and_parameters(client, monkeypatch):
    from app.api import detection as detection_api

    headers = _auth_headers(client)
    captured = {}

    def fake_detect(path, **kwargs):
        captured.update(kwargs)
        assert path.is_file()
        return {
            "task_id": 7,
            "source": "single",
            "scene": "Vision Pay",
            "model": "best.pt",
            "total_images": 1,
            "total_objects": 0,
            "total_inference_time_ms": 1.2,
            "class_counts": {},
            "items": [],
        }

    monkeypatch.setattr(detection_api.detection_service, "detect_single", fake_detect)
    response = client.post(
        "/api/detection/single",
        headers=headers,
        data={"scene_id": "3", "conf": "0.4", "iou": "0.5"},
        files={"file": ("checkout.jpg", _image_bytes(), "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["task_id"] == 7
    assert captured["scene_id"] == 3
    assert captured["conf"] == 0.4
    assert captured["iou"] == 0.5
    assert isinstance(captured["user_id"], int)


def test_detection_rejects_unsupported_upload(client):
    response = client.post(
        "/api/detection/single",
        headers=_auth_headers(client),
        files={"file": ("payload.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 415


def test_detection_conversation_crud(client):
    headers = _auth_headers(client)
    created = client.post(
        "/api/chat/sessions",
        headers=headers,
        json={"title": "新对话"},
    )
    assert created.status_code == 200
    session_uuid = created.json()["session_uuid"]

    saved = client.post(
        f"/api/chat/sessions/{session_uuid}/exchanges",
        headers=headers,
        json={
            "user_content": "识别商品",
            "assistant_content": "检测到 1 件商品",
            "files": [{"name": "checkout.jpg"}],
            "result": {"task_id": 8, "total_objects": 1, "items": []},
        },
    )
    assert saved.status_code == 200
    assert saved.json()["title"] == "识别商品"
    assert saved.json()["message_count"] == 2

    sessions = client.get("/api/chat/sessions", headers=headers)
    assert sessions.status_code == 200
    assert sessions.json()["items"][0]["session_uuid"] == session_uuid

    detail = client.get(f"/api/chat/sessions/{session_uuid}", headers=headers)
    assert detail.status_code == 200
    assert [message["role"] for message in detail.json()["messages"]] == [
        "user",
        "assistant",
    ]
    assert detail.json()["messages"][0]["files"] == [{"name": "checkout.jpg"}]
    assert detail.json()["messages"][1]["result"]["total_objects"] == 1

    deleted = client.delete(f"/api/chat/sessions/{session_uuid}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"/api/chat/sessions/{session_uuid}", headers=headers).status_code == 404


def test_detection_conversation_is_user_scoped(client):
    owner_headers = _auth_headers(client)
    session_uuid = client.post(
        "/api/chat/sessions", headers=owner_headers, json={"title": "私有对话"}
    ).json()["session_uuid"]

    client.post(
        "/api/auth/register",
        json={
            "username": "another_detection_user",
            "email": "another_detection_user@example.com",
            "password": "123456",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "another_detection_user", "password": "123456"},
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get(f"/api/chat/sessions/{session_uuid}", headers=other_headers).status_code == 404


def test_empty_draft_is_not_listed_until_first_message(client):
    headers = _auth_headers(client)
    created = client.post(
        "/api/chat/sessions", headers=headers, json={"title": "新对话"}
    )
    assert created.status_code == 200
    sessions = client.get("/api/chat/sessions", headers=headers)
    assert sessions.status_code == 200
    assert sessions.json() == {"items": []}


def test_chat_stream_emits_chunks_and_persists_full_reply(client, monkeypatch):
    from app.api import chat as chat_api

    headers = _auth_headers(client)
    session_uuid = client.post(
        "/api/chat/sessions", headers=headers, json={"title": "新对话"}
    ).json()["session_uuid"]

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        async def stream(self, message, attachment_paths, history):
            yield {"type": "text_chunk", "content": "你"}
            yield {"type": "text_chunk", "content": "好"}

    monkeypatch.setattr(chat_api, "DetectionAgent", FakeAgent)
    response = client.post(
        "/api/chat/stream",
        headers=headers,
        json={
            "message": "测试流式输出",
            "attachment_paths": [],
            "attachment_names": [],
            "session_uuid": session_uuid,
        },
    )
    assert response.status_code == 200
    assert '"content": "你"' in response.text
    assert '"content": "好"' in response.text
    assert "data: [DONE]" in response.text

    detail = client.get(f"/api/chat/sessions/{session_uuid}", headers=headers).json()
    assert detail["messages"][-1]["role"] == "assistant"
    assert detail["messages"][-1]["content"] == "你好"
