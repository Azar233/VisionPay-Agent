from io import BytesIO
import asyncio
from pathlib import Path
import threading

import pytest
from PIL import Image
from sqlalchemy.orm import sessionmaker

from app.entity.db_models import DetectionScene, DetectionTask, ModelVersion, ProductPrice, User
from app.services.detection_service import DetectionService, DetectionServiceError


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


def test_camera_options_validate_mode_and_bounds(monkeypatch):
    import torch

    from app.api.detection import _camera_options

    # 模拟无 CUDA：默认回退到 cpu，显式请求 cuda/gpu 也自动降级为 cpu。
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert _camera_options({"mode": "cpu", "conf": 0.3, "iou": 0.5, "scene_id": 2}) == {
        "mode": "cpu",
        "conf": 0.3,
        "iou": 0.5,
        "scene_id": 2,
        "camera_url": None,
        "warning": None,
    }
    assert _camera_options({"conf": 0.3, "iou": 0.5})["mode"] == "cpu"
    assert _camera_options({"camera_url": "http://10.172.52.70:8080"})["camera_url"] == "http://10.172.52.70:8080/video"
    gpu_fallback = _camera_options({"mode": "gpu"})
    assert gpu_fallback["mode"] == "cpu"
    assert "CUDA" in (gpu_fallback.get("warning") or "")
    cuda_fallback = _camera_options({"mode": "cuda"})
    assert cuda_fallback["mode"] == "cpu"
    assert "CUDA" in (cuda_fallback.get("warning") or "")

    # 模拟有 CUDA：默认使用 cuda，允许 gpu/cuda 请求。
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert _camera_options({"mode": "cuda", "conf": 0.3, "iou": 0.5, "scene_id": 2})["mode"] == "cuda"
    assert _camera_options({"mode": "gpu", "conf": 0.3, "iou": 0.5})["mode"] == "cuda"
    assert _camera_options({"conf": 0.3, "iou": 0.5})["mode"] == "cuda"

    with pytest.raises(ValueError, match="0.05"):
        _camera_options({"conf": 0.01})
    with pytest.raises(ValueError, match="局域网"):
        _camera_options({"camera_url": "http://8.8.8.8:8080"})


def test_resolve_model_prefers_selected_registry_version(
    db_session,
    monkeypatch,
    tmp_path,
):
    from app.config.settings import settings
    from app.services import detection_service as detection_module

    scene = DetectionScene(
        name="selected_model_scene",
        display_name="Selected Model Scene",
        category="retail",
        class_names=["product"],
    )
    db_session.add(scene)
    db_session.flush()
    selected_weights = tmp_path / "selected" / "best.pt"
    selected_weights.parent.mkdir(parents=True)
    selected_weights.write_bytes(b"selected")
    environment_weights = tmp_path / "environment-best.pt"
    environment_weights.write_bytes(b"environment")
    selected = ModelVersion(
        scene_id=scene.id,
        version="训练-selected",
        model_name="selected",
        model_type="yolov11n",
        status="active",
        model_path=str(selected_weights),
        is_default=True,
    )
    db_session.add(selected)
    db_session.commit()
    db_session.refresh(selected)

    monkeypatch.setattr(
        detection_module.model_version_service,
        "ensure_builtin",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(settings, "DETECTION_MODEL_PATH", str(environment_weights))

    resolved_path, model_version_id = DetectionService()._resolve_model(db_session, scene.id)

    assert resolved_path == selected_weights.resolve()
    assert model_version_id == selected.id

    selected_weights.unlink()
    with pytest.raises(DetectionServiceError, match="当前检测模型.*文件不存在"):
        DetectionService()._resolve_model(db_session, scene.id)


def test_latest_camera_frame_discards_buffered_frames():
    from app.api.detection import _LatestCameraFrame

    class BurstCapture:
        def __init__(self):
            self.index = 0
            self.drained = threading.Event()
            self.released = threading.Event()

        def read(self):
            if self.index < 3:
                self.index += 1
                if self.index == 3:
                    self.drained.set()
                return True, self.index
            self.released.wait(timeout=2)
            return False, None

        def release(self):
            self.released.set()

    capture = BurstCapture()
    reader = _LatestCameraFrame(capture)
    reader.start()
    assert capture.drained.wait(timeout=1)
    sequence, frame, captured_at = reader.latest(0, timeout=1)
    reader.stop()

    assert sequence == 3
    assert frame == 3
    assert captured_at > 0


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
            "detections": [],
            "inference_time_ms": 12.5,
        },
    )
    monkeypatch.setattr(
        detection_api.detection_service,
        "finalize_realtime_frame",
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
        assert configured["low_latency"] is True
        result = websocket.receive_json()
        assert result["type"] == "result"
        assert result["annotated_frame"] == "ZmFrZQ=="
        assert result["frame_count"] == 1
        assert result["pipeline_latency_ms"] >= 0
        websocket.send_json({"type": "close"})


def test_camera_websocket_does_not_claim_session_for_invalid_config(client):
    from app.api import detection as detection_api

    with client.websocket_connect(
        "/api/detection/camera",
        headers={"origin": "http://localhost:5173"},
    ) as websocket:
        websocket.send_json({"type": "invalid"})
        response = websocket.receive_json()
        assert response["type"] == "error"

    assert detection_api._CAMERA_ACTIVE_SESSION is None


@pytest.mark.asyncio
async def test_new_camera_session_replaces_previous_session():
    from app.api import detection as detection_api

    first = await detection_api._claim_camera_session()
    claim_second = asyncio.create_task(detection_api._claim_camera_session())
    await asyncio.wait_for(first["stopped"].wait(), timeout=1)
    first["closed"].set()
    second = await asyncio.wait_for(claim_second, timeout=1)

    assert first["replaced"] is True
    assert detection_api._CAMERA_ACTIVE_SESSION is second
    detection_api._release_camera_session(second)
    assert detection_api._CAMERA_ACTIVE_SESSION is None


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
        "product_id": None,
        "product_key": None,
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


def test_chat_routes_require_auth(client):
    assert client.get("/api/chat/status").status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/detection/single"),
        ("post", "/api/detection/batch"),
        ("post", "/api/detection/zip"),
        ("post", "/api/detection/video"),
        ("get", "/api/detection/video/status/1"),
    ],
)
def test_removed_detection_workbench_routes_are_not_exposed(client, method, path):
    assert getattr(client, method)(path).status_code == 404


def test_agent_status_does_not_expose_api_key(client):
    response = client.get("/api/chat/status", headers=_auth_headers(client))
    assert response.status_code == 200
    assert set(response.json()) == {
        "configured", "provider", "model", "multi_agent", "agents", "embedding"
    }


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
    monkeypatch.setattr(chat_api.settings, "DEEPSEEK_API_KEY", "test-key")
    response = client.post(
        "/api/chat/stream",
        headers=headers,
        json={
            "message": "检测测试流式输出",
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


def test_chat_form_submission_is_validated_and_returns_to_source_agent(
    client, db_session, monkeypatch
):
    from app.api import chat as chat_api
    from app.entity.db_models import ChatMessage, ChatSession

    headers = _auth_headers(client)
    session_uuid = client.post(
        "/api/chat/sessions", headers=headers, json={"title": "训练参数"}
    ).json()["session_uuid"]
    session = db_session.query(ChatSession).filter(
        ChatSession.session_uuid == session_uuid
    ).one()
    form = {
        "form_type": "dynamic_parameters",
        "schema_version": 1,
        "form_id": "training-form-1",
        "agent": "training",
        "title": "补充训练参数",
        "purpose": "training.start",
        "known_values": {"dataset_version_id": 2},
        "fields": [
            {
                "name": "epochs",
                "label": "训练轮数",
                "type": "integer",
                "required": True,
                "minimum": 1,
            }
        ],
    }
    db_session.add(
        ChatMessage(
            session_id=session.id,
            role="assistant",
            content="请补充训练参数",
            agent_used="training",
            tool_calls={"input_form": form},
        )
    )
    db_session.commit()

    captured = {}

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def route(self, *args, **kwargs):
            raise AssertionError("结构化表单提交不应重新执行普通路由")

        async def stream(self, message, attachment_paths, history, decision=None):
            captured["message"] = message
            captured["decision"] = decision
            yield decision.event()
            yield {"type": "text_chunk", "agent": decision.agent, "content": "已接收参数"}

    monkeypatch.setattr(chat_api, "MultiAgentOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(chat_api.settings, "DEEPSEEK_API_KEY", "test-key")
    payload = {
        "message": "已填写训练参数：训练轮数 20",
        "attachment_paths": [],
        "attachment_names": [],
        "session_uuid": session_uuid,
        "form_submission": {
            "form_id": "training-form-1",
            "values": {"epochs": "20"},
        },
    }

    response = client.post("/api/chat/stream", headers=headers, json=payload)

    assert response.status_code == 200
    assert captured["decision"].agent == "training"
    assert captured["decision"].method == "form_submission"
    assert '"epochs": 20' in captured["message"]
    repeated = client.post("/api/chat/stream", headers=headers, json=payload)
    assert repeated.status_code == 409
