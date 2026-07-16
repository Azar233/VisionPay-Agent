from pathlib import Path

from app.entity.db_models import DetectionScene, ModelVersion, User


def _auth_headers(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "model_import_user",
            "email": "model_import@example.com",
            "password": "123456",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={"username": "model_import_user", "password": "123456"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _scene(db_session):
    user = db_session.query(User).filter_by(username="model_import_user").one()
    scene = DetectionScene(
        name="imported_model_scene",
        display_name="Imported Model Scene",
        category="retail",
        class_names=[],
        created_by=user.id,
    )
    db_session.add(scene)
    db_session.commit()
    db_session.refresh(scene)
    return scene


def _mock_model_inspection(monkeypatch):
    from app.services.model_import_service import ModelImportService

    monkeypatch.setattr(
        ModelImportService,
        "_inspect_weights",
        classmethod(lambda cls, path: (["apple", "orange_juice"], "YOLO")),
    )


def test_import_available_model_from_server_path_builds_catalog_and_prices(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    from app.config.settings import settings

    headers = _auth_headers(client)
    scene = _scene(db_session)
    _mock_model_inspection(monkeypatch)
    managed_root = tmp_path / "managed"
    monkeypatch.setattr(settings, "DATASET_VERSION_ROOT", str(managed_root))
    source = tmp_path / "best.pt"
    source.write_bytes(b"fake-yolo-weights")

    response = client.post(
        "/api/datasets/import-available-model",
        headers=headers,
        data={
            "scene_id": str(scene.id),
            "version": "ready-model-v1",
            "name": "Ready model v1",
            "source_path": str(source),
            "set_current": "true",
            "set_default": "true",
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    dataset = result["dataset"]
    model = result["model_version"]
    assert dataset["status"] == "ready"
    assert dataset["is_current"] is True
    assert dataset["training_status"] == "trained"
    assert dataset["class_count"] == 2
    assert dataset["total_image_count"] == 0
    assert dataset["extra_metadata"]["catalog_only"] is True
    assert [item["class_name"] for item in dataset["classes"]] == ["apple", "orange_juice"]
    assert all(item["product_id"] for item in dataset["classes"])
    assert model["dataset_version_id"] == dataset["id"]
    assert model["is_default"] is True
    assert Path(model["model_path"]).read_bytes() == b"fake-yolo-weights"
    assert (Path(dataset["storage_path"]) / "data.yaml").is_file()
    assert (Path(dataset["storage_path"]) / "manifest.json").is_file()

    validation = client.post(
        f"/api/datasets/{dataset['id']}/validate",
        headers=headers,
        json={"check_filesystem": True},
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid"] is True

    prices = client.get(
        "/api/prices",
        headers=headers,
        params={"dataset_version_id": dataset["id"]},
    )
    assert prices.status_code == 200, prices.text
    assert len(prices.json()) == 2
    first_product = prices.json()[0]
    updated = client.put(
        f"/api/prices/{first_product['product_id']}",
        headers=headers,
        params={"dataset_version_id": dataset["id"]},
        json={"name": "苹果", "unit_price": 4.5, "currency": "CNY"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["unit_price"] == 4.5

    versions = client.get(
        "/api/training/model-versions",
        headers=headers,
        params={"scene_id": scene.id},
    )
    assert versions.status_code == 200, versions.text
    imported = next(item for item in versions.json()["items"] if item["id"] == model["id"])
    assert imported["is_default"] is True

    fallback_weights = tmp_path / "builtin-best.pt"
    fallback_weights.write_bytes(b"builtin-fallback-weights")
    from app.services.model_version_service import ModelVersionService

    monkeypatch.setattr(
        ModelVersionService,
        "_builtin_path",
        classmethod(lambda cls: fallback_weights),
    )
    archived = client.post(
        f"/api/datasets/{dataset['id']}/archive",
        headers=headers,
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"
    assert archived.json()["is_current"] is False

    db_session.expire_all()
    archived_model = db_session.query(ModelVersion).filter_by(id=model["id"]).one()
    assert archived_model.status == "archived"
    assert archived_model.is_default is False
    fallback_model = (
        db_session.query(ModelVersion)
        .filter(
            ModelVersion.scene_id == scene.id,
            ModelVersion.status == "active",
            ModelVersion.is_default.is_(True),
        )
        .one()
    )
    assert Path(fallback_model.model_path) == fallback_weights


def test_import_available_model_from_upload_copies_weights(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    from app.config.settings import settings

    headers = _auth_headers(client)
    scene = _scene(db_session)
    _mock_model_inspection(monkeypatch)
    managed_root = tmp_path / "managed"
    staging_root = tmp_path / "staging"
    monkeypatch.setattr(settings, "DATASET_VERSION_ROOT", str(managed_root))
    monkeypatch.setattr(settings, "DATASET_STAGING_ROOT", str(staging_root))

    response = client.post(
        "/api/datasets/import-available-model",
        headers=headers,
        data={
            "scene_id": str(scene.id),
            "version": "uploaded-model-v1",
            "name": "Uploaded model v1",
        },
        files={"file": ("best.pt", b"uploaded-yolo-weights", "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert Path(result["model_version"]["model_path"]).read_bytes() == b"uploaded-yolo-weights"
    assert result["dataset"]["class_count"] == 2
    assert not list((staging_root / "model-imports").glob("*.pt"))

    stored = db_session.query(ModelVersion).filter_by(id=result["model_version"]["id"]).one()
    assert stored.dataset_version_id == result["dataset"]["id"]
