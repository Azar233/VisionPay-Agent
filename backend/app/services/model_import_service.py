"""Import a ready-to-use YOLO model and synthesize its class catalog."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.entity.db_models import DatasetClassMapping, DatasetVersion, ModelVersion
from app.services.dataset_service import (
    DatasetConflictError,
    DatasetLifecycleError,
    DatasetNotFoundError,
    dataset_service,
)
from app.services.dataset_workspace_service import dataset_workspace_service


class ModelImportService:
    """Create a catalog-only dataset version from the class names embedded in best.pt."""

    @staticmethod
    def _normalize_names(raw_names: Any) -> list[str]:
        if isinstance(raw_names, (list, tuple)):
            names = [str(item).strip() for item in raw_names]
        elif isinstance(raw_names, dict):
            try:
                indexed = {int(key): str(value).strip() for key, value in raw_names.items()}
            except (TypeError, ValueError) as exc:
                raise DatasetLifecycleError("best.pt 的类别索引不是整数") from exc
            if sorted(indexed) != list(range(len(indexed))):
                raise DatasetLifecycleError("best.pt 的类别索引必须从 0 开始连续排列")
            names = [indexed[index] for index in range(len(indexed))]
        else:
            raise DatasetLifecycleError("无法从 best.pt 读取类别名称")
        if not names or any(not name for name in names):
            raise DatasetLifecycleError("best.pt 中没有有效的类别名称")
        return names

    @classmethod
    def _inspect_weights(cls, weights_path: Path) -> tuple[list[str], str]:
        try:
            from ultralytics import YOLO

            model = YOLO(str(weights_path))
        except Exception as exc:  # noqa: BLE001 - convert loader failures to a client error.
            raise DatasetLifecycleError(f"无法加载模型文件，请确认它是有效的 YOLO best.pt：{exc}") from exc
        task = str(getattr(model, "task", "") or "").lower()
        if task and task != "detect":
            raise DatasetLifecycleError(f"仅支持目标检测模型，当前模型任务类型为 {task}")
        return cls._normalize_names(getattr(model, "names", None)), "YOLO"

    @staticmethod
    def _validate_version(version: str) -> str:
        normalized = (version or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,49}", normalized):
            raise DatasetLifecycleError("版本号只能包含字母、数字、点、下划线和连字符，最长 50 位")
        return normalized

    @staticmethod
    def _write_catalog_files(
        target: Path,
        *,
        names: list[str],
        weights_sha256: str,
        source_name: str,
    ) -> None:
        (target / "data.yaml").write_text(
            yaml.safe_dump(
                {
                    "path": str(target),
                    "train": None,
                    "val": None,
                    "test": None,
                    "nc": len(names),
                    "names": {index: name for index, name in enumerate(names)},
                    "catalog_only": True,
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (target / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source": "imported_model",
                    "catalog_only": True,
                    "weights": {
                        "filename": "best.pt",
                        "source_name": source_name,
                        "sha256": weights_sha256,
                    },
                    "classes": [
                        {"class_index": index, "class_name": name}
                        for index, name in enumerate(names)
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def import_available_model(
        cls,
        db: Session,
        *,
        scene_id: int,
        source_path: str | Path,
        source_name: str,
        version: str,
        name: str,
        description: str | None,
        set_current: bool,
        set_default: bool,
        user_id: int,
    ) -> tuple[DatasetVersion, ModelVersion]:
        scene = dataset_service._ensure_scene(db, scene_id)
        version = cls._validate_version(version)
        display_name = (name or "").strip()
        if not display_name:
            raise DatasetLifecycleError("请输入显示名称")

        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise DatasetNotFoundError(f"模型文件不存在: {source_path}")
        if source.suffix.lower() != ".pt":
            raise DatasetLifecycleError("模型文件必须是 .pt 格式")
        max_bytes = settings.MODEL_IMPORT_MAX_FILE_MB * 1024 * 1024
        if source.stat().st_size > max_bytes:
            raise DatasetLifecycleError(
                f"模型文件超过 {settings.MODEL_IMPORT_MAX_FILE_MB} MB 限制"
            )
        if db.query(DatasetVersion).filter_by(scene_id=scene_id, version=version).first():
            raise DatasetConflictError("同一场景下的数据集版本号不能重复")
        if db.query(ModelVersion).filter_by(scene_id=scene_id, version=version).first():
            raise DatasetConflictError("同一场景下的模型版本号不能重复")

        names, model_type = cls._inspect_weights(source)
        target = dataset_workspace_service._target(scene_id, version)
        if target.exists():
            raise DatasetConflictError(f"版本目录已存在: {target}")

        weights_sha256 = dataset_workspace_service._hash_file(source)
        checked_at = datetime.now()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.mkdir()
            managed_weights = target / "best.pt"
            shutil.copy2(source, managed_weights)
            cls._write_catalog_files(
                target,
                names=names,
                weights_sha256=weights_sha256,
                source_name=source_name,
            )

            dataset = DatasetVersion(
                scene_id=scene_id,
                version=version,
                name=display_name,
                description=description or "由可用 YOLO 模型导入的类别目录版本。",
                status="ready",
                is_current=False,
                storage_path=str(target),
                data_yaml_path="data.yaml",
                manifest_path="manifest.json",
                content_hash=f"sha256:{weights_sha256}",
                class_count=len(names),
                created_by=user_id,
                extra_metadata={
                    "source": "imported_model",
                    "catalog_only": True,
                    "weights_file": "best.pt",
                    "weights_sha256": weights_sha256,
                    "source_name": source_name,
                },
                validation_report={
                    "valid": True,
                    "errors": [],
                    "warnings": ["该版本由模型导入，仅包含类别目录，不包含训练图片与标注。"],
                    "checked_filesystem": True,
                    "checked_at": checked_at.isoformat(),
                },
                validated_at=checked_at,
                frozen_at=checked_at,
            )
            db.add(dataset)
            db.flush()

            for class_index, class_name in enumerate(names):
                category_id = class_index + 1
                product = dataset_workspace_service._ensure_product(
                    db,
                    scene_id=scene_id,
                    class_name=class_name,
                    category_id=category_id,
                )
                db.add(
                    DatasetClassMapping(
                        dataset_version_id=dataset.id,
                        class_index=class_index,
                        product_id=product.id,
                        product_key=product.product_key,
                        category_id=category_id,
                        class_name=class_name,
                        display_name=product.name,
                        extra_metadata={"source": "imported_model"},
                    )
                )

            has_current = (
                db.query(DatasetVersion)
                .filter(DatasetVersion.scene_id == scene_id, DatasetVersion.is_current.is_(True))
                .first()
                is not None
            )
            if set_current or not has_current:
                db.query(DatasetVersion).filter(
                    DatasetVersion.scene_id == scene_id,
                    DatasetVersion.id != dataset.id,
                ).update({"is_current": False}, synchronize_session=False)
                dataset.is_current = True

            has_default = (
                db.query(ModelVersion)
                .filter(ModelVersion.scene_id == scene_id, ModelVersion.is_default.is_(True))
                .first()
                is not None
            )
            if set_default or not has_default:
                db.query(ModelVersion).filter(ModelVersion.scene_id == scene_id).update(
                    {"is_default": False},
                    synchronize_session=False,
                )
            model_version = ModelVersion(
                scene_id=scene_id,
                training_task_id=None,
                dataset_version_id=dataset.id,
                version=version,
                model_name=display_name,
                model_type=model_type,
                status="active",
                model_path=str(managed_weights),
                description=description or "手动导入的可用 YOLO best.pt。",
                file_size=managed_weights.stat().st_size,
                is_default=set_default or not has_default,
            )
            db.add(model_version)
            scene.class_names = names
            db.commit()
            db.refresh(dataset)
            db.refresh(model_version)
            return dataset, model_version
        except Exception:
            db.rollback()
            shutil.rmtree(target, ignore_errors=True)
            raise


model_import_service = ModelImportService()
