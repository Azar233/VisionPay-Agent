from app.entity.db_models import DetectionScene, TrainingTask, User


def _auth_headers(client, username="dataset_user"):
    client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "123456",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "123456"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _scene(db_session, username="dataset_user"):
    user = db_session.query(User).filter(User.username == username).first()
    scene = DetectionScene(
        name=f"dataset_scene_{username}",
        display_name="Dataset Scene",
        category="retail",
        class_names=["first", "second"],
        created_by=user.id,
    )
    db_session.add(scene)
    db_session.commit()
    db_session.refresh(scene)
    return scene


def _payload(scene_id, version="v1"):
    return {
        "scene_id": scene_id,
        "version": version,
        "name": f"Dataset {version}",
        "storage_path": f"/cluster/datasets/{version}",
        "data_yaml_path": "data.yaml",
        "manifest_path": "manifest.json",
        "content_hash": f"sha256:{version}",
        "class_count": 2,
        "train_image_count": 80,
        "val_image_count": 10,
        "test_image_count": 10,
        "train_annotation_count": 90,
        "val_annotation_count": 12,
        "test_annotation_count": 11,
        "classes": [
            {
                "class_index": 0,
                "product_key": "sku-first",
                "category_id": 1,
                "class_name": "first",
                "display_name": "第一个商品",
            },
            {
                "class_index": 1,
                "product_key": "sku-second",
                "category_id": 2,
                "class_name": "second",
                "display_name": "第二个商品",
            },
        ],
    }


def test_dataset_routes_require_auth(client):
    assert client.get("/api/datasets").status_code == 401


def test_dataset_draft_validate_freeze_and_current(client, db_session):
    headers = _auth_headers(client)
    scene = _scene(db_session)

    created = client.post("/api/datasets", headers=headers, json=_payload(scene.id))
    assert created.status_code == 201
    dataset = created.json()
    assert dataset["status"] == "draft"
    assert dataset["total_image_count"] == 100
    assert [item["product_key"] for item in dataset["classes"]] == [
        "sku-first",
        "sku-second",
    ]

    validation = client.post(
        f"/api/datasets/{dataset['id']}/validate",
        headers=headers,
        json={"check_filesystem": False},
    )
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    assert validation.json()["checked_filesystem"] is False

    frozen = client.post(
        f"/api/datasets/{dataset['id']}/freeze",
        headers=headers,
        json={"check_filesystem": False},
    )
    assert frozen.status_code == 200
    assert frozen.json()["status"] == "ready"

    update = client.put(
        f"/api/datasets/{dataset['id']}",
        headers=headers,
        json={"name": "must not change"},
    )
    assert update.status_code == 400

    current = client.post(
        f"/api/datasets/{dataset['id']}/set-current",
        headers=headers,
    )
    assert current.status_code == 200
    assert current.json()["is_current"] is True
    fetched = client.get(
        f"/api/datasets/current?scene_id={scene.id}",
        headers=headers,
    )
    assert fetched.status_code == 200
    assert fetched.json()["version"] == "v1"


def test_dataset_validation_rejects_incomplete_mapping(client, db_session):
    headers = _auth_headers(client, "dataset_invalid_user")
    scene = _scene(db_session, "dataset_invalid_user")
    payload = _payload(scene.id)
    payload["classes"] = payload["classes"][:1]

    created = client.post("/api/datasets", headers=headers, json=payload)
    assert created.status_code == 201
    dataset_id = created.json()["id"]

    validation = client.post(
        f"/api/datasets/{dataset_id}/validate",
        headers=headers,
        json={},
    )
    assert validation.status_code == 200
    assert validation.json()["valid"] is False
    assert any("类别映射数量" in item for item in validation.json()["errors"])

    freeze = client.post(
        f"/api/datasets/{dataset_id}/freeze",
        headers=headers,
        json={},
    )
    assert freeze.status_code == 400


def test_current_switch_archive_and_draft_delete(client, db_session):
    headers = _auth_headers(client, "dataset_lifecycle_user")
    scene = _scene(db_session, "dataset_lifecycle_user")
    ids = []
    for version in ("v1", "v2"):
        created = client.post(
            "/api/datasets",
            headers=headers,
            json=_payload(scene.id, version),
        )
        assert created.status_code == 201
        dataset_id = created.json()["id"]
        ids.append(dataset_id)
        assert client.post(
            f"/api/datasets/{dataset_id}/freeze",
            headers=headers,
            json={},
        ).status_code == 200

    assert client.post(f"/api/datasets/{ids[0]}/set-current", headers=headers).status_code == 200
    assert client.post(f"/api/datasets/{ids[1]}/set-current", headers=headers).status_code == 200
    first = client.get(f"/api/datasets/{ids[0]}", headers=headers).json()
    assert first["is_current"] is False
    assert client.post(f"/api/datasets/{ids[0]}/archive", headers=headers).status_code == 200
    assert client.post(f"/api/datasets/{ids[1]}/archive", headers=headers).status_code == 400

    draft = client.post(
        "/api/datasets",
        headers=headers,
        json={**_payload(scene.id, "v3"), "content_hash": None},
    ).json()
    delete_task_response = client.post(f"/api/datasets/{draft['id']}/delete-task", headers=headers)
    assert delete_task_response.status_code == 202
    delete_task = delete_task_response.json()
    delete_status_response = client.get(
        f"/api/datasets/operations/{delete_task['task_id']}",
        headers=headers,
    )
    assert delete_status_response.status_code == 200
    delete_status = delete_status_response.json()
    assert delete_status["status"] == "completed"
    assert delete_status["progress"] == 100
    assert delete_status["operation"] == "delete_draft"
    assert delete_status["result"]["dataset_id"] == draft["id"]

    listing = client.get(f"/api/datasets?scene_id={scene.id}", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 2


def test_dataset_version_is_unique_per_scene(client, db_session):
    headers = _auth_headers(client, "dataset_unique_user")
    scene = _scene(db_session, "dataset_unique_user")
    assert client.post("/api/datasets", headers=headers, json=_payload(scene.id)).status_code == 201
    duplicate = client.post("/api/datasets", headers=headers, json=_payload(scene.id))
    assert duplicate.status_code == 409


def test_remote_dataset_filesystem_check_is_reported_as_skipped(client, db_session):
    headers = _auth_headers(client, "dataset_remote_user")
    scene = _scene(db_session, "dataset_remote_user")
    payload = _payload(scene.id)
    payload["storage_path"] = "s3://vision-pay/datasets/v1"
    created = client.post("/api/datasets", headers=headers, json=payload).json()

    validation = client.post(
        f"/api/datasets/{created['id']}/validate",
        headers=headers,
        json={"check_filesystem": True},
    )
    assert validation.status_code == 200
    report = validation.json()
    assert report["valid"] is True
    assert report["checked_filesystem"] is True
    assert any("远程 URI" in item for item in report["warnings"])


def test_dataset_list_reports_training_lineage(client, db_session):
    headers = _auth_headers(client, "dataset_training_user")
    scene = _scene(db_session, "dataset_training_user")
    created = client.post(
        "/api/datasets",
        headers=headers,
        json=_payload(scene.id),
    ).json()
    user = db_session.query(User).filter(User.username == "dataset_training_user").first()
    task = TrainingTask(
        user_id=user.id,
        scene_id=scene.id,
        dataset_version_id=created["id"],
        dataset_content_hash="sha256:v1",
        task_uuid="dataset-lineage-task",
        status="completed",
        model_name="yolov11n",
        epochs=1,
        current_epoch=1,
        progress=100,
    )
    db_session.add(task)
    db_session.commit()

    listing = client.get(
        f"/api/datasets?scene_id={scene.id}",
        headers=headers,
    ).json()
    item = listing["items"][0]
    assert item["training_status"] == "trained"
    assert item["training_task_count"] == 1
    assert item["completed_training_count"] == 1
    assert item["latest_training_task_uuid"] == "dataset-lineage-task"
