"""Impact preview and one-time confirmation for Agent-initiated writes."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.entity.db_models import (
    AgentPendingOperation,
    ChatSession,
    DatasetAnnotation,
    DatasetClassMapping,
    DatasetImage,
    DatasetVersion,
    ModelVersion,
    OperationLog,
    Product,
    ProductPrice,
    TrainingTask,
    User,
)
from app.entity.schemas import DatasetDeriveRequest, ProductPriceUpdate, TrainingTaskCreate
from app.services.dataset_service import dataset_service
from app.services.dataset_workspace_service import dataset_workspace_service
from app.services.model_version_service import model_version_service
from app.training.training_service import training_service


ACTION_META = {
    "dataset.derive": ("dataset", "R2", "派生数据集版本"),
    "dataset.freeze": ("dataset", "R2", "冻结数据集版本"),
    "dataset.archive": ("dataset", "R2", "归档数据集版本"),
    "dataset.delete_product": ("dataset", "R3", "删除商品及相关样品"),
    "dataset.delete_draft": ("dataset", "R3", "删除数据集草稿"),
    "training.start": ("training", "R2", "启动训练"),
    "training.stop": ("training", "R2", "停止训练"),
    "training.set_default_model": ("training", "R3", "切换默认模型"),
    "catalog.update_price": ("catalog", "R2", "更新商品价格"),
    "catalog.clear_price": ("catalog", "R3", "清除商品价格"),
}

FROZEN_DATASET_STATUSES = {"pending_train", "training", "published"}


class AgentConfirmationError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_operation") -> None:
        super().__init__(message)
        self.code = code


def _json_default(value: Any):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=_json_default))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _fingerprint(action: str, parameters: dict) -> str:
    payload = json.dumps(
        {"action": action, "parameters": parameters},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AgentConfirmationService:
    terminal_statuses = {"completed", "failed", "cancelled", "expired"}

    @staticmethod
    def _audit(
        db: Session,
        operation: AgentPendingOperation,
        *,
        username: str | None,
        event: str,
        status: str = "success",
        detail: str = "",
    ) -> None:
        if username is None:
            username = db.query(User.username).filter(User.id == operation.user_id).scalar()
        description = json.dumps(
            {
                "operation_uuid": operation.operation_uuid,
                "domain": operation.domain,
                "action": operation.action,
                "event": event,
                "detail": detail,
            },
            ensure_ascii=False,
        )[:500]
        db.add(
            OperationLog(
                user_id=operation.user_id,
                username=username,
                module="agent",
                action=event,
                target_type="agent_pending_operation",
                target_id=operation.operation_uuid,
                description=description,
                status=status,
                error_message=detail[:1000] if status == "failure" else None,
            )
        )

    @staticmethod
    def _issue_token(operation: AgentPendingOperation) -> str:
        token = secrets.token_urlsafe(32)
        operation.confirmation_token_hash = _token_hash(token)
        operation.token_expires_at = datetime.now() + timedelta(
            seconds=int(settings.AGENT_CONFIRMATION_TTL_SECONDS)
        )
        operation.token_consumed_at = None
        return token

    @classmethod
    def _expire_if_needed(cls, db: Session, operation: AgentPendingOperation) -> None:
        if operation.status == "pending" and operation.token_expires_at <= datetime.now():
            operation.status = "expired"
            operation.updated_at = datetime.now()
            db.commit()

    @classmethod
    def serialize(
        cls,
        operation: AgentPendingOperation,
        *,
        confirmation_token: str | None = None,
        replayed: bool = False,
    ) -> dict:
        result = {
            "operation_uuid": operation.operation_uuid,
            "session_uuid": operation.session_uuid,
            "domain": operation.domain,
            "action": operation.action,
            "risk_level": operation.risk_level,
            "status": operation.status,
            "parameters": operation.parameters or {},
            "impact": operation.impact or {},
            "token_expires_at": operation.token_expires_at,
            "token_consumed_at": operation.token_consumed_at,
            "result": operation.result,
            "error_message": operation.error_message,
            "created_at": operation.created_at,
            "updated_at": operation.updated_at,
            "executed_at": operation.executed_at,
            "replayed": replayed,
        }
        if confirmation_token is not None:
            result["confirmation_token"] = confirmation_token
        return _json_safe(result)

    @staticmethod
    def _dataset_counts(db: Session, dataset_id: int) -> dict:
        image_count = db.query(DatasetImage).filter(
            DatasetImage.dataset_version_id == dataset_id
        ).count()
        annotation_count = (
            db.query(DatasetAnnotation)
            .join(DatasetImage, DatasetAnnotation.dataset_image_id == DatasetImage.id)
            .filter(DatasetImage.dataset_version_id == dataset_id)
            .count()
        )
        return {
            "images": image_count,
            "annotations": annotation_count,
            "classes": db.query(DatasetClassMapping).filter(
                DatasetClassMapping.dataset_version_id == dataset_id
            ).count(),
            "training_tasks": db.query(TrainingTask).filter(
                TrainingTask.dataset_version_id == dataset_id
            ).count(),
            "model_versions": db.query(ModelVersion).filter(
                ModelVersion.dataset_version_id == dataset_id
            ).count(),
        }

    @classmethod
    def _preview_dataset(cls, db: Session, action: str, raw: dict) -> tuple[dict, dict]:
        dataset_id = int(raw.get("dataset_id") or 0)
        if dataset_id < 1:
            raise AgentConfirmationError("dataset_id 必须是正整数")
        dataset = dataset_service.get(db, dataset_id)
        counts = cls._dataset_counts(db, dataset_id)
        target = {
            "dataset_id": dataset.id,
            "version": dataset.version,
            "name": dataset.name,
            "scene_id": dataset.scene_id,
            "status": dataset.status,
            "is_current": bool(dataset.is_current),
        }
        warnings: list[str] = []

        if action == "dataset.derive":
            request = DatasetDeriveRequest(**raw)
            parameters = {"dataset_id": dataset_id, **request.model_dump()}
            if dataset.status not in FROZEN_DATASET_STATUSES | {"archived"}:
                raise AgentConfirmationError("只有已冻结数据集可以派生")
            duplicate = db.query(DatasetVersion).filter(
                DatasetVersion.scene_id == dataset.scene_id,
                DatasetVersion.version == request.version,
            ).first()
            if duplicate:
                raise AgentConfirmationError("目标版本号已存在")
            impact = {
                "title": "派生数据集版本",
                "summary": f"将从 {dataset.version} 复制索引与文件，创建可编辑草稿 {request.version}",
                "target": target,
                "changes": {"new_version": request.version, "new_name": request.name, **counts},
                "warnings": ["派生会复制数据集文件，耗时取决于样品数量"],
            }
            return parameters, impact

        parameters = {"dataset_id": dataset_id}
        if action == "dataset.freeze":
            check_filesystem = bool(raw.get("check_filesystem", False))
            if dataset.status != "draft":
                raise AgentConfirmationError("只有草稿数据集可以冻结")
            report = dataset_service.validate(
                db, dataset_id=dataset_id, check_filesystem=check_filesystem
            )
            if not report.get("valid"):
                raise AgentConfirmationError(
                    "数据集校验未通过：" + "；".join(report.get("errors") or [])
                )
            parameters["check_filesystem"] = check_filesystem
            impact = {
                "title": "冻结数据集版本",
                "summary": f"冻结后 {dataset.version} 将变为只读，可用于训练",
                "target": target,
                "changes": {**counts, "status": "draft → pending_train"},
                "validation": report,
                "warnings": ["冻结后不能直接增删样品，需要派生新草稿"],
            }
            return parameters, impact

        if action == "dataset.archive":
            if dataset.status not in FROZEN_DATASET_STATUSES:
                raise AgentConfirmationError("只有已冻结数据集可以归档")
            if dataset.is_current:
                warnings.append("归档当前版本时系统会为同一场景选择替代当前数据集")
            if counts["training_tasks"] or counts["model_versions"]:
                warnings.append("关联活动模型会被归档，历史训练和审计记录会保留")
            impact = {
                "title": "归档数据集版本",
                "summary": f"归档后 {dataset.version} 不再作为可用训练版本展示",
                "target": target,
                "changes": {**counts, "status": f"{dataset.status} → archived"},
                "warnings": warnings,
            }
            return parameters, impact

        if action == "dataset.delete_draft":
            if dataset.status != "draft" or dataset.is_current:
                raise AgentConfirmationError("只能删除未启用的草稿数据集")
            child_count = len(dataset.children)
            if child_count:
                raise AgentConfirmationError("存在派生版本，不能删除该草稿")
            impact = {
                "title": "删除数据集草稿",
                "summary": f"将永久删除草稿 {dataset.version} 及其数据库索引和文件",
                "target": target,
                "changes": {**counts, "child_versions": child_count, "permanent_delete": True},
                "warnings": ["此操作不可撤销"],
            }
            return parameters, impact

        if action == "dataset.delete_product":
            product_id = int(raw.get("product_id") or 0)
            if product_id < 1:
                raise AgentConfirmationError("product_id 必须是正整数")
            if dataset.status != "draft":
                raise AgentConfirmationError("只有草稿数据集可以删除商品样品")
            mapping = db.query(DatasetClassMapping).filter(
                DatasetClassMapping.dataset_version_id == dataset_id,
                DatasetClassMapping.product_id == product_id,
            ).first()
            if mapping is None:
                raise AgentConfirmationError("商品不属于目标数据集版本")
            product = db.query(Product).filter(Product.id == product_id).first()
            affected_images = (
                db.query(DatasetImage.id)
                .join(DatasetAnnotation, DatasetAnnotation.dataset_image_id == DatasetImage.id)
                .filter(
                    DatasetImage.dataset_version_id == dataset_id,
                    DatasetAnnotation.product_id == product_id,
                )
                .distinct()
                .all()
            )
            image_ids = [row[0] for row in affected_images]
            annotation_count = db.query(DatasetAnnotation).filter(
                DatasetAnnotation.dataset_image_id.in_(image_ids or [-1]),
                DatasetAnnotation.product_id == product_id,
            ).count()
            mixed_images = (
                db.query(DatasetAnnotation.dataset_image_id)
                .filter(
                    DatasetAnnotation.dataset_image_id.in_(image_ids or [-1]),
                    DatasetAnnotation.product_id != product_id,
                )
                .distinct()
                .count()
            )
            classes_reindexed = db.query(DatasetClassMapping).filter(
                DatasetClassMapping.dataset_version_id == dataset_id,
                DatasetClassMapping.class_index > mapping.class_index,
            ).count()
            deactivate = bool(raw.get("deactivate_product", True))
            parameters.update({"product_id": product_id, "deactivate_product": deactivate})
            impact = {
                "title": "删除商品及相关样品",
                "summary": f"将从 {dataset.version} 删除商品 {getattr(product, 'name', None) or mapping.display_name or mapping.class_name}",
                "target": {
                    **target,
                    "product_id": product_id,
                    "product_key": mapping.product_key,
                    "class_name": mapping.class_name,
                    "class_index": mapping.class_index,
                },
                "changes": {
                    "affected_images": len(image_ids),
                    "annotations_deleted": annotation_count,
                    "mixed_scene_images_retained": mixed_images,
                    "classes_reindexed": classes_reindexed,
                    "deactivate_product": deactivate,
                },
                "warnings": ["此操作不可撤销", "多商品场景图会保留其他商品标注"],
            }
            return parameters, impact

        raise AgentConfirmationError("不支持的数据集操作")

    @staticmethod
    def _price_mapping(db: Session, dataset_id: int, product_id: int) -> DatasetClassMapping:
        dataset = db.query(DatasetVersion).filter(DatasetVersion.id == dataset_id).first()
        if dataset is None:
            raise AgentConfirmationError("数据集版本不存在")
        mapping = db.query(DatasetClassMapping).filter(
            DatasetClassMapping.dataset_version_id == dataset_id,
            DatasetClassMapping.product_id == product_id,
        ).first()
        if mapping is None:
            raise AgentConfirmationError("商品不属于所选数据集版本")
        return mapping

    @staticmethod
    def _price_record(db: Session, mapping: DatasetClassMapping) -> ProductPrice | None:
        price = db.query(ProductPrice).filter(
            ProductPrice.product_id == mapping.product_id
        ).first()
        if price is not None or mapping.category_id is None:
            return price
        legacy = db.query(ProductPrice).filter(
            ProductPrice.category_id == mapping.category_id
        ).first()
        return legacy if legacy is not None and legacy.product_id in {None, mapping.product_id} else None

    @classmethod
    def _preview_catalog(cls, db: Session, action: str, raw: dict) -> tuple[dict, dict]:
        dataset_id = int(raw.get("dataset_version_id") or 0)
        product_id = int(raw.get("product_id") or 0)
        if dataset_id < 1 or product_id < 1:
            raise AgentConfirmationError("dataset_version_id 和 product_id 必须是正整数")
        mapping = cls._price_mapping(db, dataset_id, product_id)
        price = cls._price_record(db, mapping)
        product = db.query(Product).filter(Product.id == product_id).first()
        target = {
            "dataset_version_id": dataset_id,
            "product_id": product_id,
            "product_key": mapping.product_key,
            "name": getattr(product, "name", None) or mapping.display_name,
            "class_name": mapping.class_name,
        }
        old_price = None if price is None else float(price.unit_price)
        old_currency = (price.currency if price else None) or "CNY"

        if action == "catalog.update_price":
            update = ProductPriceUpdate(**raw)
            values = update.model_dump(exclude_unset=True)
            if values.get("unit_price") is None:
                raise AgentConfirmationError("改价必须明确新单价")
            parameters = {
                "dataset_version_id": dataset_id,
                "product_id": product_id,
                **values,
            }
            impact = {
                "title": "更新商品价格",
                "summary": f"商品价格将从 {old_price if old_price is not None else '未定价'} 改为 {values['unit_price']} {values.get('currency') or old_currency}",
                "target": target,
                "changes": {
                    "old_price": old_price,
                    "new_price": values["unit_price"],
                    "old_currency": old_currency,
                    "new_currency": values.get("currency") or old_currency,
                },
                "warnings": ["确认后顾客结算端将立即使用新价格"],
            }
            return parameters, impact

        if action == "catalog.clear_price":
            if price is None:
                raise AgentConfirmationError("该商品尚未设置价格")
            parameters = {"dataset_version_id": dataset_id, "product_id": product_id}
            impact = {
                "title": "清除商品价格",
                "summary": f"将清除商品当前价格 {old_price} {old_currency}",
                "target": target,
                "changes": {"old_price": old_price, "new_price": None, "currency": old_currency},
                "warnings": ["顾客结算端会把该商品标记为未定价", "此操作需要重新设置价格才能恢复结算"],
            }
            return parameters, impact
        raise AgentConfirmationError("不支持的价目表操作")

    @classmethod
    def _preview_training(
        cls, db: Session, action: str, raw: dict, user_id: int
    ) -> tuple[dict, dict]:
        if action == "training.start":
            request = TrainingTaskCreate(**raw)
            from app.api.training import _build_training_config

            scene = request.scene_id and db.query(DatasetVersion).filter(
                DatasetVersion.id == request.dataset_version_id
            ).first()
            if request.dataset_version_id is None:
                raise AgentConfirmationError("启动训练必须明确已冻结的数据集版本 ID")
            if scene is None:
                raise AgentConfirmationError("数据集版本不存在")
            from app.entity.db_models import DetectionScene

            detection_scene = db.query(DetectionScene).filter(
                DetectionScene.id == request.scene_id
            ).first()
            if detection_scene is None:
                raise AgentConfirmationError("检测场景不存在")
            config = _build_training_config(db, detection_scene, request)
            parameters = request.model_dump(exclude_none=True)
            impact = {
                "title": "启动训练",
                "summary": f"将在数据集 {scene.version} 上创建异步训练任务",
                "target": {
                    "scene_id": request.scene_id,
                    "dataset_version_id": scene.id,
                    "dataset_version": scene.version,
                    "dataset_status": scene.status,
                },
                "changes": {
                    "model_name": request.model_name,
                    "epochs": request.epochs,
                    "batch_size": request.batch_size,
                    "img_size": request.img_size,
                    "device": request.device,
                    "optimizer": request.optimizer,
                    "lr0": request.lr0,
                    "dataset_size": config.get("dataset_size"),
                },
                "warnings": ["训练为异步任务，确认后将占用所配置的远端或本地训练资源"],
            }
            return parameters, impact

        if action == "training.stop":
            task_id = int(raw.get("task_id") or 0)
            task = db.query(TrainingTask).filter(
                TrainingTask.id == task_id, TrainingTask.user_id == user_id
            ).first()
            if task is None:
                raise AgentConfirmationError("训练任务不存在或无权访问")
            if task.status != "running":
                raise AgentConfirmationError(f"训练任务状态为 {task.status}，不能停止")
            parameters = {"task_id": task_id}
            impact = {
                "title": "停止训练",
                "summary": f"将取消训练任务 {task.task_uuid}",
                "target": {"task_id": task.id, "task_uuid": task.task_uuid, "status": task.status},
                "changes": {"status": "running → cancelled", "current_epoch": task.current_epoch, "progress": task.progress},
                "warnings": ["已消耗的训练时间不会恢复，未完成权重可能不可用于发布"],
            }
            return parameters, impact

        if action == "training.set_default_model":
            model_id = int(raw.get("model_version_id") or 0)
            model = db.query(ModelVersion).filter(
                ModelVersion.id == model_id, ModelVersion.status == "active"
            ).first()
            if model is None:
                raise AgentConfirmationError("模型版本不存在或已停用")
            if not Path(model.model_path).is_file():
                raise AgentConfirmationError("目标模型文件不存在")
            current = db.query(ModelVersion).filter(
                ModelVersion.scene_id == model.scene_id,
                ModelVersion.is_default.is_(True),
                ModelVersion.status == "active",
            ).first()
            parameters = {"model_version_id": model_id}
            impact = {
                "title": "切换默认模型",
                "summary": f"场景默认模型将从 {getattr(current, 'version', None) or '未设置'} 切换到 {model.version}",
                "target": model_version_service.serialize(db, model),
                "changes": {
                    "old_model_id": getattr(current, "id", None),
                    "old_model_version": getattr(current, "version", None),
                    "new_model_id": model.id,
                    "new_model_version": model.version,
                },
                "warnings": ["确认后新的检测请求将立即使用目标模型"],
            }
            return parameters, impact
        raise AgentConfirmationError("不支持的训练操作")

    @classmethod
    def _preview(
        cls, db: Session, *, action: str, parameters: dict, user_id: int
    ) -> tuple[dict, dict]:
        if action not in ACTION_META:
            raise AgentConfirmationError("不支持的待确认操作")
        if action.startswith("dataset."):
            return cls._preview_dataset(db, action, parameters)
        if action.startswith("training."):
            return cls._preview_training(db, action, parameters, user_id)
        return cls._preview_catalog(db, action, parameters)

    @classmethod
    def create_preview(
        cls,
        db: Session,
        *,
        user_id: int,
        username: str | None,
        session_uuid: str,
        action: str,
        parameters: dict,
        idempotency_key: str | None = None,
    ) -> dict:
        session = db.query(ChatSession).filter(
            ChatSession.session_uuid == session_uuid,
            ChatSession.user_id == user_id,
            ChatSession.status == "active",
        ).first()
        if session is None:
            raise AgentConfirmationError("对话不存在或已失效", code="not_found")
        normalized, impact = cls._preview(
            db, action=action, parameters=parameters or {}, user_id=user_id
        )
        normalized = _json_safe(normalized)
        impact = _json_safe(impact)
        fingerprint = _fingerprint(action, normalized)

        existing = None
        if idempotency_key:
            existing = db.query(AgentPendingOperation).filter(
                AgentPendingOperation.user_id == user_id,
                AgentPendingOperation.preview_idempotency_key == idempotency_key,
            ).first()
            if existing is not None and existing.request_fingerprint != fingerprint:
                raise AgentConfirmationError("同一幂等键不能用于不同操作", code="idempotency_conflict")
        if existing is None:
            existing = db.query(AgentPendingOperation).filter(
                AgentPendingOperation.user_id == user_id,
                AgentPendingOperation.session_uuid == session_uuid,
                AgentPendingOperation.request_fingerprint == fingerprint,
                AgentPendingOperation.status == "pending",
                AgentPendingOperation.token_expires_at > datetime.now(),
            ).order_by(AgentPendingOperation.created_at.desc()).first()

        if existing is not None:
            existing.impact = impact
            token = cls._issue_token(existing)
            cls._audit(db, existing, username=username, event="confirmation_preview_reused")
            db.commit()
            db.refresh(existing)
            return cls.serialize(existing, confirmation_token=token, replayed=True)

        domain, risk_level, _ = ACTION_META[action]
        operation = AgentPendingOperation(
            operation_uuid=uuid4().hex,
            user_id=user_id,
            session_uuid=session_uuid,
            domain=domain,
            action=action,
            risk_level=risk_level,
            status="pending",
            parameters=normalized,
            impact=impact,
            request_fingerprint=fingerprint,
            preview_idempotency_key=(idempotency_key or None),
            confirmation_token_hash="",
            token_expires_at=datetime.now(),
        )
        token = cls._issue_token(operation)
        db.add(operation)
        db.flush()
        cls._audit(db, operation, username=username, event="confirmation_preview_created")
        db.commit()
        db.refresh(operation)
        return cls.serialize(operation, confirmation_token=token)

    @classmethod
    def get(
        cls, db: Session, *, operation_uuid: str, user_id: int
    ) -> AgentPendingOperation:
        operation = db.query(AgentPendingOperation).filter(
            AgentPendingOperation.operation_uuid == operation_uuid,
            AgentPendingOperation.user_id == user_id,
        ).first()
        if operation is None:
            raise AgentConfirmationError("待确认操作不存在或无权访问", code="not_found")
        cls._expire_if_needed(db, operation)
        return operation

    @classmethod
    def list(
        cls,
        db: Session,
        *,
        user_id: int,
        session_uuid: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        query = db.query(AgentPendingOperation).filter(
            AgentPendingOperation.user_id == user_id
        )
        if session_uuid:
            query = query.filter(AgentPendingOperation.session_uuid == session_uuid)
        if status:
            query = query.filter(AgentPendingOperation.status == status)
        operations = query.order_by(AgentPendingOperation.created_at.desc()).limit(100).all()
        for operation in operations:
            cls._expire_if_needed(db, operation)
        return [cls.serialize(operation) for operation in operations]

    @classmethod
    def rotate_token(
        cls,
        db: Session,
        *,
        operation_uuid: str,
        user_id: int,
        username: str | None,
    ) -> dict:
        operation = cls.get(db, operation_uuid=operation_uuid, user_id=user_id)
        if operation.status != "pending":
            raise AgentConfirmationError("只有待确认操作可以刷新令牌", code="conflict")
        token = cls._issue_token(operation)
        cls._audit(db, operation, username=username, event="confirmation_token_rotated")
        db.commit()
        db.refresh(operation)
        return cls.serialize(operation, confirmation_token=token)

    @classmethod
    def _execute_catalog(cls, db: Session, action: str, p: dict) -> dict:
        dataset_id = int(p["dataset_version_id"])
        product_id = int(p["product_id"])
        mapping = cls._price_mapping(db, dataset_id, product_id)
        price = cls._price_record(db, mapping)
        if action == "catalog.clear_price":
            if price is None:
                raise AgentConfirmationError("价格已被清除，操作状态与预览不一致")
            db.delete(price)
            db.commit()
            return {"dataset_version_id": dataset_id, "product_id": product_id, "cleared": True}

        values = {key: value for key, value in p.items() if key not in {"dataset_version_id", "product_id"}}
        update = ProductPriceUpdate(**values).model_dump(exclude_unset=True)
        if price is None:
            category_id = mapping.category_id
            category_in_use = db.query(ProductPrice).filter(
                ProductPrice.category_id == category_id
            ).first() if category_id is not None else None
            if category_id is None or category_in_use is not None:
                category_id = int(db.query(func.max(ProductPrice.category_id)).scalar() or 0) + 1
            product = db.query(Product).filter(Product.id == product_id).first()
            price = ProductPrice(
                product_id=product_id,
                category_id=category_id,
                sku_name=update.get("sku_name") or getattr(product, "sku_name", None) or mapping.class_name,
                name=update.get("name") or getattr(product, "name", None) or mapping.display_name,
                barcode=update.get("barcode") or getattr(product, "barcode", None),
                unit_price=update["unit_price"],
                currency=update.get("currency") or "CNY",
            )
            db.add(price)
        else:
            if price.product_id is None:
                price.product_id = product_id
            for field, value in update.items():
                setattr(price, field, value)
        db.commit()
        db.refresh(price)
        return {
            "dataset_version_id": dataset_id,
            "product_id": product_id,
            "unit_price": float(price.unit_price),
            "currency": price.currency,
            "updated": True,
        }

    @classmethod
    def _execute(
        cls,
        db: Session,
        operation: AgentPendingOperation,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict:
        action = operation.action
        p = operation.parameters or {}
        if action == "dataset.derive":
            result = dataset_workspace_service.derive(
                db,
                parent_id=int(p["dataset_id"]),
                version=p["version"],
                name=p["name"],
                description=p.get("description"),
                user_id=operation.user_id,
                progress_callback=progress_callback,
            )
            return dataset_service.serialize(result)
        if action == "dataset.freeze":
            result = dataset_service.freeze(
                db,
                dataset_id=int(p["dataset_id"]),
                check_filesystem=bool(p.get("check_filesystem", False)),
            )
            return dataset_service.serialize(result)
        if action == "dataset.archive":
            return dataset_service.serialize(
                dataset_service.archive(db, dataset_id=int(p["dataset_id"]))
            )
        if action == "dataset.delete_draft":
            dataset_id = int(p["dataset_id"])
            dataset_service.delete_draft(
                db,
                dataset_id=dataset_id,
                progress_callback=progress_callback,
            )
            return {"dataset_id": dataset_id, "deleted": True}
        if action == "dataset.delete_product":
            dataset, images, annotations, reindexed = dataset_workspace_service.delete_product(
                db,
                dataset_id=int(p["dataset_id"]),
                product_id=int(p["product_id"]),
                deactivate_product=bool(p.get("deactivate_product", True)),
                progress_callback=progress_callback,
            )
            return {
                "dataset": dataset_service.serialize(dataset),
                "product_id": int(p["product_id"]),
                "images_deleted": images,
                "annotations_deleted": annotations,
                "classes_reindexed": reindexed,
            }
        if action == "training.start":
            request = TrainingTaskCreate(**p)
            from app.api.training import _build_training_config
            from app.entity.db_models import DetectionScene

            scene = db.query(DetectionScene).filter(DetectionScene.id == request.scene_id).first()
            if scene is None:
                raise AgentConfirmationError("检测场景不存在")
            config = _build_training_config(db, scene, request)
            task = training_service.start_training(
                db=db,
                user_id=operation.user_id,
                scene_id=request.scene_id,
                config=config,
            )
            return {
                "task_id": task.id,
                "task_uuid": task.task_uuid,
                "status": task.status,
                "dataset_version_id": task.dataset_version_id,
            }
        if action == "training.stop":
            task_id = int(p["task_id"])
            owned = db.query(TrainingTask).filter(
                TrainingTask.id == task_id,
                TrainingTask.user_id == operation.user_id,
            ).first()
            if owned is None:
                raise AgentConfirmationError("训练任务不存在或无权访问")
            result = training_service.stop_training(db, task_id)
            if result.get("error"):
                raise AgentConfirmationError(result["error"])
            return result
        if action == "training.set_default_model":
            model = model_version_service.set_default(
                db, model_version_id=int(p["model_version_id"])
            )
            return model_version_service.serialize(db, model)
        return cls._execute_catalog(db, action, p)

    @classmethod
    def confirm(
        cls,
        db: Session,
        *,
        operation_uuid: str,
        user_id: int,
        username: str | None,
        confirmation_token: str,
        idempotency_key: str,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict:
        operation = db.query(AgentPendingOperation).filter(
            AgentPendingOperation.operation_uuid == operation_uuid,
            AgentPendingOperation.user_id == user_id,
        ).with_for_update().first()
        if operation is None:
            raise AgentConfirmationError("待确认操作不存在或无权访问", code="not_found")

        if (
            operation.status == "completed"
            and operation.execution_idempotency_key == idempotency_key
        ):
            cls._audit(db, operation, username=username, event="confirmation_replayed")
            db.commit()
            return cls.serialize(operation, replayed=True)
        if operation.status == "pending" and operation.token_expires_at <= datetime.now():
            operation.status = "expired"
            operation.updated_at = datetime.now()
            cls._audit(db, operation, username=username, event="confirmation_expired")
            db.commit()
            raise AgentConfirmationError("确认令牌已过期", code="expired_token")
        if operation.status != "pending":
            raise AgentConfirmationError(
                f"操作当前状态为 {operation.status}，不能再次确认", code="conflict"
            )
        if not confirmation_token or not hmac.compare_digest(
            operation.confirmation_token_hash, _token_hash(confirmation_token)
        ):
            raise AgentConfirmationError("确认令牌无效", code="invalid_token")
        if not idempotency_key or len(idempotency_key) > 100:
            raise AgentConfirmationError("确认请求必须提供有效幂等键")

        operation.status = "executing"
        operation.execution_idempotency_key = idempotency_key
        operation.token_consumed_at = datetime.now()
        cls._audit(db, operation, username=username, event="confirmation_accepted")
        db.commit()

        try:
            result = _json_safe(cls._execute(db, operation, progress_callback=progress_callback))
            operation.status = "completed"
            operation.result = result
            operation.error_message = None
            operation.executed_at = datetime.now()
            cls._audit(db, operation, username=username, event="operation_completed")
            db.commit()
            db.refresh(operation)
            return cls.serialize(operation)
        except Exception as exc:
            db.rollback()
            operation = db.query(AgentPendingOperation).filter(
                AgentPendingOperation.id == operation.id
            ).first()
            operation.status = "failed"
            operation.error_message = str(exc)
            operation.executed_at = datetime.now()
            cls._audit(
                db,
                operation,
                username=username,
                event="operation_failed",
                status="failure",
                detail=str(exc),
            )
            db.commit()
            raise AgentConfirmationError(f"操作执行失败：{exc}", code="execution_failed") from exc

    @classmethod
    def cancel(
        cls,
        db: Session,
        *,
        operation_uuid: str,
        user_id: int,
        username: str | None,
    ) -> dict:
        operation = cls.get(db, operation_uuid=operation_uuid, user_id=user_id)
        if operation.status != "pending":
            raise AgentConfirmationError("只有待确认操作可以取消", code="conflict")
        operation.status = "cancelled"
        operation.token_consumed_at = datetime.now()
        cls._audit(db, operation, username=username, event="operation_cancelled")
        db.commit()
        db.refresh(operation)
        return cls.serialize(operation)


agent_confirmation_service = AgentConfirmationService()
