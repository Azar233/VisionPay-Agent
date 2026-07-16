"""Read-only Catalog Agent tools for current dataset-scoped prices."""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from app.agent.tools.common import json_text
from app.database.session import SessionLocal
from app.entity.db_models import DatasetClassMapping, DatasetVersion, Product, ProductPrice
from app.services.agent_confirmation_service import agent_confirmation_service


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
        dataset_version_id: int, keyword: str = "", unpriced_only: bool = False
    ) -> str:
        """查询某数据集版本的实时价目表，可按名称/类别/条码搜索或只看未定价商品。"""
        db = SessionLocal()
        try:
            dataset = db.query(DatasetVersion).filter(
                DatasetVersion.id == dataset_version_id
            ).first()
            if dataset is None:
                return json_text({"error": "数据集版本不存在"})
            mappings = db.query(DatasetClassMapping).filter(
                DatasetClassMapping.dataset_version_id == dataset_version_id
            ).order_by(DatasetClassMapping.class_index).all()
            rows = []
            for mapping in mappings:
                product = db.query(Product).filter(Product.id == mapping.product_id).first()
                price = db.query(ProductPrice).filter(
                    ProductPrice.product_id == mapping.product_id
                ).first()
                if price is None and mapping.category_id is not None:
                    legacy = db.query(ProductPrice).filter(
                        ProductPrice.category_id == mapping.category_id
                    ).first()
                    if legacy is not None and legacy.product_id in {None, mapping.product_id}:
                        price = legacy
                row = {
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
                rows.append(row)
            query = keyword.strip().lower()
            if query:
                rows = [
                    row for row in rows
                    if any(query in str(row.get(field) or "").lower() for field in (
                        "product_id", "product_key", "class_name", "name", "barcode"
                    ))
                ]
            if unpriced_only:
                rows = [row for row in rows if not row["has_price"]]
            return json_text({"dataset_version_id": dataset_version_id, "items": rows})
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
        StructuredTool.from_function(
            preview_update_product_price, name="preview_update_product_price"
        ),
        StructuredTool.from_function(
            preview_clear_product_price, name="preview_clear_product_price"
        ),
    ]
