from io import BytesIO
import json
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.orm import sessionmaker

from app.entity.db_models import DetectionScene, DetectionTask, ProductPrice, User
from app.services.detection_service import DetectionService


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


def test_camera_options_are_cpu_only_and_bounded():
    from app.api.detection import _camera_options

    assert _camera_options({"mode": "cpu", "conf": 0.3, "iou": 0.5, "scene_id": 2}) == {
        "mode": "cpu",
        "conf": 0.3,
        "iou": 0.5,
        "scene_id": 2,
        "camera_url": None,
    }
    assert _camera_options({"camera_url": "http://10.172.52.70:8080"})["camera_url"] == "http://10.172.52.70:8080/video"
    with pytest.raises(ValueError, match="仅支持 cpu"):
        _camera_options({"mode": "gpu"})
    with pytest.raises(ValueError, match="0.05"):
        _camera_options({"conf": 0.01})
    with pytest.raises(ValueError, match="局域网"):
        _camera_options({"camera_url": "http://8.8.8.8:8080"})


def test_camera_websocket_returns_annotated_current_frame(client, monkeypatch):
    import cv2
    from app.api import detection as detection_api

    class FakeCapture:
        def isOpened(self):
            return True

        def set(self, *_args):
            return True

        def read(self):
            return True, object()

        def release(self):
            return None

    monkeypatch.setattr(detection_api, "configured_ip_webcam_url", lambda: "http://192.168.1.109:8080/video")
    monkeypatch.setattr(cv2, "VideoCapture", lambda *_args: FakeCapture())
    monkeypatch.setattr(
        detection_api.detection_service,
        "prepare_realtime_model",
        lambda **_kwargs: {"model": object(), "model_name": "best.pt", "scene": "Vision Pay"},
    )
    monkeypatch.setattr(
        detection_api.detection_service,
        "detect_realtime_frame",
        lambda *_args, **_kwargs: {
            "annotated_frame": "ZmFrZQ==",
            "detections": [],
            "object_count": 0,
            "class_counts": {},
            "inference_time_ms": 12.5,
            "price_summary": {"total_price": 0, "items": []},
        },
    )

    with client.websocket_connect(
        "/api/detection/camera",
        headers={"origin": "http://localhost:5173"},
    ) as websocket:
        websocket.send_json({"type": "config", "mode": "cpu"})
        configured = websocket.receive_json()
        assert configured["type"] == "config_ok"
        assert configured["model"] == "best.pt"
        result = websocket.receive_json()
        assert result["type"] == "result"
        assert result["annotated_frame"] == "ZmFrZQ=="
        assert result["frame_count"] == 1
        websocket.send_json({"type": "close"})


def test_price_summary_groups_detections_and_reports_missing_prices(db_session):
    db_session.add_all(
        [
            ProductPrice(
                category_id=1,
                sku_name="cola-330",
                name="可口可乐 330ml",
                barcode="690000000001",
                unit_price=3.35,
                currency="CNY",
            ),
            ProductPrice(category_id=2, name="赠品", unit_price=0, currency="CNY"),
        ]
    )
    db_session.commit()

    summary = DetectionService._calculate_total_price(
        db_session,
        [
            {"class_id": 0, "class_name": "1_puffed_food"},
            {"class_id": 0, "class_name": "1_puffed_food"},
            {"class_id": 1, "class_name": "2_gift"},
            {"class_id": 98, "class_name": "99_unknown"},
        ],
    )

    assert summary["total_price"] == 6.70
    assert summary["pricing_complete"] is False
    assert summary["missing_category_ids"] == [99]
    assert summary["priced_objects"] == 3
    assert summary["unpriced_objects"] == 1
    assert summary["items"][0] == {
        "class_id": 0,
        "category_id": 1,
        "class_name": "1_puffed_food",
        "sku_name": "cola-330",
        "name": "可口可乐 330ml",
        "barcode": "690000000001",
        "count": 2,
        "unit_price": 3.35,
        "subtotal": 6.70,
        "currency": "CNY",
        "has_price": True,
    }
    assert summary["items"][1]["has_price"] is True
    assert summary["items"][2]["has_price"] is False


def test_empty_price_summary_is_complete(db_session):
    assert DetectionService._calculate_total_price(db_session, []) == {
        "total_price": 0.0,
        "currency": "CNY",
        "items": [],
        "pricing_complete": True,
        "missing_category_ids": [],
        "priced_objects": 0,
        "unpriced_objects": 0,
    }


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


def test_video_detection_rejects_non_video_upload(client):
    response = client.post(
        "/api/detection/video",
        headers=_auth_headers(client),
        files={"file": ("checkout.jpg", _image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 415


def test_video_detection_caps_requested_key_frames(client):
    response = client.post(
        "/api/detection/video",
        headers=_auth_headers(client),
        data={"max_frames": "51"},
        files={"file": ("checkout.mp4", b"fake-video", "video/mp4")},
    )
    assert response.status_code == 422


def test_video_detection_creates_background_task(client, monkeypatch):
    from app.api import detection as detection_api

    headers = _auth_headers(client)
    captured = {}

    monkeypatch.setattr(
        detection_api.detection_service,
        "create_video_task",
        lambda **_kwargs: {"task_id": 123, "scene_id": 7, "scene": "Vision Pay"},
    )
    monkeypatch.setattr(detection_api.video_task_store, "set", lambda *_args: None)

    def fake_run(**kwargs):
        captured.update(kwargs)
        kwargs["path"].unlink(missing_ok=True)

    monkeypatch.setattr(detection_api, "_run_video_detection", fake_run)
    response = client.post(
        "/api/detection/video",
        headers=headers,
        data={
            "scene_id": "7",
            "conf": "0.35",
            "iou": "0.55",
            "frame_sample_rate": "8",
            "max_frames": "40",
        },
        files={"file": ("checkout.mp4", b"fake-video", "video/mp4")},
    )

    assert response.status_code == 200
    assert response.json()["task_id"] == 123
    assert captured["task_id"] == 123
    assert captured["scene_id"] == 7
    assert captured["conf"] == 0.35
    assert captured["iou"] == 0.55
    assert captured["frame_sample_rate"] == 8
    assert captured["max_frames"] == 40
    assert isinstance(captured["user_id"], int)


def _video_task_for_user(db_session, username, *, status="processing"):
    user = db_session.query(User).filter_by(username=username).first()
    task = DetectionTask(
        user_id=user.id,
        scene_id=1,
        task_type="video",
        status=status,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_video_status_is_user_scoped(client, db_session, monkeypatch):
    from app.api import detection as detection_api

    owner_headers = _auth_headers(client)
    task = _video_task_for_user(db_session, "detection_user")
    monkeypatch.setattr(
        detection_api.video_task_store,
        "get",
        lambda _task_id: {"status": "processing", "progress": 42, "message": "processing"},
    )

    client.post(
        "/api/auth/register",
        json={
            "username": "video_other_user",
            "email": "video_other_user@example.com",
            "password": "123456",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "video_other_user", "password": "123456"},
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get(f"/api/detection/video/status/{task.id}", headers=owner_headers).status_code == 200
    assert client.get(f"/api/detection/video/status/{task.id}", headers=other_headers).status_code == 404


def test_video_status_reads_completed_result_file(client, db_session, monkeypatch, tmp_path):
    from app.api import detection as detection_api

    headers = _auth_headers(client)
    task = _video_task_for_user(db_session, "detection_user", status="completed")
    result = {"task_id": task.id, "source": "video", "processed_frames": 2, "items": []}
    result_path = tmp_path / "video-result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    monkeypatch.setattr(
        detection_api.video_task_store,
        "get",
        lambda _task_id: {
            "status": "completed",
            "progress": 100,
            "message": "completed",
            "result_path": str(result_path),
        },
    )

    response = client.get(f"/api/detection/video/status/{task.id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["result"] == result


def test_video_detection_samples_uniform_key_frames(db_session, monkeypatch, tmp_path):
    import cv2
    from app.services import detection_service as detection_module

    user = User(username="video_service_user", email="video_service_user@example.com", hashed_password="test")
    db_session.add(user)
    db_session.flush()
    scene = DetectionScene(
        name="video_test_scene",
        display_name="Video Test",
        category="retail",
        class_names=["product"],
        created_by=user.id,
    )
    db_session.add(scene)
    db_session.flush()
    task = DetectionTask(
        user_id=user.id,
        scene_id=scene.id,
        task_type="video",
        status="pending",
    )
    db_session.add(task)
    db_session.commit()
    task_id, user_id, scene_id = task.id, user.id, scene.id

    sampled_indices = []

    class FakeCapture:
        def isOpened(self):
            return True

        def get(self, prop):
            return {
                cv2.CAP_PROP_FRAME_COUNT: 260,
                cv2.CAP_PROP_FPS: 25,
                cv2.CAP_PROP_FRAME_WIDTH: 1280,
                cv2.CAP_PROP_FRAME_HEIGHT: 720,
            }.get(prop, 0)

        def set(self, prop, value):
            if prop == cv2.CAP_PROP_POS_FRAMES:
                sampled_indices.append(int(value))
            return True

        def read(self):
            return True, object()

        def release(self):
            return None

    class FakeModel:
        def predict(self, **_kwargs):
            return [object()]

    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"fake-video")
    service = DetectionService()
    progress = []
    video_test_session = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_session.get_bind(),
    )
    monkeypatch.setattr(detection_module, "SessionLocal", video_test_session)
    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: FakeCapture())
    monkeypatch.setattr(service, "_resolve_model", lambda *_args: (Path("best.pt"), None))
    monkeypatch.setattr(service, "_load_model", lambda _path: FakeModel())
    monkeypatch.setattr(
        service,
        "_serialize_prediction",
        lambda _prediction, frame_path: {
            "filename": frame_path.name,
            "image_width": 1280,
            "image_height": 720,
            "object_count": 0,
            "class_counts": {},
            "detections": [],
            "inference_time_ms": 1.0,
            "annotated_image": "data:image/jpeg;base64,ZmFrZQ==",
        },
    )

    result = service.detect_video(
        video_path,
        task_id=task_id,
        user_id=user_id,
        scene_id=scene_id,
        frame_sample_rate=5,
        max_frames=10,
        progress_callback=lambda value, message: progress.append((value, message)),
    )

    assert sampled_indices == list(range(0, 260, 26))
    assert result["processed_frames"] == 10
    assert result["frame_sample_rate"] == 26
    assert result["duration_seconds"] == 10.4
    assert result["object_count_mode"] == "sampled_detections"
    assert progress[-1][0] == 100


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
