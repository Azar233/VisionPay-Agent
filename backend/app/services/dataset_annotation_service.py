"""Temporary image staging and validation for fully manual box annotations."""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config.settings import settings
from app.services.dataset_service import BACKEND_ROOT, DatasetLifecycleError, dataset_service
from app.services.dataset_workspace_service import IMAGE_SUFFIXES, SPLITS


class DatasetAnnotationService:
    """Stage uploads without inference and validate user-drawn rectangular boxes."""

    @staticmethod
    def _root() -> Path:
        configured = Path(settings.DATASET_STAGING_ROOT).expanduser()
        root = configured.resolve() if configured.is_absolute() else (BACKEND_ROOT / configured).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def _stage_dir(cls, token: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", token or ""):
            raise DatasetLifecycleError("无效的图片暂存令牌")
        return cls._root() / token

    @classmethod
    def cleanup_expired(cls) -> None:
        cutoff = time.time() - max(60, int(settings.DATASET_STAGING_TTL_SECONDS))
        for candidate in cls._root().iterdir():
            if candidate.is_dir() and candidate.stat().st_mtime < cutoff:
                shutil.rmtree(candidate, ignore_errors=True)

    @staticmethod
    def _normalized_image(content: bytes, suffix: str) -> tuple[bytes, np.ndarray]:
        try:
            with Image.open(BytesIO(content)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                if image.width < 2 or image.height < 2:
                    raise DatasetLifecycleError("图片尺寸过小，无法生成检测框")
                array = np.asarray(image)
                output = BytesIO()
                image_format = {
                    ".jpg": "JPEG",
                    ".jpeg": "JPEG",
                    ".png": "PNG",
                    ".bmp": "BMP",
                    ".webp": "WEBP",
                    ".tif": "TIFF",
                    ".tiff": "TIFF",
                }[suffix]
                save_kwargs = {"quality": 95} if image_format in {"JPEG", "WEBP"} else {}
                image.save(output, format=image_format, **save_kwargs)
                return output.getvalue(), array
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise DatasetLifecycleError("图片损坏或格式无效") from exc

    @classmethod
    def stage(
        cls,
        db,
        *,
        dataset_id: int,
        user_id: int,
        mode: str,
        files: list[tuple[str, str, bytes]],
    ) -> dict[str, Any]:
        dataset = dataset_service.get(db, dataset_id)
        if dataset.status != "draft":
            raise DatasetLifecycleError("只能修改派生草稿数据集")
        if mode not in {"train_new", "train_existing", "scene"}:
            raise DatasetLifecycleError("不支持的样本添加模式")
        splits = {split for split, _filename, _content in files}
        if mode in {"train_new", "train_existing"}:
            if not files or splits != {"train"}:
                raise DatasetLifecycleError("训练样本模式只能上传非空的 train 文件夹")
        elif not files or "train" in splits or not splits.issubset({"val", "test"}):
            raise DatasetLifecycleError("场景样本模式只能上传 val 和/或 test 文件夹")
        if len(files) > int(settings.DATASET_MAX_BATCH_SIZE):
            raise DatasetLifecycleError(f"单次最多上传 {settings.DATASET_MAX_BATCH_SIZE} 张图片")

        cls.cleanup_expired()
        token = uuid.uuid4().hex
        stage_dir = cls._stage_dir(token)
        stage_dir.mkdir(parents=True, exist_ok=False)
        max_bytes = int(settings.DATASET_MAX_UPLOAD_MB) * 1024 * 1024
        split_indexes = {split: 0 for split in SPLITS}
        images: list[dict[str, Any]] = []
        try:
            for split, filename, content in files:
                if split not in SPLITS:
                    raise DatasetLifecycleError(f"不支持的数据集分区: {split}")
                if len(content) > max_bytes:
                    raise DatasetLifecycleError(f"图片 {filename} 超过 {settings.DATASET_MAX_UPLOAD_MB} MB")
                suffix = Path(filename).suffix.lower()
                if suffix not in IMAGE_SUFFIXES:
                    raise DatasetLifecycleError(f"不支持的图片格式: {filename}")
                normalized, image = cls._normalized_image(content, suffix)
                image_id = uuid.uuid4().hex
                stored_name = f"{image_id}{suffix}"
                (stage_dir / stored_name).write_bytes(normalized)
                split_index = split_indexes[split]
                split_indexes[split] += 1
                images.append(
                    {
                        "image_id": image_id,
                        "split": split,
                        "split_index": split_index,
                        "filename": Path(filename).name,
                        "stored_name": stored_name,
                        "width": int(image.shape[1]),
                        "height": int(image.shape[0]),
                        "boxes": [],
                        "confidence": 0,
                        "needs_review": True,
                        "detection_method": "manual",
                    }
                )
            expires_at = datetime.now() + timedelta(seconds=int(settings.DATASET_STAGING_TTL_SECONDS))
            metadata = {
                "staging_token": token,
                "dataset_id": dataset_id,
                "user_id": user_id,
                "mode": mode,
                "created_at": datetime.now().isoformat(),
                "expires_at": expires_at.isoformat(),
                "images": images,
            }
            (stage_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            public_images = [{key: value for key, value in item.items() if key != "stored_name"} for item in images]
            return {
                "staging_token": token,
                "mode": mode,
                "expires_at": expires_at,
                "images": public_images,
                "total_images": len(public_images),
                "needs_review_count": sum(bool(item["needs_review"]) for item in public_images),
            }
        except Exception:
            shutil.rmtree(stage_dir, ignore_errors=True)
            raise

    @classmethod
    def _metadata(cls, *, token: str, dataset_id: int, user_id: int) -> tuple[Path, dict[str, Any]]:
        stage_dir = cls._stage_dir(token)
        metadata_path = stage_dir / "metadata.json"
        if not metadata_path.is_file():
            raise DatasetLifecycleError("图片暂存记录不存在或已过期，请重新生成检测框")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if int(metadata.get("dataset_id", 0)) != dataset_id or int(metadata.get("user_id", 0)) != user_id:
            raise DatasetLifecycleError("图片暂存记录与当前数据集或用户不匹配")
        expires_at = datetime.fromisoformat(metadata["expires_at"])
        if expires_at < datetime.now():
            shutil.rmtree(stage_dir, ignore_errors=True)
            raise DatasetLifecycleError("图片暂存记录已过期，请重新生成检测框")
        return stage_dir, metadata

    @staticmethod
    def _validated_box(box: Any, *, width: int, height: int) -> dict[str, Any]:
        x1, y1, x2, y2 = (float(box.x1), float(box.y1), float(box.x2), float(box.y2))
        if x2 - x1 < 2 or y2 - y1 < 2:
            raise DatasetLifecycleError("检测框宽高不能小于 2 像素")
        if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
            raise DatasetLifecycleError("检测框超出原图边界")
        return {
            "x_center": ((x1 + x2) / 2) / width,
            "y_center": ((y1 + y2) / 2) / height,
            "width": (x2 - x1) / width,
            "height": (y2 - y1) / height,
            "product_id": box.product_id,
        }

    @classmethod
    def reviewed_files(
        cls,
        *,
        token: str,
        dataset_id: int,
        user_id: int,
        mode: str,
        images: list[Any],
    ) -> list[tuple[str, str, bytes, list[dict[str, Any]]]]:
        stage_dir, metadata = cls._metadata(token=token, dataset_id=dataset_id, user_id=user_id)
        staged = {item["image_id"]: item for item in metadata["images"]}
        submitted = {item.image_id: item for item in images}
        if len(submitted) != len(images):
            raise DatasetLifecycleError("审核结果包含重复图片")
        if set(submitted) != set(staged):
            raise DatasetLifecycleError("必须审核并提交暂存批次中的全部图片")
        if metadata.get("mode") not in {"train_new", "train_existing", "scene"}:
            raise DatasetLifecycleError("图片暂存记录缺少有效的样本模式")
        if metadata.get("mode") != mode:
            raise DatasetLifecycleError("提交的样本模式与图片暂存记录不一致")

        result = []
        for image_id, staged_item in staged.items():
            submitted_item = submitted[image_id]
            if not submitted_item.reviewed:
                raise DatasetLifecycleError(f"图片 {staged_item['filename']} 尚未完成人工标注")
            if not submitted_item.boxes:
                raise DatasetLifecycleError(f"图片 {staged_item['filename']} 至少需要一个检测框")
            annotations = [
                cls._validated_box(
                    box,
                    width=int(staged_item["width"]),
                    height=int(staged_item["height"]),
                )
                for box in submitted_item.boxes
            ]
            image_path = stage_dir / staged_item["stored_name"]
            if not image_path.is_file():
                raise DatasetLifecycleError(f"暂存图片缺失: {staged_item['filename']}")
            result.append(
                (
                    staged_item["split"],
                    staged_item["filename"],
                    image_path.read_bytes(),
                    annotations,
                )
            )
        return result

    @classmethod
    def discard(cls, *, token: str, dataset_id: int, user_id: int) -> None:
        stage_dir, _metadata = cls._metadata(token=token, dataset_id=dataset_id, user_id=user_id)
        shutil.rmtree(stage_dir, ignore_errors=True)


dataset_annotation_service = DatasetAnnotationService()
