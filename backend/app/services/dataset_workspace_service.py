"""Managed YOLO dataset workspaces with stable product identities."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

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
    def _report(progress_callback: Callable[[int, str], None] | None, progress: int, message: str) -> None:
        if progress_callback is not None:
            progress_callback(max(0, min(100, int(progress))), message)

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
    def _content_hash(
        cls,
        root: Path,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> str:
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
        sorted_candidates = sorted(candidates, key=lambda item: item.as_posix())
        for index, path in enumerate(sorted_candidates, 1):
            relative = path.relative_to(root).as_posix().encode("utf-8")
            digest.update(relative)
            digest.update(bytes.fromhex(cls._hash_file(path)))
            cls._report(
                progress_callback,
                91 + round(index / max(1, len(sorted_candidates)) * 5),
                f"正在计算数据集内容指纹 {index}/{len(sorted_candidates)}",
            )
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
    def scan(
        cls,
        db: Session,
        dataset: DatasetVersion,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> DatasetVersion:
        root = cls._local_root(dataset)
        mappings = {item.class_index: item for item in dataset.classes}
        if not mappings or any(item.product_id is None for item in mappings.values()):
            raise DatasetLifecycleError("所有类别必须关联稳定 product_id 后才能扫描")

        cls._report(progress_callback, 2, "正在统计旧的图片与标注索引")
        old_image_ids = [
            row_id
            for (row_id,) in db.query(DatasetImage.id)
            .filter(DatasetImage.dataset_version_id == dataset.id)
            .order_by(DatasetImage.id)
            .all()
        ]
        delete_batch_size = 250
        total_old_images = max(1, len(old_image_ids))
        for offset in range(0, len(old_image_ids), delete_batch_size):
            batch = old_image_ids[offset : offset + delete_batch_size]
            db.query(DatasetAnnotation).filter(DatasetAnnotation.dataset_image_id.in_(batch)).delete(
                synchronize_session=False
            )
            db.query(DatasetImage).filter(DatasetImage.id.in_(batch)).delete(synchronize_session=False)
            db.flush()
            deleted_count = min(offset + len(batch), len(old_image_ids))
            cls._report(
                progress_callback,
                3 + round(deleted_count / total_old_images * 22),
                f"正在清理旧索引 {deleted_count}/{len(old_image_ids)}",
            )
        db.expire(dataset, ["images"])
        cls._report(progress_callback, 26, "旧索引已清理，正在读取数据集文件")
        image_counts = {split: 0 for split in SPLITS}
        annotation_counts = {split: 0 for split in SPLITS}
        manifest_images: list[dict[str, Any]] = []

        image_items: list[tuple[str, Path, Path]] = []
        for split in SPLITS:
            image_dir = root / "images" / split
            label_dir = root / "labels" / split
            if image_dir.is_dir():
                image_items.extend(
                    (split, image_path, label_dir)
                    for image_path in sorted(image_dir.iterdir())
                    if image_path.is_file() and image_path.suffix.lower() in IMAGE_SUFFIXES
                )
        total_images = max(1, len(image_items))

        for image_number, (split, image_path, label_dir) in enumerate(image_items, 1):
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
            cls._report(
                progress_callback,
                28 + round(image_number / total_images * 62),
                f"正在扫描图片与标注 {image_number}/{len(image_items)}",
            )

        dataset.class_count = len(mappings)
        dataset.train_image_count = image_counts["train"]
        dataset.val_image_count = image_counts["val"]
        dataset.test_image_count = image_counts["test"]
        dataset.train_annotation_count = annotation_counts["train"]
        dataset.val_annotation_count = annotation_counts["val"]
        dataset.test_annotation_count = annotation_counts["test"]
        dataset.manifest_path = "manifest.json"
        dataset.content_hash = cls._content_hash(root, progress_callback)
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
        cls._report(progress_callback, 97, "正在写入数据集清单")
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cls._report(progress_callback, 99, "正在提交数据集索引")
        db.commit()
        db.refresh(dataset)
        cls._report(progress_callback, 100, "数据集索引已更新")
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
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> DatasetVersion:
        cls._report(progress_callback, 2, "正在检查父版本与目标目录")
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
            source_files = [
                path
                for path in source.rglob("*")
                if path.is_file()
                and not any(part.endswith(".cache") for part in path.relative_to(source).parts)
            ]
            total_files = max(1, len(source_files))
            copied_files = 0

            def copy_with_progress(source_path, target_path):
                nonlocal copied_files
                result = shutil.copy2(source_path, target_path)
                copied_files += 1
                cls._report(
                    progress_callback,
                    5 + round(copied_files / total_files * 60),
                    f"正在复制数据集文件 {copied_files}/{len(source_files)}",
                )
                return result

            shutil.copytree(
                source,
                target,
                ignore=shutil.ignore_patterns("*.cache"),
                copy_function=copy_with_progress,
            )
            cls._report(progress_callback, 68, "正在创建版本与商品映射")
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
            return cls.scan(
                db,
                dataset,
                progress_callback=lambda progress, message: cls._report(
                    progress_callback,
                    72 + round(progress * 0.26),
                    message,
                ),
            )
        except Exception:
            db.rollback()
            shutil.rmtree(target, ignore_errors=True)
            raise

    @classmethod
    def add_samples(
        cls,
        db: Session,
        *,
        dataset_id: int,
        mode: str,
        files: list[tuple[str, str, bytes]],
        annotations: list[list[dict[str, Any]]],
        existing_product_id: int | None = None,
        name: str | None = None,
        unit_price: float | None = None,
        class_name: str | None = None,
        barcode: str | None = None,
        product_key: str | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> tuple[DatasetVersion, Product | None, int]:
        """Add single-product train samples or multi-product val/test scenes."""

        cls._report(progress_callback, 2, "正在检查样本模式与数据集")
        dataset = dataset_service.get(db, dataset_id)
        if dataset.status != "draft":
            raise DatasetLifecycleError("只能修改派生草稿数据集")
        if mode not in {"train_new", "train_existing", "scene"}:
            raise DatasetLifecycleError("不支持的样本添加模式")
        if not files or len(files) != len(annotations):
            raise DatasetLifecycleError("图片与人工标注数量不一致")

        root = cls._local_root(dataset)
        product: Product | None = None
        target_mapping: DatasetClassMapping | None = None
        mappings_by_product = {
            item.product_id: item for item in dataset.classes if item.product_id is not None
        }
        train_product_ids = {
            product_id
            for (product_id,) in (
                db.query(DatasetAnnotation.product_id)
                .join(DatasetImage, DatasetAnnotation.dataset_image_id == DatasetImage.id)
                .filter(
                    DatasetImage.dataset_version_id == dataset.id,
                    DatasetImage.split == "train",
                )
                .distinct()
                .all()
            )
        }

        if mode == "train_new":
            if not (name or "").strip() or not (class_name or "").strip() or unit_price is None:
                raise DatasetLifecycleError("新商品必须填写商品名称、类别名称和价格")
            normalized_barcode = (barcode or "").strip() or None
            key = product_key or (
                f"barcode:{normalized_barcode}" if normalized_barcode else f"prod:{uuid.uuid4()}"
            )
            product = db.query(Product).filter(Product.product_key == key).first()
            if product is None:
                product = Product(
                    product_key=key,
                    name=name.strip(),
                    sku_name=class_name.strip(),
                    barcode=normalized_barcode,
                )
                db.add(product)
                db.flush()
            if product.id in mappings_by_product:
                raise DatasetConflictError("该商品已存在，请选择‘给已有商品新增训练图’")
            product.is_active = True
            category_id = int(db.query(func.max(ProductPrice.category_id)).scalar() or 0) + 1
            price = db.query(ProductPrice).filter(ProductPrice.product_id == product.id).first()
            if price is None:
                price = ProductPrice(
                    product_id=product.id,
                    category_id=category_id,
                    sku_name=class_name.strip(),
                    name=name.strip(),
                    barcode=normalized_barcode,
                    unit_price=unit_price,
                    currency="CNY",
                )
                db.add(price)
            else:
                price.unit_price = unit_price
                category_id = price.category_id
            target_mapping = DatasetClassMapping(
                dataset_version_id=dataset.id,
                class_index=len(dataset.classes),
                product_id=product.id,
                product_key=product.product_key,
                category_id=category_id,
                class_name=class_name.strip(),
                display_name=name.strip(),
            )
            dataset.classes.append(target_mapping)
            db.flush()
            mappings_by_product[product.id] = target_mapping
        elif mode == "train_existing":
            target_mapping = mappings_by_product.get(existing_product_id)
            if target_mapping is None:
                raise DatasetNotFoundError("所选已有商品不在当前数据集版本中")
            product = db.query(Product).filter(Product.id == existing_product_id).first()

        allowed_splits = {"train"} if mode != "scene" else {"val", "test"}
        if any(split not in allowed_splits for split, _filename, _content in files):
            raise DatasetLifecycleError(
                "训练样本只能写入 train" if mode != "scene" else "结账场景只能写入 val/test"
            )

        resolved_annotations: list[list[tuple[DatasetClassMapping, dict[str, Any]]]] = []
        for (_split, filename, _content), image_annotations in zip(files, annotations):
            if not image_annotations:
                raise DatasetLifecycleError(f"图片 {filename} 至少需要一个人工检测框")
            resolved_image: list[tuple[DatasetClassMapping, dict[str, Any]]] = []
            for annotation in image_annotations:
                submitted_product_id = annotation.get("product_id")
                if mode == "scene":
                    mapping = mappings_by_product.get(submitted_product_id)
                    if mapping is None:
                        raise DatasetLifecycleError(
                            f"图片 {filename} 包含未在 train 商品目录中的 product_id={submitted_product_id}"
                        )
                    if submitted_product_id not in train_product_ids:
                        raise DatasetLifecycleError(
                            f"图片 {filename} 的 product_id={submitted_product_id} 尚无 train 标注，不能加入 val/test"
                        )
                else:
                    if submitted_product_id not in {None, target_mapping.product_id}:
                        raise DatasetLifecycleError("训练图片中的检测框只能标记为当前商品")
                    mapping = target_mapping
                resolved_image.append((mapping, annotation))
            resolved_annotations.append(resolved_image)

        cls._report(progress_callback, 5, "正在准备写入人工矩形框标注")
        added = 0
        total_files = max(1, len(files))
        batch_token = uuid.uuid4().hex[:12]
        for sequence, ((split, filename, content), image_annotations) in enumerate(
            zip(files, resolved_annotations), 1
        ):
            suffix = Path(filename).suffix.lower()
            if suffix not in IMAGE_SUFFIXES:
                raise DatasetLifecycleError(f"不支持的图片格式: {filename}")
            stem = f"manual_{batch_token}_{sequence:04d}"
            image_dir = root / "images" / split
            label_dir = root / "labels" / split
            image_dir.mkdir(parents=True, exist_ok=True)
            label_dir.mkdir(parents=True, exist_ok=True)
            (image_dir / f"{stem}{suffix}").write_bytes(content)

            label_lines: list[str] = []
            for mapping, annotation in image_annotations:
                x_center = float(annotation["x_center"])
                y_center = float(annotation["y_center"])
                box_width = float(annotation["width"])
                box_height = float(annotation["height"])
                if not (
                    0 <= x_center <= 1
                    and 0 <= y_center <= 1
                    and 0 < box_width <= 1
                    and 0 < box_height <= 1
                ):
                    raise DatasetLifecycleError(f"图片 {filename} 的检测框超出 YOLO 坐标范围")
                label_lines.append(
                    f"{mapping.class_index} {x_center:.8f} {y_center:.8f} "
                    f"{box_width:.8f} {box_height:.8f}"
                )
            (label_dir / f"{stem}.txt").write_text("\n".join(label_lines) + "\n", encoding="utf-8")
            added += 1
            cls._report(
                progress_callback,
                8 + round(sequence / total_files * 12),
                f"正在写入人工样本 {sequence}/{len(files)}",
            )

        cls._write_data_yaml(root, list(dataset.classes))
        return (
            cls.scan(
                db,
                dataset,
                progress_callback=lambda progress, message: cls._report(
                    progress_callback,
                    22 + round(progress * 0.76),
                    message,
                ),
            ),
            product,
            added,
        )

    @classmethod
    def delete_product(
        cls,
        db: Session,
        *,
        dataset_id: int,
        product_id: int,
        deactivate_product: bool,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> tuple[DatasetVersion, int, int, int]:
        cls._report(progress_callback, 2, "正在检查商品映射与数据集")
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

        labels_by_split: dict[str, list[Path]] = {}
        total_labels = 0
        for split in SPLITS:
            label_dir = root / "labels" / split
            labels = list(label_dir.glob("*.txt")) if label_dir.is_dir() else []
            labels_by_split[split] = labels
            total_labels += len(labels)
        processed_labels = 0

        for split in SPLITS:
            image_dir = root / "images" / split
            for label_path in labels_by_split[split]:
                lines = [line.strip() for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                parsed = [(int(line.split()[0]), line.split()) for line in lines]
                hits = sum(class_id == deleted_index for class_id, _parts in parsed)
                annotations_deleted += hits
                rewritten = []
                for class_id, parts in parsed:
                    if class_id == deleted_index:
                        continue
                    if class_id > deleted_index:
                        parts[0] = str(class_id - 1)
                    rewritten.append(" ".join(parts))
                if hits and not rewritten:
                    for image_path in image_dir.glob(f"{label_path.stem}.*"):
                        if image_path.suffix.lower() in IMAGE_SUFFIXES:
                            image_path.unlink()
                            images_deleted += 1
                    label_path.unlink()
                    processed_labels += 1
                    cls._report(
                        progress_callback,
                        5 + round(processed_labels / max(1, total_labels) * 35),
                        f"正在删除商品样本并重排标注 {processed_labels}/{total_labels}",
                    )
                    continue
                label_path.write_text(("\n".join(rewritten) + "\n") if rewritten else "", encoding="utf-8")
                processed_labels += 1
                cls._report(
                    progress_callback,
                    5 + round(processed_labels / max(1, total_labels) * 35),
                    f"正在删除商品样本并重排标注 {processed_labels}/{total_labels}",
                )

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
        cls._report(progress_callback, 43, "正在更新类别映射与 data.yaml")
        cls._write_data_yaml(root, list(dataset.classes))
        dataset = cls.scan(
            db,
            dataset,
            progress_callback=lambda progress, message: cls._report(
                progress_callback,
                45 + round(progress * 0.53),
                message,
            ),
        )
        return dataset, images_deleted, annotations_deleted, sum(
            item.class_index >= deleted_index for item in dataset.classes
        )


dataset_workspace_service = DatasetWorkspaceService()
