"""Read-only Dataset Agent tools for the initial architecture phase."""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import StructuredTool

from app.agent.tools.common import json_text
from app.database.session import SessionLocal
from app.services.agent_handoff_service import agent_handoff_service
from app.services.agent_confirmation_service import agent_confirmation_service
from app.services.dataset_service import dataset_service


def build_dataset_tools(user_id: int, session_uuid: str) -> list:
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

    def list_dataset_versions(
        scene_id: int | None = None,
        status: Literal[
            "draft", "pending_train", "training", "published", "archived"
        ] | None = None,
    ) -> str:
        """列出全部数据集版本；可按 scene_id 和当前生命周期状态筛选。"""
        db = SessionLocal()
        try:
            result = dataset_service.list(
                db,
                scene_id=scene_id,
                status=status,
                current_only=False,
                limit=100,
            )
            return json_text(result)
        finally:
            db.close()

    def get_current_dataset_version(scene_id: int | None = None) -> str:
        """查询当前数据集版本；可提供 scene_id，返回版本状态、样本计数和训练摘要。"""
        db = SessionLocal()
        try:
            result = dataset_service.list(db, scene_id=scene_id, current_only=True, limit=20)
            return json_text(result)
        finally:
            db.close()

    def get_dataset_version_detail(dataset_id: int) -> str:
        """按数据集版本 ID 查看完整详情、类别映射、校验结果和训练状态。"""
        db = SessionLocal()
        try:
            dataset = dataset_service.get(db, dataset_id)
            return json_text(dataset_service.serialize(dataset))
        finally:
            db.close()

    def prepare_add_samples_handoff(
        dataset_id: int,
        mode: Literal["train_new", "train_existing", "scene"],
        existing_product_id: int | None = None,
        name: str | None = None,
        class_name: str | None = None,
        unit_price: float | None = None,
        barcode: str | None = None,
    ) -> str:
        """在用户已明确三种样品模式之一后，创建人工选图和绘框页面交接；不会写入样品。"""
        db = SessionLocal()
        try:
            handoff = agent_handoff_service.create_dataset_add_samples(
                db,
                user_id=user_id,
                session_uuid=session_uuid,
                dataset_id=dataset_id,
                mode=mode,
                existing_product_id=existing_product_id,
                name=name,
                class_name=class_name,
                unit_price=unit_price,
                barcode=barcode,
            )
            return json_text(agent_handoff_service.serialize(handoff))
        finally:
            db.close()

    def get_add_samples_handoff_status(handoff_id: str) -> str:
        """查询当前经营者的添加样品人工交接进度和最终结果。"""
        db = SessionLocal()
        try:
            handoff = agent_handoff_service.get(
                db,
                handoff_uuid=handoff_id,
                user_id=user_id,
            )
            return json_text(agent_handoff_service.serialize(handoff))
        finally:
            db.close()

    def preview_derive_dataset_version(
        dataset_id: int, version: str, name: str, description: str | None = None
    ) -> str:
        """预览从已冻结版本派生新草稿的复制范围，并生成一次性待确认操作；不会直接派生。"""
        return _preview(
            "dataset.derive",
            {"dataset_id": dataset_id, "version": version, "name": name, "description": description},
        )

    def preview_freeze_dataset_version(
        dataset_id: int, check_filesystem: bool = False
    ) -> str:
        """校验草稿并预览冻结后的只读影响，生成一次性待确认操作；不会直接冻结。"""
        return _preview(
            "dataset.freeze",
            {"dataset_id": dataset_id, "check_filesystem": check_filesystem},
        )

    def preview_archive_dataset_version(dataset_id: int) -> str:
        """预览归档版本对训练、模型和当前版本的影响，生成一次性待确认操作。"""
        return _preview("dataset.archive", {"dataset_id": dataset_id})

    def preview_delete_product_samples(
        dataset_id: int, product_id: int, deactivate_product: bool = True
    ) -> str:
        """统计将删除的图片、标注和类别重排范围，生成高风险一次性待确认操作。"""
        return _preview(
            "dataset.delete_product",
            {
                "dataset_id": dataset_id,
                "product_id": product_id,
                "deactivate_product": deactivate_product,
            },
        )

    def preview_delete_dataset_draft(dataset_id: int) -> str:
        """统计草稿的图片、标注、类别和引用，生成永久删除的一次性待确认操作。"""
        return _preview("dataset.delete_draft", {"dataset_id": dataset_id})

    return [
        StructuredTool.from_function(
            list_dataset_versions, name="list_dataset_versions"
        ),
        StructuredTool.from_function(
            get_current_dataset_version, name="get_current_dataset_version"
        ),
        StructuredTool.from_function(
            get_dataset_version_detail, name="get_dataset_version_detail"
        ),
        StructuredTool.from_function(
            prepare_add_samples_handoff, name="prepare_add_samples_handoff"
        ),
        StructuredTool.from_function(
            get_add_samples_handoff_status, name="get_add_samples_handoff_status"
        ),
        StructuredTool.from_function(
            preview_derive_dataset_version, name="preview_derive_dataset_version"
        ),
        StructuredTool.from_function(
            preview_freeze_dataset_version, name="preview_freeze_dataset_version"
        ),
        StructuredTool.from_function(
            preview_archive_dataset_version, name="preview_archive_dataset_version"
        ),
        StructuredTool.from_function(
            preview_delete_product_samples, name="preview_delete_product_samples"
        ),
        StructuredTool.from_function(
            preview_delete_dataset_draft, name="preview_delete_dataset_draft"
        ),
    ]
