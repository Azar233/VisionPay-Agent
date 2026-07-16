"""Detection model registry bound to training and dataset versions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.entity.db_models import DetectionScene, ModelVersion, TrainingMetric, TrainingTask

BACKEND_ROOT = Path(__file__).resolve().parents[2]
BUILTIN_VERSION = "正式版v1.0"


class ModelVersionService:
    @staticmethod
    def _builtin_path() -> Path:
        return (BACKEND_ROOT / "best.pt").resolve()

    @classmethod
    def ensure_builtin(cls, db: Session, *, scene_id: int | None = None) -> list[ModelVersion]:
        """Register backend/best.pt once per active scene without overriding later choices."""

        model_path = cls._builtin_path()
        if not model_path.is_file():
            return []
        query = db.query(DetectionScene).filter(DetectionScene.is_active.is_(True))
        if scene_id is not None:
            query = query.filter(DetectionScene.id == scene_id)
        created: list[ModelVersion] = []
        for scene in query.order_by(DetectionScene.id).all():
            existing = (
                db.query(ModelVersion)
                .filter(
                    ModelVersion.scene_id == scene.id,
                    ModelVersion.version == BUILTIN_VERSION,
                    ModelVersion.training_task_id.is_(None),
                )
                .first()
            )
            if existing is not None:
                if existing.model_path != str(model_path) or existing.file_size != model_path.stat().st_size:
                    existing.model_path = str(model_path)
                    existing.file_size = model_path.stat().st_size
                continue

            # Preserve an already selected imported/trained model. The builtin
            # file becomes the default only when the scene has no default yet.
            has_default = (
                db.query(ModelVersion)
                .filter(ModelVersion.scene_id == scene.id, ModelVersion.is_default.is_(True))
                .first()
                is not None
            )
            model = ModelVersion(
                scene_id=scene.id,
                training_task_id=None,
                dataset_version_id=None,
                version=BUILTIN_VERSION,
                model_name="backend/best.pt",
                model_type="YOLO",
                status="active",
                model_path=str(model_path),
                description="系统原有正式检测模型，由 backend/best.pt 自动登记。",
                file_size=model_path.stat().st_size,
                is_default=not has_default,
            )
            db.add(model)
            created.append(model)
        if created or db.dirty:
            db.commit()
            for model in created:
                db.refresh(model)
        return created

    @staticmethod
    def _latest_metric(db: Session, task_id: int | None) -> TrainingMetric | None:
        if task_id is None:
            return None
        return (
            db.query(TrainingMetric)
            .filter(TrainingMetric.task_id == task_id)
            .order_by(TrainingMetric.epoch.desc())
            .first()
        )

    @classmethod
    def serialize(cls, db: Session, model: ModelVersion) -> dict[str, Any]:
        task: TrainingTask | None = model.training_task
        dataset = model.dataset_version
        metric = cls._latest_metric(db, model.training_task_id)
        return {
            "id": model.id,
            "scene_id": model.scene_id,
            "scene_name": getattr(model.scene, "display_name", None) or getattr(model.scene, "name", None),
            "training_task_id": model.training_task_id,
            "training_task_uuid": getattr(task, "task_uuid", None),
            "dataset_version_id": model.dataset_version_id,
            "dataset_version": getattr(dataset, "version", None),
            "dataset_name": getattr(dataset, "name", None),
            "dataset_content_hash": getattr(task, "dataset_content_hash", None),
            "version": model.version,
            "model_name": model.model_name,
            "model_type": model.model_type,
            "status": model.status,
            "model_path": model.model_path,
            "file_exists": Path(model.model_path).is_file(),
            "file_size": model.file_size,
            "is_default": bool(model.is_default),
            "description": model.description,
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "training_parameters": None if task is None else {
                "model_name": task.model_name,
                "epochs": task.epochs,
                "img_size": task.img_size,
                "batch_size": task.batch_size,
                "device": task.device,
                "optimizer": task.optimizer,
                "lr0": task.lr0,
                "augment_config": task.augment_config,
            },
            "training_result": None if task is None else {
                "status": task.status,
                "current_epoch": task.current_epoch,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "precision": model.precision if model.precision is not None else getattr(metric, "precision", None),
                "recall": model.recall if model.recall is not None else getattr(metric, "recall", None),
                "map50": model.map50 if model.map50 is not None else getattr(metric, "map50", None),
                "map50_95": model.map50_95 if model.map50_95 is not None else getattr(metric, "map50_95", None),
                "box_loss": getattr(metric, "box_loss", None),
                "cls_loss": getattr(metric, "cls_loss", None),
                "dfl_loss": getattr(metric, "dfl_loss", None),
            },
        }

    @classmethod
    def list(cls, db: Session, *, scene_id: int | None = None) -> list[dict[str, Any]]:
        cls.ensure_builtin(db, scene_id=scene_id)
        query = db.query(ModelVersion).filter(ModelVersion.status == "active")
        if scene_id is not None:
            query = query.filter(ModelVersion.scene_id == scene_id)
        models = query.order_by(ModelVersion.scene_id, ModelVersion.is_default.desc(), ModelVersion.created_at.desc()).all()
        return [cls.serialize(db, model) for model in models]

    @classmethod
    def set_default(cls, db: Session, *, model_version_id: int) -> ModelVersion:
        model = db.query(ModelVersion).filter(ModelVersion.id == model_version_id).first()
        if model is None or model.status != "active":
            raise ValueError("模型版本不存在或已停用")
        if not Path(model.model_path).is_file():
            raise ValueError(f"模型文件不存在: {model.model_path}")
        db.query(ModelVersion).filter(ModelVersion.scene_id == model.scene_id).update(
            {"is_default": False},
            synchronize_session=False,
        )
        model.is_default = True
        db.commit()
        db.refresh(model)
        return model

    @classmethod
    def register_training_output(
        cls,
        db: Session,
        *,
        task: TrainingTask,
        weights_path: Path,
    ) -> ModelVersion | None:
        if task.status != "completed" or not weights_path.is_file():
            return None
        existing = (
            db.query(ModelVersion)
            .filter(ModelVersion.training_task_id == task.id)
            .order_by(ModelVersion.id)
            .first()
        )
        metric = cls._latest_metric(db, task.id)
        if existing is None:
            has_default = (
                db.query(ModelVersion)
                .filter(ModelVersion.scene_id == task.scene_id, ModelVersion.is_default.is_(True))
                .first()
                is not None
            )
            existing = ModelVersion(
                scene_id=task.scene_id,
                training_task_id=task.id,
                dataset_version_id=task.dataset_version_id,
                version=f"训练-{task.task_uuid}",
                model_name=f"{task.model_name} / {task.task_uuid}",
                model_type=task.model_name,
                status="active",
                model_path=str(weights_path.resolve()),
                description="训练完成后自动登记的 best.pt。",
                is_default=not has_default,
            )
            db.add(existing)
        existing.dataset_version_id = task.dataset_version_id
        existing.model_path = str(weights_path.resolve())
        existing.file_size = weights_path.stat().st_size
        if metric is not None:
            existing.precision = metric.precision
            existing.recall = metric.recall
            existing.map50 = metric.map50
            existing.map50_95 = metric.map50_95
        db.commit()
        db.refresh(existing)
        return existing


model_version_service = ModelVersionService()
