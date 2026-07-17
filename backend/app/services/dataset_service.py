"""Dataset version registry and lifecycle rules.

This module intentionally does not start training jobs or inspect the local
development dataset automatically. Real cluster directories are registered
explicitly and filesystem checks are opt-in.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.entity.db_models import (
    DatasetAnnotation,
    DatasetClassMapping,
    DatasetImage,
    DatasetVersion,
    DetectionScene,
    ModelVersion,
    TrainingTask,
)
from app.entity.schemas import DatasetVersionCreate, DatasetVersionUpdate

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATASET_STATUSES = {"draft", "pending_train", "training", "published", "archived"}


class DatasetNotFoundError(ValueError):
    pass


class DatasetConflictError(ValueError):
    pass


class DatasetLifecycleError(ValueError):
    pass


class DatasetService:
    @staticmethod
    def get(db: Session, dataset_id: int) -> DatasetVersion:
        dataset = db.query(DatasetVersion).filter(DatasetVersion.id == dataset_id).first()
        if dataset is None:
            raise DatasetNotFoundError("数据集版本不存在")
        return dataset

    @staticmethod
    def _ensure_scene(db: Session, scene_id: int) -> DetectionScene:
        scene = db.query(DetectionScene).filter(DetectionScene.id == scene_id).first()
        if scene is None:
            raise DatasetNotFoundError("检测场景不存在")
        return scene

    @classmethod
    def _ensure_parent(
        cls,
        db: Session,
        scene_id: int,
        parent_id: int | None,
        dataset_id: int | None = None,
    ) -> DatasetVersion | None:
        if parent_id is None:
            return None
        if dataset_id is not None and parent_id == dataset_id:
            raise DatasetLifecycleError("数据集版本不能将自己设为父版本")
        parent = cls.get(db, parent_id)
        if parent.scene_id != scene_id:
            raise DatasetLifecycleError("父版本必须属于同一检测场景")
        return parent

    @staticmethod
    def _replace_classes(
        dataset: DatasetVersion,
        class_items: list[Any],
    ) -> None:
        indexes = [item.class_index for item in class_items]
        product_keys = [item.product_key for item in class_items]
        if len(indexes) != len(set(indexes)):
            raise DatasetConflictError("同一数据集版本内 class_index 不能重复")
        if len(product_keys) != len(set(product_keys)):
            raise DatasetConflictError("同一数据集版本内 product_key 不能重复")
        dataset.classes.clear()
        for item in class_items:
            values = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            dataset.classes.append(DatasetClassMapping(**values))

    @staticmethod
    def serialize(dataset: DatasetVersion, *, include_classes: bool = True) -> dict[str, Any]:
        scene = getattr(dataset, "scene", None)
        parent = getattr(dataset, "parent", None)
        creator = getattr(dataset, "creator", None)
        tasks = sorted(
            list(getattr(dataset, "training_tasks", []) or []),
            key=lambda item: (item.created_at or datetime.min, item.id or 0),
            reverse=True,
        )
        model_versions = list(getattr(dataset, "model_versions", []) or [])
        task_statuses = {item.status for item in tasks}
        completed_training_count = sum(item.status == "completed" for item in tasks)
        if "running" in task_statuses:
            training_status = "training"
        elif "pending" in task_statuses:
            training_status = "queued"
        elif completed_training_count or model_versions:
            training_status = "trained"
        elif tasks:
            training_status = "failed"
        else:
            training_status = "untrained"
        latest_task = tasks[0] if tasks else None

        session = Session.object_session(dataset)
        default_model = None
        if session is not None:
            default_model = (
                session.query(ModelVersion)
                .filter(
                    ModelVersion.scene_id == dataset.scene_id,
                    ModelVersion.status == "active",
                    ModelVersion.is_default.is_(True),
                )
                .first()
            )
        active_model_count = sum(
            1 for model in model_versions if model.status == "active"
        )
        running_training_count = sum(
            1 for task in tasks if task.status == "running"
        )
        is_in_use = (
            default_model is not None
            and default_model.dataset_version_id == dataset.id
        )

        result = {
            "id": dataset.id,
            "scene_id": dataset.scene_id,
            "scene_name": getattr(scene, "display_name", None) or getattr(scene, "name", None),
            "parent_id": dataset.parent_id,
            "parent_version": getattr(parent, "version", None),
            "version": dataset.version,
            "name": dataset.name,
            "description": dataset.description,
            "status": dataset.status,
            "is_current": bool(dataset.is_current),
            "is_in_use": is_in_use,
            "storage_path": dataset.storage_path,
            "data_yaml_path": dataset.data_yaml_path,
            "manifest_path": dataset.manifest_path,
            "content_hash": dataset.content_hash,
            "class_count": dataset.class_count,
            "train_image_count": dataset.train_image_count,
            "val_image_count": dataset.val_image_count,
            "test_image_count": dataset.test_image_count,
            "total_image_count": (
                dataset.train_image_count + dataset.val_image_count + dataset.test_image_count
            ),
            "train_annotation_count": dataset.train_annotation_count,
            "val_annotation_count": dataset.val_annotation_count,
            "test_annotation_count": dataset.test_annotation_count,
            "total_annotation_count": (
                dataset.train_annotation_count
                + dataset.val_annotation_count
                + dataset.test_annotation_count
            ),
            "extra_metadata": dataset.extra_metadata,
            "validation_report": dataset.validation_report,
            "created_by": dataset.created_by,
            "creator_name": getattr(creator, "username", None),
            "created_at": dataset.created_at,
            "updated_at": dataset.updated_at,
            "validated_at": dataset.validated_at,
            "frozen_at": dataset.frozen_at,
            "archived_at": dataset.archived_at,
            "training_status": training_status,
            "training_task_count": len(tasks),
            "completed_training_count": completed_training_count,
            "latest_training_task_id": getattr(latest_task, "id", None),
            "latest_training_task_uuid": getattr(latest_task, "task_uuid", None),
            "latest_training_status": getattr(latest_task, "status", None),
            "model_version_count": len(model_versions),
            "active_model_count": active_model_count,
            "running_training_count": running_training_count,
            "classes": [],
        }
        if include_classes:
            result["classes"] = [
                {
                    "id": mapping.id,
                    "class_index": mapping.class_index,
                    "product_id": mapping.product_id,
                    "product_key": mapping.product_key,
                    "category_id": mapping.category_id,
                    "class_name": mapping.class_name,
                    "display_name": mapping.display_name,
                    "extra_metadata": mapping.extra_metadata,
                }
                for mapping in dataset.classes
            ]
        return result

    @classmethod
    def list(
        cls,
        db: Session,
        *,
        scene_id: int | None = None,
        status: str | None = None,
        current_only: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        query = db.query(DatasetVersion)
        if scene_id is not None:
            query = query.filter(DatasetVersion.scene_id == scene_id)
        if status is not None:
            if status not in DATASET_STATUSES:
                raise DatasetLifecycleError("不支持的数据集状态")
            query = query.filter(DatasetVersion.status == status)
        if current_only:
            query = query.filter(DatasetVersion.is_current.is_(True))

        total = query.count()
        items = (
            query.order_by(DatasetVersion.created_at.desc(), DatasetVersion.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "total": total,
            "items": [cls.serialize(item, include_classes=False) for item in items],
        }

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        payload: DatasetVersionCreate,
        user_id: int,
    ) -> DatasetVersion:
        cls._ensure_scene(db, payload.scene_id)
        cls._ensure_parent(db, payload.scene_id, payload.parent_id)
        duplicate = (
            db.query(DatasetVersion)
            .filter(
                DatasetVersion.scene_id == payload.scene_id,
                DatasetVersion.version == payload.version,
            )
            .first()
        )
        if duplicate:
            raise DatasetConflictError("同一场景下的数据集版本号不能重复")

        values = payload.model_dump(exclude={"classes"})
        dataset = DatasetVersion(**values, status="draft", is_current=False, created_by=user_id)
        cls._replace_classes(dataset, payload.classes)
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        return dataset

    @classmethod
    def update(
        cls,
        db: Session,
        *,
        dataset_id: int,
        payload: DatasetVersionUpdate,
    ) -> DatasetVersion:
        dataset = cls.get(db, dataset_id)
        if dataset.status != "draft":
            raise DatasetLifecycleError("只有草稿数据集可以修改")

        changes = payload.model_dump(exclude_unset=True)
        classes = changes.pop("classes", None)
        parent_id = changes.get("parent_id", dataset.parent_id)
        cls._ensure_parent(db, dataset.scene_id, parent_id, dataset.id)

        version = changes.get("version")
        if version and version != dataset.version:
            duplicate = (
                db.query(DatasetVersion)
                .filter(
                    DatasetVersion.scene_id == dataset.scene_id,
                    DatasetVersion.version == version,
                    DatasetVersion.id != dataset.id,
                )
                .first()
            )
            if duplicate:
                raise DatasetConflictError("同一场景下的数据集版本号不能重复")

        for field, value in changes.items():
            setattr(dataset, field, value)
        if classes is not None:
            cls._replace_classes(dataset, classes)
        dataset.validation_report = None
        dataset.validated_at = None
        db.commit()
        db.refresh(dataset)
        return dataset

    @staticmethod
    def _resolve_local_path(value: str, *, root: Path | None = None) -> Path | None:
        if "://" in value:
            return None
        path = Path(value).expanduser()
        if path.is_absolute():
            return path.resolve()
        return ((root or BACKEND_ROOT) / path).resolve()

    @classmethod
    def validate(
        cls,
        db: Session,
        *,
        dataset_id: int,
        check_filesystem: bool = False,
    ) -> dict[str, Any]:
        dataset = cls.get(db, dataset_id)
        errors: list[str] = []
        warnings: list[str] = []

        mappings = list(dataset.classes)
        if dataset.class_count <= 0:
            errors.append("class_count 必须大于 0")
        if len(mappings) != dataset.class_count:
            errors.append(
                f"类别映射数量 {len(mappings)} 与 class_count={dataset.class_count} 不一致"
            )
        indexes = [item.class_index for item in mappings]
        if indexes != list(range(dataset.class_count)):
            errors.append("class_index 必须从 0 开始连续排列")
        product_keys = [item.product_key for item in mappings]
        if len(product_keys) != len(set(product_keys)):
            errors.append("同一数据集版本内 product_key 不能重复")
        product_ids = [item.product_id for item in mappings if item.product_id is not None]
        if len(product_ids) != len(set(product_ids)):
            errors.append("同一数据集版本内 product_id 不能重复")
        if product_ids and len(product_ids) != len(mappings):
            errors.append("product_id 必须为全部类别同时配置，不能部分缺失")

        catalog_only = bool((dataset.extra_metadata or {}).get("catalog_only"))
        if catalog_only:
            warnings.append("该版本由可用模型生成，仅包含类别目录，不包含训练图片与标注")
        else:
            if dataset.train_image_count <= 0:
                errors.append("训练集图片数量必须大于 0")
            if dataset.val_image_count <= 0:
                errors.append("验证集图片数量必须大于 0")
            if dataset.test_image_count <= 0:
                errors.append("测试集图片数量必须大于 0")
            if dataset.train_annotation_count <= 0:
                errors.append("训练集标注数量必须大于 0")
            if dataset.val_annotation_count <= 0:
                errors.append("验证集标注数量必须大于 0")
            if dataset.test_annotation_count <= 0:
                errors.append("测试集标注数量必须大于 0")
        if not dataset.content_hash:
            errors.append("冻结前必须填写 content_hash")

        if check_filesystem:
            storage_root = cls._resolve_local_path(dataset.storage_path)
            remote_storage = storage_root is None and "://" in dataset.storage_path
            if storage_root is None:
                warnings.append("storage_path 是远程 URI，跳过本地目录检查")
            elif not storage_root.is_dir():
                errors.append(f"数据集目录不存在: {storage_root}")

            yaml_value = Path(dataset.data_yaml_path).expanduser()
            yaml_path = (
                None
                if remote_storage and not yaml_value.is_absolute()
                else cls._resolve_local_path(
                    dataset.data_yaml_path,
                    root=storage_root if storage_root and storage_root.is_dir() else None,
                )
            )
            if yaml_path is None:
                warnings.append("data_yaml_path 是远程 URI，跳过本地文件检查")
            elif not yaml_path.is_file():
                errors.append(f"data.yaml 不存在: {yaml_path}")

            if dataset.manifest_path:
                manifest_value = Path(dataset.manifest_path).expanduser()
                manifest_path = (
                    None
                    if remote_storage and not manifest_value.is_absolute()
                    else cls._resolve_local_path(
                        dataset.manifest_path,
                        root=storage_root if storage_root and storage_root.is_dir() else None,
                    )
                )
                if manifest_path is None:
                    warnings.append("manifest_path 是远程 URI，跳过本地文件检查")
                elif not manifest_path.is_file():
                    errors.append(f"manifest 不存在: {manifest_path}")

        checked_at = datetime.now()
        report = {
            "dataset_id": dataset.id,
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "checked_filesystem": check_filesystem,
            "checked_at": checked_at,
        }
        dataset.validation_report = {
            **report,
            "checked_at": checked_at.isoformat(),
        }
        dataset.validated_at = checked_at
        db.commit()
        return report

    @classmethod
    def freeze(
        cls,
        db: Session,
        *,
        dataset_id: int,
        check_filesystem: bool = False,
    ) -> DatasetVersion:
        dataset = cls.get(db, dataset_id)
        if dataset.status != "draft":
            raise DatasetLifecycleError("只有草稿数据集可以冻结")
        report = cls.validate(
            db,
            dataset_id=dataset_id,
            check_filesystem=check_filesystem,
        )
        if not report["valid"]:
            raise DatasetLifecycleError("数据集校验未通过：" + "；".join(report["errors"]))

        dataset = cls.get(db, dataset_id)
        dataset.status = "pending_train"
        dataset.frozen_at = datetime.now()
        db.commit()
        db.refresh(dataset)
        return dataset

    @classmethod
    def set_current(cls, db: Session, *, dataset_id: int) -> DatasetVersion:
        dataset = cls.get(db, dataset_id)
        if dataset.status not in {"pending_train", "training", "published"}:
            raise DatasetLifecycleError("只有已冻结的数据集可以设为当前版本")
        db.query(DatasetVersion).filter(
            DatasetVersion.scene_id == dataset.scene_id,
            DatasetVersion.id != dataset.id,
        ).update({"is_current": False}, synchronize_session=False)
        dataset.is_current = True
        db.commit()
        db.refresh(dataset)
        return dataset

    @classmethod
    def _pick_replacement_default_model(
        cls,
        db: Session,
        scene_id: int,
        exclude_model_ids: list[int] | None = None,
    ) -> ModelVersion | None:
        query = db.query(ModelVersion).filter(
            ModelVersion.scene_id == scene_id,
            ModelVersion.status == "active",
        )
        if exclude_model_ids:
            query = query.filter(ModelVersion.id.notin_(exclude_model_ids))
        candidates = query.order_by(
            ModelVersion.is_default.desc(),
            ModelVersion.created_at.desc(),
        ).all()
        return next(
            (model for model in candidates if Path(model.model_path).expanduser().is_file()),
            None,
        )

    @classmethod
    def _pick_replacement_current_dataset(
        cls,
        db: Session,
        scene_id: int,
        exclude_dataset_id: int | None = None,
        preferred_dataset_id: int | None = None,
    ) -> DatasetVersion | None:
        ready_statuses = {"pending_train", "training", "published"}
        if preferred_dataset_id is not None:
            preferred = db.query(DatasetVersion).filter(
                DatasetVersion.id == preferred_dataset_id,
                DatasetVersion.scene_id == scene_id,
                DatasetVersion.status.in_(ready_statuses),
            ).first()
            if preferred is not None:
                return preferred
        query = db.query(DatasetVersion).filter(
            DatasetVersion.scene_id == scene_id,
            DatasetVersion.status.in_(ready_statuses),
        )
        if exclude_dataset_id is not None:
            query = query.filter(DatasetVersion.id != exclude_dataset_id)
        return query.order_by(
            DatasetVersion.frozen_at.desc(),
            DatasetVersion.created_at.desc(),
        ).first()

    @classmethod
    def archive(
        cls,
        db: Session,
        *,
        dataset_id: int,
        actor_user_id: int | None = None,
        actor_username: str | None = None,
    ) -> DatasetVersion:
        dataset = cls.get(db, dataset_id)
        if dataset.status not in {"pending_train", "training", "published"}:
            raise DatasetLifecycleError("只有已冻结的数据集可以归档")

        from app.services.model_version_service import model_version_service

        model_version_service.ensure_builtin(db, scene_id=dataset.scene_id)

        linked_models = [
            model for model in (dataset.model_versions or []) if model.status == "active"
        ]
        linked_ids = [model.id for model in linked_models]
        archived_default = any(model.is_default for model in linked_models)
        for model in linked_models:
            model.status = "archived"
            model.is_default = False
            model_version_service.record_event(
                db,
                model,
                action="archive",
                user_id=actor_user_id,
                username=actor_username,
                detail=f"归档数据集版本 {dataset.version} 时联动归档模型。",
            )

        replacement_model = None
        if archived_default:
            replacement_model = cls._pick_replacement_default_model(
                db,
                scene_id=dataset.scene_id,
                exclude_model_ids=linked_ids,
            )
            if replacement_model is not None:
                replacement_model.is_default = True
                model_version_service.record_event(
                    db,
                    replacement_model,
                    action="auto_set_default",
                    user_id=actor_user_id,
                    username=actor_username,
                    detail=f"数据集 {dataset.version} 归档后自动接替默认模型。",
                )

        preferred_dataset_id = None
        if (
            replacement_model is not None
            and replacement_model.dataset_version_id is not None
            and replacement_model.dataset_version_id != dataset.id
        ):
            preferred_dataset_id = replacement_model.dataset_version_id

        replacement_dataset = cls._pick_replacement_current_dataset(
            db,
            scene_id=dataset.scene_id,
            exclude_dataset_id=dataset.id,
            preferred_dataset_id=preferred_dataset_id,
        )
        db.query(DatasetVersion).filter(
            DatasetVersion.scene_id == dataset.scene_id,
        ).update({"is_current": False}, synchronize_session=False)
        if replacement_dataset is not None:
            replacement_dataset.is_current = True

        dataset.status = "archived"
        dataset.is_current = False
        dataset.archived_at = datetime.now()
        db.commit()
        db.refresh(dataset)
        return dataset

    @classmethod
    def sync_dataset_status(cls, db: Session, dataset_id: int | None) -> None:
        if dataset_id is None:
            return
        dataset = db.query(DatasetVersion).filter(DatasetVersion.id == dataset_id).first()
        if dataset is None:
            return
        if dataset.status in {"draft", "archived"}:
            return
        has_running_training = (
            db.query(TrainingTask)
            .filter(
                TrainingTask.dataset_version_id == dataset_id,
                TrainingTask.status == "running",
            )
            .first()
            is not None
        )
        if has_running_training:
            dataset.status = "training"
        else:
            has_active_model = (
                db.query(ModelVersion)
                .filter(
                    ModelVersion.dataset_version_id == dataset_id,
                    ModelVersion.status == "active",
                )
                .first()
                is not None
            )
            if has_active_model:
                dataset.status = "published"
            else:
                dataset.status = "pending_train"
        db.commit()
        db.refresh(dataset)

    @classmethod
    def set_current_from_model(cls, db: Session, model_version: ModelVersion) -> None:
        if model_version.dataset_version_id is None:
            return
        dataset = db.query(DatasetVersion).filter(
            DatasetVersion.id == model_version.dataset_version_id,
        ).first()
        if dataset is None or dataset.status == "archived":
            return
        db.query(DatasetVersion).filter(
            DatasetVersion.scene_id == model_version.scene_id,
            DatasetVersion.id != dataset.id,
        ).update({"is_current": False}, synchronize_session=False)
        dataset.is_current = True
        db.commit()
        db.refresh(dataset)

    @classmethod
    def delete_draft(
        cls,
        db: Session,
        *,
        dataset_id: int,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> None:
        if progress_callback is not None:
            progress_callback(5, "正在检查草稿状态与派生关系")
        dataset = cls.get(db, dataset_id)
        if dataset.status != "draft" or dataset.is_current:
            raise DatasetLifecycleError("只能删除未启用的草稿数据集")
        if dataset.children:
            raise DatasetLifecycleError("存在派生版本，不能删除该草稿")
        if progress_callback is not None:
            progress_callback(10, "正在统计数据库中的图片与标注索引")
        image_ids = [
            row_id
            for (row_id,) in db.query(DatasetImage.id)
            .filter(DatasetImage.dataset_version_id == dataset.id)
            .order_by(DatasetImage.id)
            .all()
        ]
        batch_size = 250
        total_images = max(1, len(image_ids))
        for offset in range(0, len(image_ids), batch_size):
            batch = image_ids[offset : offset + batch_size]
            db.query(DatasetAnnotation).filter(DatasetAnnotation.dataset_image_id.in_(batch)).delete(
                synchronize_session=False
            )
            db.query(DatasetImage).filter(DatasetImage.id.in_(batch)).delete(synchronize_session=False)
            db.flush()
            deleted_count = min(offset + len(batch), len(image_ids))
            if progress_callback is not None:
                progress_callback(
                    12 + round(deleted_count / total_images * 63),
                    f"正在删除图片与标注索引 {deleted_count}/{len(image_ids)}",
                )
        if progress_callback is not None:
            progress_callback(78, "正在删除草稿版本与商品映射")
        db.expire(dataset, ["images"])
        db.delete(dataset)
        db.flush()
        if progress_callback is not None:
            progress_callback(85, "正在提交草稿删除结果")
        db.commit()
        if progress_callback is not None:
            progress_callback(100, "草稿已删除")


dataset_service = DatasetService()
