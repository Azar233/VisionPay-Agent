"""YOLO inference service for VisionPay retail product detection."""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import threading
import zipfile
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import (
    DetectionResult,
    DetectionScene,
    DetectionTask,
    ModelVersion,
    ProductPrice,
    TrainingTask,
)

logger = get_logger(__name__)

ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
_MODEL_CACHE: dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class DetectionServiceError(RuntimeError):
    """A user-facing detection error."""


def _data_url(image: Any) -> str:
    """Encode an RGB/BGR numpy image as a compact JPEG data URL."""
    import cv2

    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 86])
    if not ok:
        raise DetectionServiceError("标注图编码失败")
    return "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")


class DetectionService:
    """Run single, batch, and ZIP inference with a trained VisionPay model."""

    def _resolve_scene(self, db, scene_id: int | None) -> DetectionScene:
        query = db.query(DetectionScene).filter(DetectionScene.is_active.is_(True))
        scene = query.filter(DetectionScene.id == scene_id).first() if scene_id else query.first()
        if not scene:
            raise DetectionServiceError("没有可用的零售检测场景，请先创建 Vision Pay 场景")
        return scene

    def _resolve_model(self, db, scene_id: int) -> tuple[Path, int | None]:
        if settings.DETECTION_MODEL_PATH:
            path = Path(settings.DETECTION_MODEL_PATH).expanduser().resolve()
            if not path.is_file():
                raise DetectionServiceError(f"DETECTION_MODEL_PATH 不存在: {path}")
            return path, None

        model_version = (
            db.query(ModelVersion)
            .filter(
                ModelVersion.scene_id == scene_id,
                ModelVersion.status == "active",
                ModelVersion.is_default.is_(True),
            )
            .order_by(ModelVersion.created_at.desc())
            .first()
        )
        if model_version and Path(model_version.model_path).is_file():
            return Path(model_version.model_path).resolve(), model_version.id

        task = (
            db.query(TrainingTask)
            .filter(TrainingTask.scene_id == scene_id, TrainingTask.status == "completed")
            .order_by(TrainingTask.completed_at.desc())
            .first()
        )
        if task:
            path = (
                Path(settings.TRAIN_OUTPUT_DIR)
                / f"task_{task.task_uuid}"
                / "weights"
                / "best.pt"
            ).resolve()
            if path.is_file():
                return path, None

        raise DetectionServiceError(
            "未找到已训练的商品检测模型。请先导出默认模型，或配置 DETECTION_MODEL_PATH"
        )

    @staticmethod
    def _load_model(model_path: Path):
        key = str(model_path)
        with _MODEL_LOCK:
            if key not in _MODEL_CACHE:
                config_dir = Path(settings.YOLO_CONFIG_DIR)
                if not config_dir.is_absolute():
                    config_dir = BACKEND_ROOT / config_dir
                config_dir.mkdir(parents=True, exist_ok=True)
                os.environ.setdefault("YOLO_CONFIG_DIR", str(config_dir.resolve()))
                from ultralytics import YOLO

                logger.info("加载商品检测模型: %s", key)
                _MODEL_CACHE[key] = YOLO(key)
            return _MODEL_CACHE[key]

    @staticmethod
    def validate_image(path: str | Path) -> Path:
        image_path = Path(path).resolve()
        if image_path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES or not image_path.is_file():
            raise DetectionServiceError(f"不支持的图片文件: {image_path.name}")
        try:
            with Image.open(image_path) as image:
                image.verify()
        except Exception as exc:
            raise DetectionServiceError(f"图片损坏或格式无效: {image_path.name}") from exc
        return image_path

    @staticmethod
    def _serialize_prediction(result: Any, image_path: Path) -> dict[str, Any]:
        names = result.names
        detections: list[dict[str, Any]] = []
        if result.boxes is not None:
            for box in result.boxes:
                class_id = int(box.cls.item())
                class_name = str(names[class_id])
                detections.append(
                    {
                        "class_id": class_id,
                        "class_name": class_name,
                        "confidence": round(float(box.conf.item()), 4),
                        "bbox": [round(float(value), 2) for value in box.xyxy[0].tolist()],
                    }
                )

        speed = result.speed or {}
        inference_ms = round(float(speed.get("inference", 0)), 2)
        height, width = result.orig_shape
        counts = dict(Counter(item["class_name"] for item in detections))
        return {
            "filename": image_path.name,
            "image_width": int(width),
            "image_height": int(height),
            "object_count": len(detections),
            "class_counts": counts,
            "detections": detections,
            "inference_time_ms": inference_ms,
            "annotated_image": _data_url(result.plot()),
        }

    @staticmethod
    def _calculate_total_price(db, detections: list[dict[str, Any]]) -> dict[str, Any]:
        """根据逐个检测框汇总类别数量并计算总价。"""
        counts: dict[int, int] = Counter()
        name_map: dict[int, str] = {}
        for detection in detections:
            class_id = int(detection["class_id"])
            counts[class_id] += 1
            name_map[class_id] = detection["class_name"]

        return DetectionService.calculate_price(db, counts, name_map)

    @staticmethod
    def calculate_price(
        db,
        class_counts: dict[int, int],
        class_names: dict[int, str] | None = None,
    ) -> dict[str, Any]:
        """Use authoritative database prices to calculate a checkout summary."""
        counts = {
            int(class_id): int(count)
            for class_id, count in class_counts.items()
            if int(count) > 0
        }
        name_map = class_names or {}

        if not counts:
            return {
                "total_price": 0.0,
                "currency": "CNY",
                "items": [],
                "pricing_complete": True,
                "missing_category_ids": [],
                "priced_objects": 0,
                "unpriced_objects": 0,
            }

        # YOLO uses zero-based class IDs while instances_train2019.json (and
        # product_prices) uses one-based category IDs: class 0 -> category 1.
        category_ids = [class_id + 1 for class_id in counts]
        prices = {
            price.category_id: price
            for price in db.query(ProductPrice)
            .filter(ProductPrice.category_id.in_(category_ids))
            .all()
        }

        missing = [cid for cid in category_ids if cid not in prices]
        if missing:
            logger.warning("以下 category_id 未设置价格，暂不计入总价: %s", missing)

        items = []
        total_price = Decimal("0.00")
        priced_objects = 0
        unpriced_objects = 0
        for class_id, count in sorted(counts.items()):
            category_id = class_id + 1
            price = prices.get(category_id)
            has_price = price is not None
            unit_price = Decimal(str(price.unit_price if price else 0)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            subtotal = (unit_price * count).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            total_price += subtotal
            if has_price:
                priced_objects += count
            else:
                unpriced_objects += count
            items.append(
                {
                    "class_id": class_id,
                    "category_id": category_id,
                    "class_name": name_map.get(class_id) or (price.sku_name if price else ""),
                    "sku_name": price.sku_name if price else None,
                    "name": price.name if price else None,
                    "barcode": price.barcode if price else None,
                    "count": count,
                    "unit_price": float(unit_price),
                    "subtotal": float(subtotal),
                    "currency": (price.currency or "CNY") if price else "CNY",
                    "has_price": has_price,
                }
            )

        return {
            "total_price": float(total_price.quantize(Decimal("0.01"))),
            "currency": "CNY",
            "items": items,
            "pricing_complete": not missing,
            "missing_category_ids": sorted(missing),
            "priced_objects": priced_objects,
            "unpriced_objects": unpriced_objects,
        }

    @staticmethod
    def _persist_results(
        db,
        task: DetectionTask,
        image_path: Path,
        item: dict[str, Any],
    ) -> None:
        for detection in item["detections"]:
            db.add(
                DetectionResult(
                    task_id=task.id,
                    image_path=str(image_path),
                    class_name=detection["class_name"],
                    class_id=detection["class_id"],
                    confidence=detection["confidence"],
                    bbox=detection["bbox"],
                    inference_time=item["inference_time_ms"],
                    image_width=item["image_width"],
                    image_height=item["image_height"],
                )
            )

    def detect_batch(
        self,
        image_paths: Iterable[str | Path],
        *,
        user_id: int,
        scene_id: int | None = None,
        conf: float = 0.25,
        iou: float = 0.45,
        image_size: int = 640,
        source: str = "batch",
    ) -> dict[str, Any]:
        paths = [self.validate_image(path) for path in image_paths]
        if not paths:
            raise DetectionServiceError("没有可检测的图片")
        if len(paths) > settings.DETECTION_MAX_BATCH_SIZE:
            raise DetectionServiceError(
                f"单次最多检测 {settings.DETECTION_MAX_BATCH_SIZE} 张图片"
            )

        db = SessionLocal()
        task: DetectionTask | None = None
        try:
            scene = self._resolve_scene(db, scene_id)
            model_path, model_version_id = self._resolve_model(db, scene.id)
            task = DetectionTask(
                user_id=user_id,
                scene_id=scene.id,
                model_version_id=model_version_id,
                task_type="single" if len(paths) == 1 else source,
                status="processing",
                total_images=len(paths),
                conf_threshold=conf,
                iou_threshold=iou,
                image_size=image_size,
            )
            db.add(task)
            db.commit()
            db.refresh(task)

            model = self._load_model(model_path)
            raw_results = model.predict(
                source=[str(path) for path in paths],
                conf=conf,
                iou=iou,
                imgsz=image_size,
                verbose=False,
            )
            items = []
            for path, raw_result in zip(paths, raw_results):
                item = self._serialize_prediction(raw_result, path)
                self._persist_results(db, task, path, item)
                items.append(item)

            class_counts = Counter()
            for item in items:
                class_counts.update(item["class_counts"])
            total_objects = sum(item["object_count"] for item in items)
            total_inference = round(sum(item["inference_time_ms"] for item in items), 2)
            task.status = "completed"
            task.total_objects = total_objects
            task.total_inference_time = total_inference
            task.completed_at = datetime.now()
            db.commit()

            all_detections = [
                detection for item in items for detection in item["detections"]
            ]
            price_summary = self._calculate_total_price(db, all_detections)

            return {
                "task_id": task.id,
                "source": source,
                "scene": scene.display_name,
                "model": model_path.name,
                "total_images": len(items),
                "total_objects": total_objects,
                "total_inference_time_ms": total_inference,
                "class_counts": dict(class_counts),
                "items": items,
                "price_summary": price_summary,
            }
        except Exception as exc:
            db.rollback()
            if task and task.id:
                task.status = "failed"
                task.error_message = str(exc)
                db.add(task)
                db.commit()
            if isinstance(exc, DetectionServiceError):
                raise
            logger.error("商品检测失败: %s", exc, exc_info=True)
            raise DetectionServiceError(f"检测失败: {exc}") from exc
        finally:
            db.close()

    def detect_single(self, image_path: str | Path, **kwargs) -> dict[str, Any]:
        return self.detect_batch([image_path], source="single", **kwargs)

    def detect_zip(self, zip_path: str | Path, **kwargs) -> dict[str, Any]:
        archive_path = Path(zip_path).resolve()
        if not archive_path.is_file() or not zipfile.is_zipfile(archive_path):
            raise DetectionServiceError("ZIP 文件无效或已损坏")

        temp_dir = Path(tempfile.mkdtemp(prefix="visionpay_zip_"))
        try:
            image_paths: list[Path] = []
            with zipfile.ZipFile(archive_path) as archive:
                candidates = [
                    member
                    for member in archive.infolist()
                    if not member.is_dir()
                    and Path(member.filename).suffix.lower() in ALLOWED_IMAGE_SUFFIXES
                ]
                if len(candidates) > settings.DETECTION_MAX_BATCH_SIZE:
                    raise DetectionServiceError(
                        f"ZIP 中图片超过 {settings.DETECTION_MAX_BATCH_SIZE} 张限制"
                    )
                max_expanded_bytes = (
                    settings.DETECTION_MAX_FILE_MB
                    * 1024
                    * 1024
                    * min(settings.DETECTION_MAX_BATCH_SIZE, 10)
                )
                expanded_bytes = sum(member.file_size for member in candidates)
                if expanded_bytes > max_expanded_bytes:
                    raise DetectionServiceError("ZIP 解压后的图片总大小超过安全限制")
                for index, member in enumerate(candidates):
                    # Generate our own flat filename, preventing Zip Slip and collisions.
                    target = temp_dir / f"{index:03d}_{Path(member.filename).name}"
                    with archive.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    image_paths.append(target)
            if not image_paths:
                raise DetectionServiceError("ZIP 中没有支持的图片")
            result = self.detect_batch(image_paths, source="zip", **kwargs)
            result["zip_filename"] = archive_path.name
            return result
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


detection_service = DetectionService()


def result_to_json(result: dict[str, Any]) -> str:
    """Return an LLM-friendly result without embedding annotated images."""
    compact = dict(result)
    compact["items"] = [
        {key: value for key, value in item.items() if key != "annotated_image"}
        for item in result.get("items", [])
    ]
    return json.dumps(compact, ensure_ascii=False)
