from types import SimpleNamespace

import pytest


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


def test_normalize_training_device_accepts_8_gpus():
    from app.training.training_service import _normalize_device

    assert _normalize_device("0-7") == "0,1,2,3,4,5,6,7"
    assert _normalize_device("0,1,2,3,4,5,6,7") == "0,1,2,3,4,5,6,7"


def test_trainer_epoch_values_use_epoch_average_and_current_validation_metrics():
    from app.training.training_service import _trainer_epoch_values

    trainer = SimpleNamespace(
        loss_names=["box_loss", "cls_loss", "dfl_loss"],
        tloss=[0.4, 1.2, 0.8],
        loss_items=[9.0, 9.0, 9.0],
        metrics={
            "metrics/precision(B)": 0.31,
            "metrics/recall(B)": 0.42,
            "metrics/mAP50(B)": 0.27,
            "metrics/mAP50-95(B)": 0.18,
        },
    )

    assert _trainer_epoch_values(trainer) == {
        "box_loss": 0.4,
        "cls_loss": 1.2,
        "dfl_loss": 0.8,
        "precision": 0.31,
        "recall": 0.42,
        "map50": 0.27,
        "map50_95": 0.18,
    }


def test_training_augment_kwargs_validate_supported_keys():
    from app.training.training_service import _training_augment_kwargs

    assert _training_augment_kwargs({"degrees": 180, "mixup": 0.1}) == {
        "degrees": 180,
        "mixup": 0.1,
    }
    with pytest.raises(ValueError, match="Unsupported augment_config keys"):
        _training_augment_kwargs({"degree": 180})


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
            "batch_size": 128,
            "device": "0,1,2,3,4,5,6,7",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["task_uuid"] == "abc123ef"
    assert data["model_name"] == "yolov11n"
    assert data["epochs"] == 5
    assert captured["batch_size"] == 128
    assert captured["device"] == "0,1,2,3,4,5,6,7"
    assert captured["data_yaml"].endswith("datasets\\vision_pay\\data.yaml") or captured[
        "data_yaml"
    ].endswith("datasets/vision_pay/data.yaml")


def test_training_start_uses_registered_dataset_version(
    client,
    db_session,
    monkeypatch,
    tmp_path,
):
    from app.api import training as training_api
    from app.entity.db_models import DatasetVersion, DetectionScene, User

    headers = _auth_headers(client)
    user = db_session.query(User).filter_by(username="training_api_user").first()
    scene = DetectionScene(
        name="registered_dataset_scene",
        display_name="Registered Dataset Scene",
        description="Versioned training scene",
        category="retail",
        class_names=["product"],
        created_by=user.id,
    )
    db_session.add(scene)
    db_session.flush()
    (tmp_path / "data.yaml").write_text(
        "path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnc: 1\nnames: [product]\n",
        encoding="utf-8",
    )
    dataset = DatasetVersion(
        scene_id=scene.id,
        version="v-cluster-1",
        name="Cluster Dataset",
        status="ready",
        is_current=True,
        storage_path=str(tmp_path),
        data_yaml_path="data.yaml",
        content_hash="sha256:registered",
        class_count=1,
        train_image_count=80,
        val_image_count=10,
        test_image_count=10,
        train_annotation_count=80,
        val_annotation_count=10,
        test_annotation_count=10,
        created_by=user.id,
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)

    captured = {}

    def fake_start_training(db, user_id, scene_id, config):
        captured.update(config)
        return SimpleNamespace(
            id=321,
            task_uuid="registered1",
            status="pending",
            model_name=config["model_name"],
            epochs=config["epochs"],
            dataset_size=config["dataset_size"],
            dataset_version_id=config["dataset_version_id"],
            dataset_version=SimpleNamespace(version=dataset.version),
        )

    monkeypatch.setattr(training_api.training_service, "start_training", fake_start_training)
    response = client.post(
        "/api/training/start",
        headers=headers,
        json={
            "scene_id": scene.id,
            "dataset_version_id": dataset.id,
            "model_name": "yolov11s",
            "epochs": 3,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    assert response.json()["dataset_version_id"] == dataset.id
    assert response.json()["dataset_version"] == "v-cluster-1"
    assert captured["dataset_content_hash"] == "sha256:registered"
    assert captured["dataset_size"] == 100
    assert captured["dataset_path"] == str(tmp_path.resolve())
    assert captured["data_yaml"] == str((tmp_path / "data.yaml").resolve())
