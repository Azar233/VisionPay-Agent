"""Day 10 dashboard, history, and account settings integration tests."""

from io import BytesIO
from datetime import datetime, timedelta

from PIL import Image

from app.entity.db_models import (
    ChatMessage,
    ChatSession,
    DetectionResult,
    DetectionScene,
    DetectionTask,
    ModelVersion,
    User,
)


def auth_headers(client, username="day10_user"):
    client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "123456"},
    )
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "123456"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def seed_scene(db_session, owner: User, name="visionpay_day10"):
    scene = DetectionScene(
        name=name,
        display_name="VisionPay 零售识别",
        category="retail",
        class_names=["cola", "chips"],
        created_by=owner.id,
    )
    db_session.add(scene)
    db_session.commit()
    db_session.refresh(scene)
    return scene


def seed_task(db_session, owner, scene, **overrides):
    values = {
        "user_id": owner.id,
        "scene_id": scene.id,
        "task_type": "single",
        "status": "completed",
        "total_images": 1,
        "total_objects": 2,
        "total_inference_time": 20,
        "created_at": datetime.now(),
        "completed_at": datetime.now(),
    }
    values.update(overrides)
    task = DetectionTask(**values)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_day10_routes_require_auth(client):
    assert client.get("/api/dashboard/statistics").status_code == 401
    assert client.get("/api/dashboard/model-usage").status_code == 401
    assert client.get("/api/history/tasks").status_code == 401
    assert client.put("/api/user/profile", json={"phone": "123"}).status_code == 401


def test_dashboard_aggregates_only_current_user(client, db_session):
    headers = auth_headers(client)
    owner = db_session.query(User).filter_by(username="day10_user").one()
    scene = seed_scene(db_session, owner)
    first = seed_task(db_session, owner, scene, total_images=2, total_objects=3, total_inference_time=40)
    seed_task(db_session, owner, scene, task_type="video", total_images=4, total_objects=5, total_inference_time=80)
    db_session.add_all(
        [
            DetectionResult(task_id=first.id, image_path="a.jpg", class_name="cola", class_name_cn="可乐", class_id=0, confidence=.9, bbox=[1, 2, 3, 4]),
            DetectionResult(task_id=first.id, image_path="a.jpg", class_name="chips", class_name_cn="薯片", class_id=1, confidence=.8, bbox=[2, 3, 4, 5]),
        ]
    )
    other_headers = auth_headers(client, "day10_other")
    other = db_session.query(User).filter_by(username="day10_other").one()
    seed_task(db_session, other, scene, total_images=100, total_objects=100, total_inference_time=100)
    db_session.commit()

    stats = client.get("/api/dashboard/statistics?days=30", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["total_tasks"] == 2
    assert stats.json()["total_images"] == 6
    assert stats.json()["total_objects"] == 8
    assert stats.json()["avg_inference_time"] == 20.0
    assert client.get("/api/dashboard/statistics?days=30", headers=other_headers).json()["total_tasks"] == 1

    class_dist = client.get("/api/dashboard/class-dist?days=30", headers=headers).json()
    assert class_dist["distribution"] == [{"name": "可乐", "value": 1}, {"name": "薯片", "value": 1}]
    type_dist = client.get("/api/dashboard/type-dist?days=30", headers=headers).json()
    assert {item["name"] for item in type_dist["distribution"]} == {"单图识别", "视频识别"}
    assert len(client.get("/api/dashboard/trend?days=7", headers=headers).json()["trend"]) == 7
    hourly = client.get("/api/dashboard/trend?hours=48", headers=headers).json()
    assert hourly["granularity"] == "hour"
    assert len(hourly["trend"]) == 48
    two_hour = client.get(
        "/api/dashboard/trend?hours=24&bucket_hours=2", headers=headers
    ).json()
    assert two_hour["bucket_hours"] == 2
    assert len(two_hour["trend"]) == 12


def test_dashboard_model_usage_is_aggregated_and_user_scoped(client, db_session):
    headers = auth_headers(client)
    owner = db_session.query(User).filter_by(username="day10_user").one()
    session = ChatSession(user_id=owner.id, session_uuid="dashboard-agent-session", title="数据集操作")
    db_session.add(session)
    db_session.flush()
    db_session.add_all(
        [
            ChatMessage(
                session_id=session.id,
                role="assistant",
                content="已完成查询",
                agent_used="dataset",
                tokens_used=100,
                latency_ms=1200,
                tool_calls={
                    "model_name": "deepseek-chat",
                    "model_run_count": 2,
                    "model_usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
                },
                created_at=datetime.now() - timedelta(minutes=2),
            ),
            ChatMessage(
                session_id=session.id,
                role="assistant",
                content="Agent 处理失败: timeout",
                agent_used="knowledge",
                tokens_used=20,
                latency_ms=800,
                tool_calls={
                    "model_name": "deepseek-chat",
                    "model_usage": {"input_tokens": 15, "output_tokens": 5, "total_tokens": 20},
                },
                created_at=datetime.now() - timedelta(minutes=1),
            ),
        ]
    )
    db_session.commit()

    other_headers = auth_headers(client, "day10_model_other")
    other = db_session.query(User).filter_by(username="day10_model_other").one()
    other_session = ChatSession(user_id=other.id, session_uuid="other-dashboard-agent-session")
    db_session.add(other_session)
    db_session.flush()
    db_session.add(
        ChatMessage(
            session_id=other_session.id,
            role="assistant",
            content="不应出现在当前用户看板",
            agent_used="training",
            tokens_used=999,
        )
    )
    db_session.commit()

    response = client.get("/api/dashboard/model-usage?days=30&limit=1", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == {
        "total_calls": 3,
        "total_turns": 2,
        "total_tokens": 120,
        "input_tokens": 95,
        "output_tokens": 25,
        "avg_latency_ms": 1000,
        "success_rate": 50.0,
    }
    assert {item["agent"]: item["value"] for item in data["agent_distribution"]} == {
        "dataset": 2,
        "knowledge": 1,
    }
    assert len(data["recent"]) == 1
    assert data["recent"][0]["agent"] == "knowledge"
    assert len(data["trend"]) == 30
    hourly = client.get(
        "/api/dashboard/model-usage?hours=24&bucket_hours=2", headers=headers
    ).json()
    assert hourly["granularity"] == "hour"
    assert hourly["bucket_hours"] == 2
    assert len(hourly["trend"]) == 12
    assert client.get("/api/dashboard/model-usage", headers=other_headers).json()["summary"]["total_tokens"] == 999


def test_history_filters_details_deletes_and_isolates(client, db_session):
    headers = auth_headers(client)
    owner = db_session.query(User).filter_by(username="day10_user").one()
    scene = seed_scene(db_session, owner)
    completed = seed_task(db_session, owner, scene, task_type="zip")
    seed_task(
        db_session,
        owner,
        scene,
        task_type="video",
        status="failed",
        created_at=datetime.now() - timedelta(days=10),
        error_message="bad video",
    )
    db_session.add(
        DetectionResult(task_id=completed.id, image_path="zip/a.jpg", class_name="cola", class_id=0, confidence=.93, bbox=[1, 2, 3, 4])
    )
    db_session.commit()

    listing = client.get("/api/history/tasks?task_type=zip&status=completed", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["avg_inference_time"] == 20.0

    detail = client.get(f"/api/history/tasks/{completed.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["class_counts"] == {"cola": 1}
    assert detail.json()["results"][0]["confidence"] == .93

    other_headers = auth_headers(client, "history_other")
    assert client.get(f"/api/history/tasks/{completed.id}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/history/tasks/{completed.id}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/history/tasks/{completed.id}", headers=headers).status_code == 200
    assert db_session.query(DetectionResult).filter_by(task_id=completed.id).count() == 0


def test_unified_history_lists_agent_calls_and_model_lifecycle(client, db_session):
    headers = auth_headers(client, "history_center_user")
    owner = db_session.query(User).filter_by(username="history_center_user").one()
    scene = seed_scene(db_session, owner, name="history_center_scene")
    session = ChatSession(
        user_id=owner.id,
        session_uuid="history-center-session",
        title="检查数据集",
        message_count=2,
        last_message_at=datetime.now(),
    )
    db_session.add(session)
    db_session.flush()
    db_session.add_all(
        [
            ChatMessage(
                session_id=session.id,
                role="user",
                content="查看全部数据集版本",
                agent_used="dataset",
                tool_calls={"attachments": [{"name": "note.png"}]},
            ),
            ChatMessage(
                session_id=session.id,
                role="assistant",
                content="当前共有两个数据集版本。",
                agent_used="dataset",
                tool_calls={"tool": "list_dataset_versions"},
                latency_ms=125,
            ),
        ]
    )
    model = ModelVersion(
        scene_id=scene.id,
        version="history-model-v1",
        model_name="History model",
        model_type="yolov11n",
        status="active",
        model_path="missing-history-model.pt",
        is_default=False,
        description="历史中心测试模型",
    )
    db_session.add(model)
    db_session.commit()
    db_session.refresh(model)

    agent_listing = client.get(
        "/api/history/agent-calls?agent=dataset&keyword=数据集",
        headers=headers,
    )
    assert agent_listing.status_code == 200, agent_listing.text
    assert agent_listing.json()["total"] == 1
    activity = agent_listing.json()["items"][0]
    assert activity["agent_label"] == "Dataset Agent"
    assert activity["action_label"] == "查询数据集版本"
    assert activity["user_request"] == "查看全部数据集版本"
    assert activity["attachment_count"] == 1
    assert client.get(
        f"/api/history/agent-calls/{activity['id']}", headers=headers
    ).status_code == 200

    other_headers = auth_headers(client, "history_center_other")
    assert client.get(
        f"/api/history/agent-calls/{activity['id']}", headers=other_headers
    ).status_code == 404

    model_listing = client.get(
        "/api/history/models?status=active&keyword=history-model-v1",
        headers=headers,
    )
    assert model_listing.status_code == 200, model_listing.text
    assert model_listing.json()["total"] == 1
    assert model_listing.json()["items"][0]["origin"] == "imported"

    archive = client.post(
        f"/api/training/model-versions/{model.id}/archive",
        headers=headers,
    )
    assert archive.status_code == 200, archive.text
    timeline = client.get(f"/api/history/models/{model.id}", headers=headers)
    assert timeline.status_code == 200, timeline.text
    assert [event["action"] for event in timeline.json()["events"]] == [
        "archive",
        "created",
    ]
    assert timeline.json()["events"][0]["actor"] == "history_center_user"

    overview = client.get("/api/history/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["agent_calls"] == 1
    assert overview.json()["models"] == 1


def test_profile_and_password_settings(client):
    headers = auth_headers(client)
    updated = client.put(
        "/api/user/profile",
        headers=headers,
        json={"email": "updated@example.com", "phone": "13800138000"},
    )
    assert updated.status_code == 200
    assert updated.json()["user"]["phone"] == "13800138000"
    assert client.get("/api/auth/me", headers=headers).json()["email"] == "updated@example.com"

    wrong = client.put(
        "/api/user/password",
        headers=headers,
        json={"old_password": "bad-password", "new_password": "654321"},
    )
    assert wrong.status_code == 400
    changed = client.put(
        "/api/user/password",
        headers=headers,
        json={"old_password": "123456", "new_password": "654321"},
    )
    assert changed.status_code == 200
    assert client.post("/api/auth/login", json={"username": "day10_user", "password": "654321"}).status_code == 200


def test_avatar_upload_updates_current_user(client):
    headers = auth_headers(client, "avatar_user")
    buffer = BytesIO()
    Image.new("RGB", (1, 1), color=(0, 113, 227)).save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    uploaded = client.post(
        "/api/user/avatar",
        headers=headers,
        files={"file": ("avatar.png", png_bytes, "image/png")},
    )

    assert uploaded.status_code == 200
    avatar_url = uploaded.json()["user"]["avatar"]
    assert avatar_url.startswith("/media/avatars/user_")
    assert client.get("/api/auth/me", headers=headers).json()["avatar"] == avatar_url
    assert client.get(avatar_url).status_code == 200


def test_user_directory_is_admin_only(client, db_session):
    headers = auth_headers(client)
    assert client.get("/api/user/list", headers=headers).status_code == 403

    user = db_session.query(User).filter_by(username="day10_user").one()
    user.is_superuser = True
    db_session.commit()
    listing = client.get("/api/user/list?keyword=day10", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["items"][0]["username"] == "day10_user"
