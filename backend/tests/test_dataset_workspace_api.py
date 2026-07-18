import json
from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageDraw
import yaml


def _auth_headers(client):
    client.post(
        "/api/auth/register",
        json={"username": "workspace_user", "email": "workspace@example.com", "password": "123456"},
    )
    response = client.post(
        "/api/auth/login",
        json={"username": "workspace_user", "password": "123456"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _jpeg_bytes(color=(20, 80, 160)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (24, 24), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _product_jpeg_bytes() -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", (120, 100), "white")
    ImageDraw.Draw(image).rectangle((20, 15, 100, 85), fill=(190, 35, 45))
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _write_dataset(root):
    root.mkdir()
    (root / "data.yaml").write_text(
        "path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnc: 2\n"
        "names:\n  0: first_product\n  1: second_product\n",
        encoding="utf-8",
    )
    for split in ("train", "val", "test"):
        (root / "images" / split).mkdir(parents=True)
        (root / "labels" / split).mkdir(parents=True)
        for class_index in (0, 1):
            stem = f"{split}_{class_index}"
            image_color = (20 + class_index * 80, 80, 160 - class_index * 80)
            (root / "images" / split / f"{stem}.jpg").write_bytes(_jpeg_bytes(image_color))
            (root / "labels" / split / f"{stem}.txt").write_text(
                f"{class_index} 0.5 0.5 0.8 0.8\n",
                encoding="utf-8",
            )


def test_managed_dataset_end_to_end(client, db_session, tmp_path, monkeypatch):
    from app.config.settings import settings
    from app.entity.db_models import DetectionScene, ModelVersion, Product, ProductPrice, User
    from app.services.detection_service import detection_service

    headers = _auth_headers(client)
    user = db_session.query(User).filter_by(username="workspace_user").one()
    scene = DetectionScene(
        name="workspace_scene",
        display_name="Workspace Scene",
        category="retail",
        class_names=["first_product", "second_product"],
        created_by=user.id,
    )
    db_session.add(scene)
    db_session.flush()
    db_session.add_all(
        [
            ProductPrice(category_id=1, name="First", sku_name="first_product", unit_price=3.5),
            ProductPrice(category_id=2, name="Second", sku_name="second_product", unit_price=7.0),
        ]
    )
    db_session.commit()

    source = tmp_path / "source"
    managed = tmp_path / "managed"
    staging = tmp_path / "staging"
    _write_dataset(source)
    monkeypatch.setattr(settings, "DATASET_VERSION_ROOT", str(managed))
    monkeypatch.setattr(settings, "DATASET_STAGING_ROOT", str(staging))

    baseline_response = client.post(
        "/api/datasets/import-baseline",
        headers=headers,
        json={
            "scene_id": scene.id,
            "source_path": str(source),
            "version": "baseline-v1",
            "name": "Baseline",
            "copy_files": True,
            "set_current": True,
        },
    )
    assert baseline_response.status_code == 201, baseline_response.text
    baseline = baseline_response.json()
    assert baseline["status"] == "pending_train"
    assert baseline["is_current"] is True
    assert baseline["total_image_count"] == 6
    assert all(item["product_id"] for item in baseline["classes"])
    assert len({item["product_key"] for item in baseline["classes"]}) == 2
    assert (managed / f"scene_{scene.id}" / "baseline-v1" / "manifest.json").is_file()

    first_sample = client.get(
        f"/api/datasets/{baseline['id']}/products/{baseline['classes'][0]['product_id']}/sample-image",
        headers=headers,
    )
    assert first_sample.status_code == 200, first_sample.text
    assert first_sample.headers["content-type"] == "image/jpeg"
    assert first_sample.content == _jpeg_bytes((20, 80, 160))
    assert first_sample.content != _jpeg_bytes((100, 80, 80))
    missing_sample = client.get(
        f"/api/datasets/{baseline['id']}/products/999999/sample-image",
        headers=headers,
    )
    assert missing_sample.status_code == 404
    assert missing_sample.json()["message"] == "该商品暂无训练集图片"

    first_product_id = baseline["classes"][0]["product_id"]
    second_product_id = baseline["classes"][1]["product_id"]
    image_listing = client.get(
        f"/api/datasets/{baseline['id']}/products/{first_product_id}/images",
        headers=headers,
    )
    assert image_listing.status_code == 200, image_listing.text
    listed_images = image_listing.json()
    assert listed_images["total"] == 1
    assert [item["split"] for item in listed_images["items"]] == ["train"]
    assert [item["filename"] for item in listed_images["items"]] == ["train_0.jpg"]

    first_image_id = listed_images["items"][0]["id"]
    first_image = client.get(
        f"/api/datasets/{baseline['id']}/products/{first_product_id}/images/{first_image_id}",
        headers=headers,
    )
    assert first_image.status_code == 200, first_image.text
    assert first_image.content == _jpeg_bytes((20, 80, 160))
    unrelated_image = client.get(
        f"/api/datasets/{baseline['id']}/products/{second_product_id}/images/{first_image_id}",
        headers=headers,
    )
    assert unrelated_image.status_code == 404

    derive_task_response = client.post(
        f"/api/datasets/{baseline['id']}/derive-task",
        headers=headers,
        json={"version": "derived-v2", "name": "Derived"},
    )
    assert derive_task_response.status_code == 202, derive_task_response.text
    derive_task = derive_task_response.json()
    derive_status_response = client.get(
        f"/api/datasets/operations/{derive_task['task_id']}",
        headers=headers,
    )
    assert derive_status_response.status_code == 200, derive_status_response.text
    derive_status = derive_status_response.json()
    assert derive_status["status"] == "completed"
    assert derive_status["progress"] == 100
    assert derive_status["operation"] == "derive"
    derived = derive_status["result"]["dataset"]
    assert derived["status"] == "draft"
    assert [item["product_key"] for item in derived["classes"]] == [
        item["product_key"] for item in baseline["classes"]
    ]

    duplicate_task_response = client.post(
        f"/api/datasets/{baseline['id']}/derive-task",
        headers=headers,
        json={"version": "derived-v2", "name": "Duplicate"},
    )
    duplicate_task = duplicate_task_response.json()
    duplicate_status = client.get(
        f"/api/datasets/operations/{duplicate_task['task_id']}",
        headers=headers,
    ).json()
    assert duplicate_status["status"] == "failed"
    assert duplicate_status["progress"] < 100
    assert "版本号不能重复" in duplicate_status["message"]

    missing_train_response = client.post(
        f"/api/datasets/{derived['id']}/products/stage",
        headers=headers,
        data={"mode": "train_new"},
        files=[("val_files", ("validation-only.jpg", _jpeg_bytes(), "image/jpeg"))],
    )
    assert missing_train_response.status_code == 400
    assert "训练样本模式只能上传非空的 train 文件夹" in missing_train_response.json()["message"]

    flat_stage_response = client.post(
        f"/api/datasets/{derived['id']}/products/stage",
        headers=headers,
        data={"mode": "train_new"},
        files=[("train_files", ("flat.jpg", _jpeg_bytes(), "image/jpeg"))],
    )
    assert flat_stage_response.status_code == 200, flat_stage_response.text
    flat_stage = flat_stage_response.json()
    assert flat_stage["needs_review_count"] == 1
    assert flat_stage["images"][0]["boxes"] == []
    rejected_commit = client.post(
        f"/api/datasets/{derived['id']}/products/commit",
        headers=headers,
        json={
            "staging_token": flat_stage["staging_token"],
            "mode": "train_new",
            "name": "Invalid",
            "unit_price": 1,
            "images": [
                {
                    "image_id": flat_stage["images"][0]["image_id"],
                    "reviewed": True,
                    "boxes": [],
                }
            ],
        },
    )
    assert rejected_commit.status_code == 400
    assert "至少需要一个检测框" in rejected_commit.json()["message"]
    assert client.delete(
        f"/api/datasets/{derived['id']}/products/stage/{flat_stage['staging_token']}",
        headers=headers,
    ).status_code == 204

    upload = _product_jpeg_bytes()
    stage_response = client.post(
        f"/api/datasets/{derived['id']}/products/stage",
        headers=headers,
        data={"mode": "train_new"},
        files=[("train_files", ("third-train.jpg", upload, "image/jpeg"))],
    )
    assert stage_response.status_code == 200, stage_response.text
    staged = stage_response.json()
    assert staged["total_images"] == 1
    assert staged["needs_review_count"] == 1
    assert staged["images"][0]["boxes"] == []

    reviewed_images = [
        {
            "image_id": item["image_id"],
            "reviewed": True,
            "boxes": [{"x1": 18, "y1": 12, "x2": 102, "y2": 88}],
        }
        for item in staged["images"]
    ]
    add_task_response = client.post(
        f"/api/datasets/{derived['id']}/products/commit-task",
        headers=headers,
        json={
            "staging_token": staged["staging_token"],
            "mode": "train_new",
            "name": "Third",
            "unit_price": 9.9,
            "class_name": "third_product",
            "images": reviewed_images,
        },
    )
    assert add_task_response.status_code == 202, add_task_response.text
    add_task = add_task_response.json()
    add_status_response = client.get(
        f"/api/datasets/operations/{add_task['task_id']}",
        headers=headers,
    )
    assert add_status_response.status_code == 200, add_status_response.text
    add_status = add_status_response.json()
    assert add_status["status"] == "completed"
    assert add_status["progress"] == 100
    assert add_status["operation"] == "add_samples"
    added = add_status["result"]
    assert added["images_added"] == 1
    assert added["dataset"]["class_count"] == 3
    third_product_id = added["product_id"]
    assert not (staging / staged["staging_token"]).exists()

    derived_root = managed / f"scene_{scene.id}" / "derived-v2"
    third_labels = [
        path.read_text(encoding="utf-8").strip()
        for path in (derived_root / "labels" / "train").glob("*.txt")
        if path.read_text(encoding="utf-8").startswith("2 ")
    ]
    assert len(third_labels) == 1
    _, x_center, y_center, box_width, box_height = third_labels[0].split()
    assert float(x_center) == 0.5
    assert float(y_center) == 0.5
    assert 0.69 < float(box_width) < 0.71
    assert 0.75 < float(box_height) < 0.77

    existing_product_id = baseline["classes"][1]["product_id"]
    existing_stage_response = client.post(
        f"/api/datasets/{derived['id']}/products/stage",
        headers=headers,
        data={"mode": "train_existing"},
        files=[("train_files", ("second-extra-angle.jpg", upload, "image/jpeg"))],
    )
    assert existing_stage_response.status_code == 200, existing_stage_response.text
    existing_stage = existing_stage_response.json()
    existing_commit = client.post(
        f"/api/datasets/{derived['id']}/products/commit",
        headers=headers,
        json={
            "staging_token": existing_stage["staging_token"],
            "mode": "train_existing",
            "existing_product_id": existing_product_id,
            "images": [
                {
                    "image_id": existing_stage["images"][0]["image_id"],
                    "reviewed": True,
                    "boxes": [{"x1": 18, "y1": 12, "x2": 102, "y2": 88}],
                }
            ],
        },
    )
    assert existing_commit.status_code == 200, existing_commit.text
    assert existing_commit.json()["product_id"] == existing_product_id
    assert existing_commit.json()["dataset"]["class_count"] == 3

    scene_stage_response = client.post(
        f"/api/datasets/{derived['id']}/products/stage",
        headers=headers,
        data={"mode": "scene"},
        files=[
            ("val_files", ("checkout-val.jpg", upload, "image/jpeg")),
            ("test_files", ("checkout-test.jpg", upload, "image/jpeg")),
        ],
    )
    assert scene_stage_response.status_code == 200, scene_stage_response.text
    scene_stage = scene_stage_response.json()
    first_product_id = baseline["classes"][0]["product_id"]
    scene_images = [
        {
            "image_id": item["image_id"],
            "reviewed": True,
            "boxes": [
                {"x1": 8, "y1": 8, "x2": 52, "y2": 60, "product_id": first_product_id},
                {"x1": 60, "y1": 20, "x2": 112, "y2": 92, "product_id": third_product_id},
            ],
        }
        for item in scene_stage["images"]
    ]
    scene_commit = client.post(
        f"/api/datasets/{derived['id']}/products/commit",
        headers=headers,
        json={
            "staging_token": scene_stage["staging_token"],
            "mode": "scene",
            "images": scene_images,
        },
    )
    assert scene_commit.status_code == 200, scene_commit.text
    assert scene_commit.json()["images_added"] == 2
    assert scene_commit.json()["product_id"] is None

    unknown_stage_response = client.post(
        f"/api/datasets/{derived['id']}/products/stage",
        headers=headers,
        data={"mode": "scene"},
        files=[("val_files", ("unknown-product.jpg", upload, "image/jpeg"))],
    )
    assert unknown_stage_response.status_code == 200, unknown_stage_response.text
    unknown_stage = unknown_stage_response.json()
    unknown_commit = client.post(
        f"/api/datasets/{derived['id']}/products/commit",
        headers=headers,
        json={
            "staging_token": unknown_stage["staging_token"],
            "mode": "scene",
            "images": [
                {
                    "image_id": unknown_stage["images"][0]["image_id"],
                    "reviewed": True,
                    "boxes": [
                        {"x1": 8, "y1": 8, "x2": 52, "y2": 60, "product_id": 999999}
                    ],
                }
            ],
        },
    )
    assert unknown_commit.status_code == 400
    assert "未在 train 商品目录" in unknown_commit.json()["message"]
    assert client.delete(
        f"/api/datasets/{derived['id']}/products/stage/{unknown_stage['staging_token']}",
        headers=headers,
    ).status_code == 204

    delete_task_response = client.post(
        f"/api/datasets/{derived['id']}/products/{first_product_id}/delete-task",
        headers=headers,
        json={"deactivate_product": True},
    )
    assert delete_task_response.status_code == 202, delete_task_response.text
    delete_task = delete_task_response.json()
    delete_status_response = client.get(
        f"/api/datasets/operations/{delete_task['task_id']}",
        headers=headers,
    )
    assert delete_status_response.status_code == 200, delete_status_response.text
    delete_status = delete_status_response.json()
    assert delete_status["status"] == "completed"
    assert delete_status["progress"] == 100
    assert delete_status["operation"] == "delete_product"
    deleted = delete_status["result"]
    assert deleted["images_deleted"] == 3
    assert deleted["annotations_deleted"] == 5
    assert deleted["dataset"]["class_count"] == 2
    assert [item["class_index"] for item in deleted["dataset"]["classes"]] == [0, 1]
    assert [item["product_id"] for item in deleted["dataset"]["classes"]] == [
        baseline["classes"][1]["product_id"],
        third_product_id,
    ]
    assert db_session.query(Product).filter(Product.id == first_product_id).one().is_active is False

    kept_scene_labels = [
        path.read_text(encoding="utf-8").strip()
        for path in (derived_root / "labels" / "val").glob("manual_*.txt")
    ]
    assert len(kept_scene_labels) == 1
    assert kept_scene_labels[0].startswith("1 ")

    rewritten_yaml = yaml.safe_load((derived_root / "data.yaml").read_text(encoding="utf-8"))
    rewritten_manifest = json.loads(
        (derived_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert rewritten_yaml["nc"] == 2
    assert len(rewritten_yaml["names"]) == 2
    assert len(rewritten_manifest["products"]) == 2

    freeze_response = client.post(
        f"/api/datasets/{derived['id']}/freeze",
        headers=headers,
        json={"check_filesystem": True},
    )
    assert freeze_response.status_code == 200, freeze_response.text
    frozen = freeze_response.json()
    assert frozen["status"] == "pending_train"

    from app.api import training as training_api

    captured = {}

    def fake_start_training(db, user_id, scene_id, config):
        captured.update(config)
        return SimpleNamespace(
            id=9001,
            task_uuid="workspace-train",
            status="pending",
            model_name=config["model_name"],
            epochs=config["epochs"],
            dataset_size=config["dataset_size"],
            dataset_version_id=config["dataset_version_id"],
            dataset_version=SimpleNamespace(version=frozen["version"]),
        )

    monkeypatch.setattr(training_api.training_service, "start_training", fake_start_training)
    training_response = client.post(
        "/api/training/start",
        headers=headers,
        json={
            "scene_id": scene.id,
            "dataset_version_id": frozen["id"],
            "model_name": "yolov11n",
            "epochs": 1,
            "device": "cpu",
        },
    )
    assert training_response.status_code == 200, training_response.text
    assert captured["dataset_version_id"] == frozen["id"]
    assert captured["dataset_content_hash"] == frozen["content_hash"]

    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"weights")
    model = ModelVersion(
        scene_id=scene.id,
        dataset_version_id=frozen["id"],
        version="model-v2",
        model_name="model-v2",
        model_path=str(model_path),
        is_default=True,
    )
    db_session.add(model)
    db_session.commit()
    db_session.refresh(model)

    summary = detection_service.calculate_price(
        db_session,
        {0: 2, 1: 1},
        model_version_id=model.id,
    )
    assert [item["product_id"] for item in summary["items"]] == [
        baseline["classes"][1]["product_id"],
        third_product_id,
    ]
    assert summary["total_price"] == 23.9
