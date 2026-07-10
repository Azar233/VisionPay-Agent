from types import SimpleNamespace


def _auth_headers(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "training_api_user",
            "email": "training_api_user@example.com",
            "password": "123456",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={"username": "training_api_user", "password": "123456"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_scene(client, headers):
    response = client.post(
        "/api/training/start",
        headers=headers,
        json={
            "scene_id": 9999,
            "model_name": "yolov11n",
            "epochs": 5,
            "batch_size": 2,
            "device": "cpu",
        },
    )
    assert response.status_code == 404


def test_training_routes_require_auth(client):
    response = client.get("/api/training/tasks")
    assert response.status_code == 401


def test_training_tasks_empty_for_new_user(client):
    headers = _auth_headers(client)
    response = client.get("/api/training/tasks", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"total": 0, "items": []}


def test_training_start_scene_not_found(client):
    headers = _auth_headers(client)
    _create_scene(client, headers)


def test_training_start_uses_vision_pay_dataset(client, db_session, monkeypatch):
    from app.api import training as training_api
    from app.entity.db_models import DetectionScene, User

    headers = _auth_headers(client)
    user = db_session.query(User).filter_by(username="training_api_user").first()
    scene = DetectionScene(
        name="vision_pay",
        display_name="Vision Pay",
        description="Vision Pay training scene",
        category="retail",
        class_names=["product"],
        created_by=user.id,
    )
    db_session.add(scene)
    db_session.commit()
    db_session.refresh(scene)

    captured = {}

    def fake_start_training(db, user_id, scene_id, config):
        captured.update(config)
        return SimpleNamespace(
            id=123,
            task_uuid="abc123ef",
            status="pending",
            model_name=config["model_name"],
            epochs=config["epochs"],
            dataset_size=500,
        )

    monkeypatch.setattr(training_api.training_service, "start_training", fake_start_training)

    response = client.post(
        "/api/training/start",
        headers=headers,
        json={
            "scene_id": scene.id,
            "model_name": "yolov11n",
            "epochs": 5,
            "batch_size": 2,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["task_uuid"] == "abc123ef"
    assert data["model_name"] == "yolov11n"
    assert data["epochs"] == 5
    assert captured["data_yaml"].endswith("datasets\\vision_pay\\data.yaml") or captured[
        "data_yaml"
    ].endswith("datasets/vision_pay/data.yaml")
