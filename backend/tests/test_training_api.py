from types import SimpleNamespace
from pathlib import Path

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
        status="pending_train",
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


def test_import_local_results_csv_creates_completed_task(client, db_session, monkeypatch, tmp_path):
    import app.training.training_service as training_module
    from app.api import training as training_api
    from app.entity.db_models import DatasetVersion, DetectionScene, TrainingMetric, User

    headers = _auth_headers(client)
    user = db_session.query(User).filter_by(username="training_api_user").first()
    scene = DetectionScene(
        name="local_results_scene",
        display_name="Local Results Scene",
        category="retail",
        class_names=["product"],
        created_by=user.id,
    )
    db_session.add(scene)
    db_session.flush()
    dataset_path = tmp_path / "dataset"
    dataset_path.mkdir()
    dataset = DatasetVersion(
        scene_id=scene.id,
        version="local-results-v1",
        name="Local Results Dataset",
        status="pending_train",
        is_current=True,
        storage_path=str(dataset_path),
        data_yaml_path="data.yaml",
        content_hash="sha256:local-results",
        created_by=user.id,
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)

    (tmp_path / "results.csv").write_text(
        "epoch,train/box_loss,train/cls_loss,train/dfl_loss,metrics/precision(B),"
        "metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B),lr/pg0\n"
        "1,0.7,1.2,0.9,0.5,0.6,0.7,0.4,0.01\n"
        "2,0.6,1.0,0.8,0.6,0.7,0.8,0.5,0.009\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(training_api, "BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(training_module, "PROJECT_ROOT", tmp_path)

    response = client.post(
        "/api/training/import-local-results",
        headers=headers,
        json={
            "scene_id": scene.id,
            "dataset_version_id": dataset.id,
            "task_uuid": "ppt_curve",
            "model_name": "yolov11n",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["metrics_imported"] == 2
    assert data["task"]["task_uuid"] == "ppt_curve"
    assert data["task"]["status"] == "completed"
    assert data["task"]["progress"] == 100
    assert (tmp_path / "runs" / "train" / "task_ppt_curve" / "results.csv").exists()

    metric = (
        db_session.query(TrainingMetric)
        .filter(TrainingMetric.task_id == data["task"]["id"], TrainingMetric.epoch == 2)
        .first()
    )
    assert metric.map50 == pytest.approx(0.8)


def test_model_versions_register_builtin_best_pt(
    client,
    db_session,
    monkeypatch,
    tmp_path,
):
    from app.entity.db_models import DetectionScene, ModelVersion, User
    from app.services.model_version_service import ModelVersionService

    headers = _auth_headers(client)
    user = db_session.query(User).filter_by(username="training_api_user").first()
    scene = DetectionScene(
        name="builtin_model_scene",
        display_name="Builtin Model Scene",
        category="retail",
        class_names=["product"],
        created_by=user.id,
    )
    db_session.add(scene)
    db_session.commit()
    db_session.refresh(scene)

    builtin_weights = tmp_path / "best.pt"
    builtin_weights.write_bytes(b"builtin-model")
    monkeypatch.setattr(
        ModelVersionService,
        "_builtin_path",
        staticmethod(lambda: builtin_weights.resolve()),
    )

    response = client.get(
        "/api/training/model-versions",
        headers=headers,
        params={"scene_id": scene.id},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["version"] == "正式版v1.0"
    assert items[0]["model_name"] == "backend/best.pt"
    assert Path(items[0]["model_path"]) == builtin_weights.resolve()
    assert items[0]["file_exists"] is True
    assert items[0]["is_default"] is True
    assert items[0]["dataset_version_id"] is None
    assert items[0]["training_task_id"] is None
    assert db_session.query(ModelVersion).filter_by(scene_id=scene.id).count() == 1

    # Re-reading the registry is idempotent and must not create another v1.0.
    repeated = client.get(
        "/api/training/model-versions",
        headers=headers,
        params={"scene_id": scene.id},
    )
    assert repeated.status_code == 200
    assert len(repeated.json()["items"]) == 1
    db_session.expire_all()
    assert db_session.query(ModelVersion).filter_by(scene_id=scene.id).count() == 1


def test_training_outputs_create_distinct_versions_and_can_switch_detection_default(
    client,
    db_session,
    monkeypatch,
    tmp_path,
):
    from app.entity.db_models import (
        DatasetVersion,
        DetectionScene,
        ModelVersion,
        TrainingMetric,
        TrainingTask,
        User,
    )
    from app.services.model_version_service import ModelVersionService, model_version_service

    headers = _auth_headers(client)
    user = db_session.query(User).filter_by(username="training_api_user").first()
    scene = DetectionScene(
        name="retrained_dataset_scene",
        display_name="Retrained Dataset Scene",
        category="retail",
        class_names=["product"],
        created_by=user.id,
    )
    db_session.add(scene)
    db_session.flush()
    dataset = DatasetVersion(
        scene_id=scene.id,
        version="dataset-v3",
        name="Dataset V3",
        status="pending_train",
        is_current=True,
        storage_path=str(tmp_path / "dataset"),
        data_yaml_path="data.yaml",
        content_hash="sha256:dataset-v3",
        created_by=user.id,
    )
    db_session.add(dataset)
    db_session.flush()

    tasks = []
    weights = []
    for index, optimizer in enumerate(("SGD", "AdamW"), start=1):
        task = TrainingTask(
            user_id=user.id,
            scene_id=scene.id,
            dataset_version_id=dataset.id,
            task_uuid=f"repeat{index}",
            status="completed",
            model_name="yolov11n",
            epochs=10 * index,
            img_size=640,
            batch_size=8,
            device="cpu",
            optimizer=optimizer,
            lr0=0.01 / index,
            augment_config={"degrees": index * 5},
            current_epoch=10 * index,
            dataset_content_hash=dataset.content_hash,
        )
        db_session.add(task)
        db_session.flush()
        db_session.add(
            TrainingMetric(
                task_id=task.id,
                epoch=task.epochs,
                box_loss=0.1 * index,
                cls_loss=0.2 * index,
                dfl_loss=0.3 * index,
                precision=0.80 + index / 100,
                recall=0.70 + index / 100,
                map50=0.90 + index / 100,
                map50_95=0.60 + index / 100,
            )
        )
        weight_path = tmp_path / f"run-{index}" / "weights" / "best.pt"
        weight_path.parent.mkdir(parents=True)
        weight_path.write_bytes(f"trained-model-{index}".encode())
        tasks.append(task)
        weights.append(weight_path)
    db_session.commit()

    # Keep this test independent from the real backend/best.pt file.
    monkeypatch.setattr(
        ModelVersionService,
        "_builtin_path",
        staticmethod(lambda: (tmp_path / "missing-builtin.pt").resolve()),
    )
    first = model_version_service.register_training_output(
        db_session,
        task=tasks[0],
        weights_path=weights[0],
    )
    second = model_version_service.register_training_output(
        db_session,
        task=tasks[1],
        weights_path=weights[1],
    )

    assert first.id != second.id
    assert first.dataset_version_id == second.dataset_version_id == dataset.id
    assert first.is_default is True
    assert second.is_default is False
    assert db_session.query(ModelVersion).filter_by(dataset_version_id=dataset.id).count() == 2

    # Registering the same training run again updates it instead of duplicating it.
    same_first = model_version_service.register_training_output(
        db_session,
        task=tasks[0],
        weights_path=weights[0],
    )
    assert same_first.id == first.id
    assert db_session.query(ModelVersion).filter_by(dataset_version_id=dataset.id).count() == 2

    listed = client.get(
        "/api/training/model-versions",
        headers=headers,
        params={"scene_id": scene.id},
    )
    assert listed.status_code == 200
    by_task = {item["training_task_uuid"]: item for item in listed.json()["items"]}
    assert set(by_task) == {"repeat1", "repeat2"}
    assert by_task["repeat2"]["dataset_version"] == "dataset-v3"
    assert by_task["repeat2"]["dataset_content_hash"] == "sha256:dataset-v3"
    assert by_task["repeat2"]["training_parameters"] == {
        "model_name": "yolov11n",
        "epochs": 20,
        "img_size": 640,
        "batch_size": 8,
        "device": "cpu",
        "optimizer": "AdamW",
        "lr0": 0.005,
        "augment_config": {"degrees": 10},
    }
    assert by_task["repeat2"]["training_result"]["map50"] == pytest.approx(0.92)
    assert by_task["repeat2"]["training_result"]["box_loss"] == pytest.approx(0.2)

    switched = client.post(
        f"/api/training/model-versions/{second.id}/set-default",
        headers=headers,
    )
    assert switched.status_code == 200
    assert switched.json()["is_default"] is True
    db_session.expire_all()
    assert db_session.get(ModelVersion, first.id).is_default is False
    assert db_session.get(ModelVersion, second.id).is_default is True

    weights[0].unlink()
    missing = client.post(
        f"/api/training/model-versions/{first.id}/set-default",
        headers=headers,
    )
    assert missing.status_code == 400
    assert "模型文件不存在" in missing.json()["message"]
    db_session.expire_all()
    assert db_session.get(ModelVersion, second.id).is_default is True
