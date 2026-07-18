import json

import pytest

from app.agent.tools import catalog_tools
from app.entity.db_models import (
    DatasetClassMapping,
    DatasetVersion,
    DetectionScene,
    ModelVersion,
    Product,
    ProductPrice,
    User,
)


@pytest.fixture
def price_data(db_session, monkeypatch):
    """两个版本各有价目数据：当前默认模型绑定 v-current，另一个版本 v-old。"""
    user = User(username="catalog_user", email="catalog@example.com", hashed_password="x", is_active=True)
    scene = DetectionScene(name="catalog-scene", display_name="价目场景", category="retail", class_names=["cola"])
    db_session.add_all([user, scene])
    db_session.flush()
    current = DatasetVersion(
        scene_id=scene.id, version="v-current", name="当前版本", status="published",
        storage_path="dataset_versions/v-current", data_yaml_path="data.yaml",
        class_count=2, is_current=True, created_by=user.id,
    )
    old = DatasetVersion(
        scene_id=scene.id, version="v-old", name="旧版本", status="published",
        storage_path="dataset_versions/v-old", data_yaml_path="data.yaml",
        class_count=1, is_current=False, created_by=user.id,
    )
    cola = Product(product_key="catalog:cola", name="可口可乐500ml", sku_name="cola", barcode="6901234567890")
    sprite = Product(product_key="catalog:sprite", name="雪碧330ml", sku_name="sprite", barcode="6901234567891")
    db_session.add_all([current, old, cola, sprite])
    db_session.flush()
    db_session.add_all([
        DatasetClassMapping(
            dataset_version_id=current.id, class_index=0, product_id=cola.id,
            product_key=cola.product_key, category_id=401, class_name="cola", display_name="可口可乐500ml",
        ),
        DatasetClassMapping(
            dataset_version_id=current.id, class_index=1, product_id=sprite.id,
            product_key=sprite.product_key, category_id=402, class_name="sprite", display_name="雪碧330ml",
        ),
        DatasetClassMapping(
            dataset_version_id=old.id, class_index=0, product_id=cola.id,
            product_key=cola.product_key, category_id=401, class_name="cola", display_name="可口可乐500ml",
        ),
        ProductPrice(product_id=cola.id, category_id=401, sku_name="cola", name="可口可乐500ml", unit_price=3.5, currency="CNY"),
    ])
    db_session.add(
        ModelVersion(
            scene_id=scene.id, dataset_version_id=current.id, version="m-current",
            model_name="yolov11n", status="active", is_default=True,
            model_path="models/m-current.pt",
        )
    )
    db_session.commit()

    # 工具内部使用 SessionLocal 创建会话，测试时替换为测试库会话。
    monkeypatch.setattr(catalog_tools, "SessionLocal", lambda: db_session)
    return {"current": current, "old": old, "cola": cola, "sprite": sprite}


def _tool(name):
    return next(item for item in catalog_tools.build_catalog_tools(1, "session") if item.name == name)


def test_list_product_prices_defaults_to_default_model_dataset(price_data):
    result = json.loads(_tool("list_product_prices").invoke({}))

    assert result["dataset_version_id"] == price_data["current"].id
    assert result["is_default_scope"] is True
    names = {item["name"] for item in result["items"]}
    assert names == {"可口可乐500ml", "雪碧330ml"}
    cola = next(item for item in result["items"] if item["name"] == "可口可乐500ml")
    assert cola["unit_price"] == 3.5
    sprite = next(item for item in result["items"] if item["name"] == "雪碧330ml")
    assert sprite["has_price"] is False


def test_list_product_prices_explicit_version_keeps_scope(price_data):
    result = json.loads(
        _tool("list_product_prices").invoke({"dataset_version_id": price_data["old"].id})
    )

    assert result["dataset_version_id"] == price_data["old"].id
    assert result["is_default_scope"] is False
    assert [item["name"] for item in result["items"]] == ["可口可乐500ml"]


def test_search_product_prices_across_versions(price_data):
    result = json.loads(_tool("search_product_prices").invoke({"keyword": "可乐"}))

    assert result["matched_versions"] == 2
    by_version = {group["version"]: group for group in result["groups"]}
    assert by_version["v-current"]["is_default_scope"] is True
    assert by_version["v-current"]["is_current"] is True
    assert by_version["v-old"]["is_default_scope"] is False
    assert by_version["v-old"]["items"][0]["unit_price"] == 3.5


def test_search_product_prices_keyword_filters_versions(price_data):
    result = json.loads(_tool("search_product_prices").invoke({"keyword": "雪碧"}))

    assert result["matched_versions"] == 1
    assert result["groups"][0]["version"] == "v-current"
    assert result["groups"][0]["items"][0]["has_price"] is False
