"""Managed YOLO dataset workspaces with stable product identities."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.entity.db_models import (
    DatasetAnnotation,
    DatasetClassMapping,
    DatasetImage,
    DatasetVersion,
    Product,
    ProductPrice,
)
from app.services.dataset_service import (
    BACKEND_ROOT,
    DatasetConflictError,
    DatasetLifecycleError,
    DatasetNotFoundError,
    dataset_service,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
SPLITS = ("train", "val", "test")


class DatasetWorkspaceService:
    @staticmethod
    def _local_root(dataset: DatasetVersion) -> Path:
        root = dataset_service._resolve_local_path(dataset.storage_path)
        if root is None or not root.is_dir():
            raise DatasetLifecycleError("数据集版本必须位于后端可访问的本地或挂载目录")
        return root

    @staticmethod
    def _version_root() -> Path:
        root = Path(settings.DATASET_VERSION_ROOT).expanduser()
        return root.resolve() if root.is_absolute() else (BACKEND_ROOT / root).resolve()

    @classmethod
    def _target(cls, scene_id: int, version: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", version).strip("._")
        return cls._version_root() / f"scene_{scene_id}" / safe

    @staticmethod
    def _yaml_names(root: Path) -> list[str]:
        yaml_path = root / "data.yaml"
        if not yaml_path.is_file():
            raise DatasetLifecycleError(f"data.yaml 不存在: {yaml_path}")
        payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        names = payload.get("names")
        if isinstance(names, list):
            result = [str(item) for item in names]
        elif isinstance(names, dict):
            result = [str(names[key]) for key in sorted(names, key=lambda value: int(value))]
        else:
            raise DatasetLifecycleError("data.yaml 缺少 names")
        if int(payload.get("nc", len(result))) != len(result):
            raise DatasetLifecycleError("data.yaml 的 nc 与 names 数量不一致")
        return result

    @staticmethod
    def _stable_key(scene_id: int, class_name: str, legacy_category_id: int) -> str:
        value = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"visionpay:{scene_id}:{legacy_category_id}:{class_name}",
        )
        return f"prod:{value}"

    @classmethod
    def _ensure_product(
        cls,
        db: Session,
        *,
        scene_id: int,
        class_name: str,
        category_id: int,
    ) -> Product:
        price = db.query(ProductPrice).filter(ProductPrice.category_id == category_id).first()
        barcode = (price.barcode or "").strip() if price else ""
        product_key = (
            f"barcode:{barcode}"
            if barcode
            else cls._stable_key(scene_id, class_name, category_id)
        )
        product = db.query(Product).filter(Product.product_key == product_key).first()
        if product is None:
            product = Product(
                product_key=product_key,
                name=(price.name if price and price.name else class_name),
                sku_name=(price.sku_name if price else class_name),
                barcode=barcode or None,
                extra_metadata={"baseline_category_id": category_id},
            )
            db.add(product)
            db.flush()
        if price is not None and price.product_id is None:
            price.product_id = product.id
        return product

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _content_hash(cls, root: Path) -> str:
        digest = hashlib.sha256()
        candidates: list[Path] = []
        for split in SPLITS:
            candidates.extend(
                path for path in (root / "images" / split).glob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
            )
            candidates.extend((root / "labels" / split).glob("*.txt"))
        if (root / "data.yaml").is_file():
            candidates.append(root / "data.yaml")
        for path in sorted(candidates, key=lambda item: item.as_posix()):
            relative = path.relative_to(root).as_posix().encode("utf-8")
            digest.update(relative)
            digest.update(bytes.fromhex(cls._hash_file(path)))
        return f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _write_data_yaml(root: Path, mappings: list[DatasetClassMapping]) -> None:
        yaml_path = root / "data.yaml"
        current = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) if yaml_path.exists() else {}
        current = current or {}
        current.update(
            {
                "path": str(root),
                "train": "images/train",
                "val": "images/val",
                "test": "images/test",
                "nc": len(mappings),
                "names": {item.class_index: item.class_name for item in sorted(mappings, key=lambda row: row.class_index)},
            }
        )
        yaml_path.write_text(
            yaml.safe_dump(current, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    @classmethod
    def scan(cls, db: Session, dataset: DatasetVersion) -> DatasetVersion:
        root = cls._local_root(dataset)
        mappings = {item.class_index: item for item in dataset.classes}
        if not mappings or any(item.product_id is None for item in mappings.values()):
            raise DatasetLifecycleError("所有类别必须关联稳定 product_id 后才能扫描")

        dataset.images.clear()
        db.flush()
        image_counts = {split: 0 for split in SPLITS}
        annotation_counts = {split: 0 for split in SPLITS}
        manifest_images: list[dict[str, Any]] = []

        for split in SPLITS:
            image_dir = root / "images" / split
            label_dir = root / "labels" / split
            if not image_dir.is_dir():
                continue
            for image_path in sorted(image_dir.iterdir()):
                if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                label_path = label_dir / f"{image_path.stem}.txt"
                checksum = cls._hash_file(image_path)
                image_row = DatasetImage(
                    dataset_version_id=dataset.id,
                    split=split,
                    relative_path=image_path.relative_to(root).as_posix(),
                    label_relative_path=(label_path.relative_to(root).as_posix() if label_path.exists() else None),
                    checksum=checksum,
                    file_size=image_path.stat().st_size,
                )
                db.add(image_row)
                db.flush()
                annotation_items = []
                if label_path.is_file():
                    for line_number, raw_line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
                        line = raw_line.strip()
                        if not line:
                            continue
                        parts = line.split()
                        if len(parts) != 5:
                            raise DatasetLifecycleError(f"无效标注: {label_path}:{line_number}")
                        class_index = int(parts[0])
                        mapping = mappings.get(class_index)
                        if mapping is None:
                            raise DatasetLifecycleError(f"标注类别 {class_index} 没有商品映射: {label_path}")
                        coords = [float(value) for value in parts[1:]]
                        db.add(
                            DatasetAnnotation(
                                dataset_image_id=image_row.id,
                                product_id=mapping.product_id,
                                class_index=class_index,
                                x_center=coords[0],
                                y_center=coords[1],
                                width=coords[2],
                                height=coords[3],
                                source="imported",
                            )
                        )
                        annotation_items.append(
                            {"product_id": mapping.product_id, "class_index": class_index, "bbox": coords}
                        )
                        annotation_counts[split] += 1
                image_counts[split] += 1
                manifest_images.append(
                    {
                        "split": split,
                        "path": image_row.relative_path,
                        "label_path": image_row.label_relative_path,
                        "sha256": checksum,
                        "annotations": annotation_items,
                    }
                )

        dataset.class_count = len(mappings)
        dataset.train_image_count = image_counts["train"]
        dataset.val_image_count = image_counts["val"]
        dataset.test_image_count = image_counts["test"]
        dataset.train_annotation_count = annotation_counts["train"]
        dataset.val_annotation_count = annotation_counts["val"]
        dataset.test_annotation_count = annotation_counts["test"]
        dataset.manifest_path = "manifest.json"
        dataset.content_hash = cls._content_hash(root)
        dataset.validation_report = None
        dataset.validated_at = None
        manifest = {
            "schema_version": 1,
            "dataset_version": dataset.version,
            "generated_at": datetime.now().isoformat(),
            "content_hash": dataset.content_hash,
            "products": [
                {
                    "class_index": item.class_index,
                    "product_id": item.product_id,
                    "product_key": item.product_key,
                    "class_name": item.class_name,
                    "display_name": item.display_name,
                }
                for item in sorted(dataset.classes, key=lambda row: row.class_index)
            ],
            "images": manifest_images,
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        db.commit()
        db.refresh(dataset)
        return dataset

    @classmethod
    def import_baseline(
        cls,
        db: Session,
        *,
        scene_id: int,
        source_path: str,
        version: str,
        name: str,
        description: str | None,
        copy_files: bool,
        set_current: bool,
        user_id: int,
    ) -> DatasetVersion:
        scene = dataset_service._ensure_scene(db, scene_id)
        if db.query(DatasetVersion).filter_by(scene_id=scene_id, version=version).first():
            raise DatasetConflictError("同一场景下的数据集版本号不能重复")
        source = dataset_service._resolve_local_path(source_path)
        if source is None or not source.is_dir():
            raise DatasetNotFoundError(f"基线数据集目录不存在: {source_path}")
        names = cls._yaml_names(source)
        target = cls._target(scene_id, version) if copy_files else source
        copied = False
        try:
            if copy_files:
                if target.exists():
                    raise DatasetConflictError(f"版本目录已存在: {target}")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("*.cache"))
                copied = True

            mappings: list[DatasetClassMapping] = []
            dataset = DatasetVersion(
                scene_id=scene_id,
                version=version,
                name=name,
                description=description,
                status="draft",
                is_current=False,
                storage_path=str(target),
                data_yaml_path="data.yaml",
                manifest_path="manifest.json",
                class_count=len(names),
                created_by=user_id,
                extra_metadata={"source_path": str(source), "baseline": True, "managed_copy": copy_files},
            )
            db.add(dataset)
            db.flush()
            for class_index, class_name in enumerate(names):
                category_id = class_index + 1
                product = cls._ensure_product(
                    db,
                    scene_id=scene_id,
                    class_name=class_name,
                    category_id=category_id,
                )
                mapping = DatasetClassMapping(
                    dataset_version_id=dataset.id,
                    class_index=class_index,
                    product_id=product.id,
                    product_key=product.product_key,
                    category_id=category_id,
                    class_name=class_name,
                    display_name=product.name,
                )
                db.add(mapping)
                mappings.append(mapping)
            db.flush()
            if copy_files:
                cls._write_data_yaml(target, mappings)
            scene.class_names = names
            cls.scan(db, dataset)
            dataset = dataset_service.freeze(db, dataset_id=dataset.id, check_filesystem=True)
            if set_current:
                dataset = dataset_service.set_current(db, dataset_id=dataset.id)
            return dataset
        except Exception:
            db.rollback()
            if copied and target.exists():
                shutil.rmtree(target, ignore_errors=True)
            raise

    @classmethod
    def derive(
        cls,
        db: Session,
        *,
        parent_id: int,
        version: str,
        name: str,
        description: str | None,
        user_id: int,
    ) -> DatasetVersion:
        parent = dataset_service.get(db, parent_id)
        if parent.status not in {"ready", "archived"}:
            raise DatasetLifecycleError("只能从已冻结的数据集派生新版本")
        if db.query(DatasetVersion).filter_by(scene_id=parent.scene_id, version=version).first():
            raise DatasetConflictError("同一场景下的数据集版本号不能重复")
        source = cls._local_root(parent)
        target = cls._target(parent.scene_id, version)
        if target.exists():
            raise DatasetConflictError(f"版本目录已存在: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("*.cache"))
            dataset = DatasetVersion(
                scene_id=parent.scene_id,
                parent_id=parent.id,
                version=version,
                name=name,
                description=description,
                status="draft",
                is_current=False,
                storage_path=str(target),
                data_yaml_path="data.yaml",
                manifest_path="manifest.json",
                class_count=parent.class_count,
                created_by=user_id,
                extra_metadata={"derived_from": parent.id, "managed_copy": True},
            )
            db.add(dataset)
            db.flush()
            for item in parent.classes:
                db.add(
                    DatasetClassMapping(
                        dataset_version_id=dataset.id,
                        class_index=item.class_index,
                        product_id=item.product_id,
                        product_key=item.product_key,
                        category_id=item.category_id,
                        class_name=item.class_name,
                        display_name=item.display_name,
                        extra_metadata=item.extra_metadata,
                    )
                )
            db.flush()
            cls._write_data_yaml(target, list(dataset.classes))
            return cls.scan(db, dataset)
        except Exception:
            db.rollback()
            shutil.rmtree(target, ignore_errors=True)
            raise

    @classmethod
    def add_product(
        cls,
        db: Session,
        *,
        dataset_id: int,
        name: str,
        unit_price: float,
        files: list[tuple[str, str, bytes]],
        annotations: list[list[tuple[float, float, float, float]]] | None = None,
        class_name: str | None = None,
        barcode: str | None = None,
        product_key: str | None = None,
    ) -> tuple[DatasetVersion, Product, int]:
        dataset = dataset_service.get(db, dataset_id)
        if dataset.status != "draft":
            raise DatasetLifecycleError("只能修改派生草稿数据集")
        if not files:
            raise DatasetLifecycleError("至少上传一张商品图片")
        if annotations is not None and len(annotations) != len(files):
            raise DatasetLifecycleError("图片数量与审核标注数量不一致")
        root = cls._local_root(dataset)
        normalized_barcode = (barcode or "").strip() or None
        key = product_key or (
            f"barcode:{normalized_barcode}" if normalized_barcode else f"prod:{uuid.uuid4()}"
        )
        product = db.query(Product).filter(Product.product_key == key).first()
        if product is None:
            product = Product(
                product_key=key,
                name=name,
                sku_name=class_name or name,
                barcode=normalized_barcode,
            )
            db.add(product)
            db.flush()
        product.is_active = True
        class_index = len(dataset.classes)
        if any(item.product_id == product.id for item in dataset.classes):
            raise DatasetConflictError("该商品已存在于当前数据集")
        category_id = int(db.query(func.max(ProductPrice.category_id)).scalar() or 0) + 1
        price = db.query(ProductPrice).filter(ProductPrice.product_id == product.id).first()
        if price is None:
            price = ProductPrice(
                product_id=product.id,
                category_id=category_id,
                sku_name=class_name or name,
                name=name,
                barcode=normalized_barcode,
                unit_price=unit_price,
                currency="CNY",
            )
            db.add(price)
        else:
            price.unit_price = unit_price
        mapping = DatasetClassMapping(
            dataset_version_id=dataset.id,
            class_index=class_index,
            product_id=product.id,
            product_key=product.product_key,
            category_id=price.category_id,
            class_name=class_name or f"product_{product.id}",
            display_name=name,
        )
        dataset.classes.append(mapping)
        db.flush()

        added = 0
        safe_key = re.sub(r"[^A-Za-z0-9._-]+", "_", product.product_key)
        for sequence, (split, filename, content) in enumerate(files, 1):
            if split not in SPLITS:
                raise DatasetLifecycleError(f"不支持的数据集分区: {split}")
            suffix = Path(filename).suffix.lower()
            if suffix not in IMAGE_SUFFIXES:
                raise DatasetLifecycleError(f"不支持的图片格式: {filename}")
            stem = f"{safe_key}_{sequence:04d}"
            image_dir = root / "images" / split
            label_dir = root / "labels" / split
            image_dir.mkdir(parents=True, exist_ok=True)
            label_dir.mkdir(parents=True, exist_ok=True)
            (image_dir / f"{stem}{suffix}").write_bytes(content)
            image_annotations = (
                annotations[sequence - 1]
                if annotations is not None
                else [(0.5, 0.5, 1.0, 1.0)]
            )
            if not image_annotations:
                raise DatasetLifecycleError(f"图片 {filename} 至少需要一个检测框")
            label_lines = []
            for coords in image_annotations:
                if len(coords) != 4:
                    raise DatasetLifecycleError(f"图片 {filename} 的检测框格式无效")
                x_center, y_center, box_width, box_height = (float(value) for value in coords)
                if not (
                    0 <= x_center <= 1
                    and 0 <= y_center <= 1
                    and 0 < box_width <= 1
                    and 0 < box_height <= 1
                ):
                    raise DatasetLifecycleError(f"图片 {filename} 的检测框超出 YOLO 坐标范围")
                label_lines.append(
                    f"{class_index} {x_center:.8f} {y_center:.8f} {box_width:.8f} {box_height:.8f}"
                )
            (label_dir / f"{stem}.txt").write_text(
                "\n".join(label_lines) + "\n",
                encoding="utf-8",
            )
            added += 1
        cls._write_data_yaml(root, list(dataset.classes))
        return cls.scan(db, dataset), product, added

    @classmethod
    def delete_product(
        cls,
        db: Session,
        *,
        dataset_id: int,
        product_id: int,
        deactivate_product: bool,
    ) -> tuple[DatasetVersion, int, int, int]:
        dataset = dataset_service.get(db, dataset_id)
        if dataset.status != "draft":
            raise DatasetLifecycleError("只能修改派生草稿数据集")
        mapping = next((item for item in dataset.classes if item.product_id == product_id), None)
        if mapping is None:
            raise DatasetNotFoundError("该商品不在当前数据集版本中")
        root = cls._local_root(dataset)
        deleted_index = mapping.class_index
        images_deleted = 0
        annotations_deleted = 0

        for split in SPLITS:
            label_dir = root / "labels" / split
            image_dir = root / "images" / split
            if not label_dir.is_dir():
                continue
            for label_path in list(label_dir.glob("*.txt")):
                lines = [line.strip() for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                parsed = [(int(line.split()[0]), line.split()) for line in lines]
                hits = sum(class_id == deleted_index for class_id, _ in parsed)
                if hits:
                    annotations_deleted += hits
                    for image_path in image_dir.glob(f"{label_path.stem}.*"):
                        if image_path.suffix.lower() in IMAGE_SUFFIXES:
                            image_path.unlink()
                            images_deleted += 1
                    label_path.unlink()
                    continue
                rewritten = []
                for class_id, parts in parsed:
                    if class_id > deleted_index:
                        parts[0] = str(class_id - 1)
                    rewritten.append(" ".join(parts))
                label_path.write_text(("\n".join(rewritten) + "\n") if rewritten else "", encoding="utf-8")

        # Remove the mapping from both the ORM collection and the database.
        # Calling db.delete(mapping) alone leaves the deleted object in the
        # already-loaded relationship until the session is expired.  That
        # stale object would then leak into data.yaml and manifest.json.
        dataset.classes.remove(mapping)
        db.flush()
        for item in dataset.classes:
            if item.class_index > deleted_index:
                item.class_index -= 1
        product = db.query(Product).filter(Product.id == product_id).first()
        if product is not None and deactivate_product:
            product.is_active = False
        db.flush()
        cls._write_data_yaml(root, list(dataset.classes))
        dataset = cls.scan(db, dataset)
        return dataset, images_deleted, annotations_deleted, sum(
            item.class_index >= deleted_index for item in dataset.classes
        )


dataset_workspace_service = DatasetWorkspaceService()
