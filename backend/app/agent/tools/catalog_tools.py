"""Read-only Catalog Agent tools for dataset-scoped and cross-version prices."""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from app.agent.tools.common import json_text
from app.database.session import SessionLocal
from app.entity.db_models import (
    DatasetClassMapping,
    DatasetVersion,
    ModelVersion,
    Product,
    ProductPrice,
)
from app.services.agent_confirmation_service import agent_confirmation_service


def _default_dataset_version_id(db) -> int | None:
    """当前默认检测模型绑定的数据集版本；没有默认模型时退回 is_current 版本。"""
    default_model = (
        db.query(ModelVersion)
        .filter(ModelVersion.is_default.is_(True), ModelVersion.status == "active")
        .first()
    )
    if default_model and default_model.dataset_version_id:
        return default_model.dataset_version_id
    current = db.query(DatasetVersion).filter(DatasetVersion.is_current.is_(True)).first()
    return current.id if current else None


def _price_row(mapping, products: dict, prices: dict, legacy_prices: list) -> dict:
    product = products.get(mapping.product_id)
    price = prices.get(mapping.product_id)
    if price is None and mapping.category_id is not None:
        for legacy in legacy_prices:
            if legacy.category_id == mapping.category_id and legacy.product_id in {
                None,
                mapping.product_id,
            }:
                price = legacy
                break
    return {
        "product_id": mapping.product_id,
        "product_key": mapping.product_key,
        "class_index": mapping.class_index,
        "class_name": mapping.class_name,
        "name": getattr(product, "name", None) or mapping.display_name,
        "barcode": getattr(product, "barcode", None),
        "unit_price": price.unit_price if price else None,
        "currency": (price.currency if price else None) or "CNY",
        "has_price": price is not None,
    }


def _version_price_rows(db, dataset_version_id: int, keyword: str, unpriced_only: bool) -> list[dict]:
    """Build the price rows of one dataset version with products/prices prefetched once."""
    mappings = (
        db.query(DatasetClassMapping)
        .filter(DatasetClassMapping.dataset_version_id == dataset_version_id)
        .order_by(DatasetClassMapping.class_index)
        .all()
    )
    if not mappings:
        return []
    products = {product.id: product for product in db.query(Product).all()}
    prices = {price.product_id: price for price in db.query(ProductPrice).all()}
    legacy_prices = [
        price for price in db.query(ProductPrice).all() if price.category_id is not None
    ]
    rows = [_price_row(mapping, products, prices, legacy_prices) for mapping in mappings]
    query = keyword.strip().lower()
    if query:
        rows = [
            row
            for row in rows
            if any(
                query in str(row.get(field) or "").lower()
                for field in ("product_id", "product_key", "class_name", "name", "barcode")
            )
        ]
    if unpriced_only:
        rows = [row for row in rows if not row["has_price"]]
    return rows


def build_catalog_tools(user_id: int, session_uuid: str) -> list:
    def _preview(action: str, parameters: dict) -> str:
        db = SessionLocal()
        try:
            view = agent_confirmation_service.create_preview(
                db,
                user_id=user_id,
                username=None,
                session_uuid=session_uuid,
                action=action,
                parameters=parameters,
            )
            view.pop("confirmation_token", None)
            return json_text(view)
        finally:
            db.close()

    def list_product_prices(
        dataset_version_id: int | None = None, keyword: str = "", unpriced_only: bool = False
    ) -> str:
        """查询某数据集版本的实时价目表；省略版本时默认当前检测模型绑定的数据集版本。"""
        db = SessionLocal()
        try:
            resolved_id = dataset_version_id or _default_dataset_version_id(db)
            if resolved_id is None:
                return json_text({"error": "没有可用的数据集版本"})
            dataset = db.query(DatasetVersion).filter(
                DatasetVersion.id == resolved_id
            ).first()
            if dataset is None:
                return json_text({"error": "数据集版本不存在"})
            rows = _version_price_rows(db, resolved_id, keyword, unpriced_only)
            return json_text(
                {
                    "dataset_version_id": resolved_id,
                    "version": dataset.version,
                    "is_default_scope": dataset_version_id is None,
                    "items": rows,
                }
            )
        finally:
            db.close()

    def search_product_prices(keyword: str = "", unpriced_only: bool = False) -> str:
        """跨全部数据集版本搜索商品价格，按版本分组返回；适合"所有数据集里有没有某商品、价格多少"的问题。"""
        db = SessionLocal()
        try:
            default_id = _default_dataset_version_id(db)
            versions = (
                db.query(DatasetVersion)
                .order_by(DatasetVersion.created_at.desc(), DatasetVersion.id.desc())
                .all()
            )
            groups = []
            for version in versions:
                rows = _version_price_rows(db, version.id, keyword, unpriced_only)
                if not rows:
                    continue
                groups.append(
                    {
                        "dataset_version_id": version.id,
                        "version": version.version,
                        "status": version.status,
                        "is_current": bool(version.is_current),
                        "is_default_scope": version.id == default_id,
                        "match_count": len(rows),
                        "items": rows,
                    }
                )
            return json_text(
                {
                    "keyword": keyword,
                    "matched_versions": len(groups),
                    "groups": groups,
                }
            )
        finally:
            db.close()

    def preview_update_product_price(
        dataset_version_id: int,
        product_id: int,
        unit_price: float,
        currency: str = "CNY",
    ) -> str:
        """实时读取原价并预览新价对顾客结算端的影响，生成一次性待确认操作。"""
        return _preview(
            "catalog.update_price",
            {
                "dataset_version_id": dataset_version_id,
                "product_id": product_id,
                "unit_price": unit_price,
                "currency": currency,
            },
        )

    def preview_clear_product_price(dataset_version_id: int, product_id: int) -> str:
        """预览清除价格后商品变为未定价的影响，生成高风险一次性待确认操作。"""
        return _preview(
            "catalog.clear_price",
            {"dataset_version_id": dataset_version_id, "product_id": product_id},
        )

    return [
        StructuredTool.from_function(list_product_prices, name="list_product_prices"),
        StructuredTool.from_function(search_product_prices, name="search_product_prices"),
        StructuredTool.from_function(
            preview_update_product_price, name="preview_update_product_price"
        ),
        StructuredTool.from_function(
            preview_clear_product_price, name="preview_clear_product_price"
        ),
    ]
