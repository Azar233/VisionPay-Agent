"""YOLO inference service for VisionPay retail product detection."""

from __future__ import annotations

import base64
import json
import math
import os
import shutil
import tempfile
import threading
import zipfile
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import (
    DatasetClassMapping,
    DetectionResult,
    DetectionScene,
    DetectionTask,
    ModelVersion,
    Product,
    ProductPrice,
    TrainingTask,
)
from app.services.model_version_service import model_version_service
from app.services.track_aggregator import TrackRegistry

logger = get_logger(__name__)

ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv"}
_MODEL_CACHE: dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()
_PREDICT_LOCK = threading.Lock()
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
        model_version_service.ensure_builtin(db, scene_id=scene_id)
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
        if model_version:
            selected_path = Path(model_version.model_path).expanduser().resolve()
            if not selected_path.is_file():
                raise DetectionServiceError(
                    f"当前检测模型 {model_version.version} 的文件不存在: {selected_path}"
                )
            return selected_path, model_version.id

        # Keep the environment override as a compatibility fallback only.
        # Once a model version is selected in the registry, that selection wins.
        if settings.DETECTION_MODEL_PATH:
            path = Path(settings.DETECTION_MODEL_PATH).expanduser().resolve()
            if not path.is_file():
                raise DetectionServiceError(f"DETECTION_MODEL_PATH 不存在: {path}")
            return path, None

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
    def _ensure_yolo_config() -> None:
        config_dir = Path(settings.YOLO_CONFIG_DIR)
        if not config_dir.is_absolute():
            config_dir = BACKEND_ROOT / config_dir
        config_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(config_dir.resolve()))

    @classmethod
    def _load_model(cls, model_path: Path):
        key = str(model_path)
        with _MODEL_LOCK:
            if key not in _MODEL_CACHE:
                cls._ensure_yolo_config()
                from ultralytics import YOLO

                logger.info("加载商品检测模型: %s", key)
                _MODEL_CACHE[key] = YOLO(key)
            return _MODEL_CACHE[key]

    @classmethod
    def _load_fresh_model(cls, model_path: Path):
        """Uncached per-task YOLO instance so tracker state never leaks between tasks."""
        cls._ensure_yolo_config()
        from ultralytics import YOLO

        logger.info("加载独立跟踪模型实例: %s", model_path)
        return YOLO(str(model_path))

    @staticmethod
    def _get_device() -> str:
        """Return GPU device id if CUDA is available, otherwise CPU."""
        import torch

        return "0" if torch.cuda.is_available() else "cpu"

    @staticmethod
    def _use_half(device: str) -> bool:
        """Enable FP16 on CUDA to leverage T4 Tensor Cores; CPU keeps FP32."""
        return device != "cpu"

    def prepare_realtime_model(
        self,
        *,
        scene_id: int | None = None,
        image_size: int = 512,
        conf: float = 0.30,
        iou: float = 0.45,
    ) -> dict[str, Any]:
        """Resolve, load and warm the model used by an IP Webcam session."""
        import numpy as np

        db = SessionLocal()
        try:
            scene = self._resolve_scene(db, scene_id)
            model_path, _model_version_id = self._resolve_model(db, scene.id)
            # 每会话独立实例：ByteTrack 的内部状态不能跨会话/跨任务残留。
            model = self._load_fresh_model(model_path)
            scene_info = {
                "scene_id": scene.id,
                "scene": scene.display_name,
            }
        finally:
            db.close()

        dummy_frame = np.zeros((image_size, image_size, 3), dtype=np.uint8)
        device = self._get_device()
        with _PREDICT_LOCK:
            model.predict(
                source=dummy_frame,
                conf=conf,
                iou=iou,
                imgsz=image_size,
                device=device,
                half=self._use_half(device),
                save=False,
                verbose=False,
            )
        return {
            "model": model,
            "model_name": model_path.name,
            **scene_info,
        }

    def detect_realtime_frame(
        self,
        model: Any,
        frame: Any,
        *,
        conf: float = 0.30,
        iou: float = 0.45,
        image_size: int = 512,
        jpeg_quality: int = 70,
        output_max_width: int = 960,
        finalize: bool = True,
        tracking: bool = False,
    ) -> dict[str, Any]:
        """Run one inference (or ByteTrack step) and return a compact WebSocket payload."""
        import cv2

        # Real-time camera sessions are guaranteed single by _claim_camera_session,
        # so the global predict lock is not needed here.
        device = self._get_device()
        if tracking:
            result = model.track(
                source=frame,
                persist=True,
                tracker="bytetrack.yaml",
                conf=conf,
                iou=iou,
                imgsz=image_size,
                device=device,
                half=self._use_half(device),
                save=False,
                verbose=False,
            )[0]
            detections = self._serialize_tracks(result)
        else:
            result = model.predict(
                source=frame,
                conf=conf,
                iou=iou,
                imgsz=image_size,
                device=device,
                half=self._use_half(device),
                save=False,
                verbose=False,
            )[0]

            names = result.names
            detections = []
            if result.boxes is not None:
                for box in result.boxes:
                    class_id = int(box.cls.item())
                    detections.append(
                        {
                            "class_id": class_id,
                            "class_name": str(names[class_id]),
                            "confidence": round(float(box.conf.item()), 4),
                            "bbox": [
                                round(float(value), 2) for value in box.xyxy[0].tolist()
                            ],
                        }
                    )

        speed = result.speed or {}
        inference_time_ms = round(float(speed.get("inference", 0)), 2)
        if not finalize:
            return {
                "detections": detections,
                "inference_time_ms": inference_time_ms,
            }
        return self.finalize_realtime_frame(
            frame,
            detections,
            inference_time_ms=inference_time_ms,
            jpeg_quality=jpeg_quality,
            output_max_width=output_max_width,
        )

    def finalize_realtime_frame(
        self,
        frame: Any,
        detections: list[dict[str, Any]],
        *,
        inference_time_ms: float,
        jpeg_quality: int = 70,
        output_max_width: int = 960,
        price_detections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Render stabilized detections and calculate their price summary."""
        import cv2

        annotated = frame.copy()
        palette = [
            (235, 64, 52),
            (46, 204, 113),
            (52, 152, 219),
            (155, 89, 182),
            (241, 196, 15),
            (230, 126, 34),
        ]
        line_width = max(2, round(min(annotated.shape[:2]) / 320))
        for detection in detections:
            x1, y1, x2, y2 = [round(float(value)) for value in detection["bbox"]]
            color = palette[int(detection["class_id"]) % len(palette)]
            label = f'{detection["class_name"]} {float(detection["confidence"]):.2f}'
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, line_width)
            (text_width, text_height), baseline = cv2.getTextSize(
                label,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                1,
            )
            label_top = max(0, y1 - text_height - baseline - 6)
            cv2.rectangle(
                annotated,
                (x1, label_top),
                (x1 + text_width + 8, label_top + text_height + baseline + 6),
                color,
                -1,
            )
            cv2.putText(
                annotated,
                label,
                (x1 + 4, label_top + text_height + 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        height, width = annotated.shape[:2]
        if output_max_width > 0 and width > output_max_width:
            scale = output_max_width / width
            annotated = cv2.resize(
                annotated,
                (output_max_width, max(1, round(height * scale))),
                interpolation=cv2.INTER_AREA,
            )

        ok, encoded = cv2.imencode(
            ".jpg",
            annotated,
            [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
        )
        if not ok:
            raise DetectionServiceError("实时标注帧编码失败")

        db = SessionLocal()
        try:
            # price_detections 用于"按确认轨迹累计计价"；缺省按当前帧检测计价。
            price_summary = self._calculate_total_price(
                db, price_detections if price_detections is not None else detections
            )
        finally:
            db.close()

        return {
            "annotated_frame": base64.b64encode(encoded).decode("ascii"),
            "detections": detections,
            "object_count": len(detections),
            "class_counts": dict(Counter(item["class_name"] for item in detections)),
            "inference_time_ms": inference_time_ms,
            "price_summary": price_summary,
        }

    def create_video_task(
        self,
        *,
        user_id: int,
        scene_id: int | None = None,
        conf: float = 0.25,
        iou: float = 0.45,
        image_size: int = 640,
    ) -> dict[str, Any]:
        """Create the durable database row before background processing starts."""
        db = SessionLocal()
        try:
            scene = self._resolve_scene(db, scene_id)
            _model_path, model_version_id = self._resolve_model(db, scene.id)
            task = DetectionTask(
                user_id=user_id,
                scene_id=scene.id,
                model_version_id=model_version_id,
                task_type="video",
                status="pending",
                total_images=0,
                conf_threshold=conf,
                iou_threshold=iou,
                image_size=image_size,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            return {"task_id": task.id, "scene_id": scene.id, "scene": scene.display_name}
        except Exception as exc:
            db.rollback()
            if isinstance(exc, DetectionServiceError):
                raise
            raise DetectionServiceError(f"创建视频检测任务失败: {exc}") from exc
        finally:
            db.close()

    def detect_video(
        self,
        video_path: str | Path,
        *,
        user_id: int,
        scene_id: int | None = None,
        conf: float = 0.25,
        iou: float = 0.45,
        image_size: int = 640,
        frame_sample_rate: int = 5,
        max_frames: int = 50,
        task_id: int | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
        tracking: bool | None = None,
    ) -> dict[str, Any]:
        """Detect a video; tracked mode (default) counts unique ByteTrack tracks,
        sampled mode sums detections over uniformly sampled key frames."""
        import cv2

        path = Path(video_path).resolve()
        if path.suffix.lower() not in ALLOWED_VIDEO_SUFFIXES or not path.is_file():
            raise DetectionServiceError(f"不支持的视频文件: {path.name}")
        if frame_sample_rate < 1 or max_frames < 1:
            raise DetectionServiceError("视频采样间隔和最大关键帧数必须大于 0")
        if tracking is None:
            tracking = settings.VIDEO_TRACKING_ENABLED
        if task_id is None:
            task_id = self.create_video_task(
                user_id=user_id,
                scene_id=scene_id,
                conf=conf,
                iou=iou,
                image_size=image_size,
            )["task_id"]

        db = SessionLocal()
        capture = None
        try:
            task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
            if not task or task.user_id != user_id or task.task_type != "video":
                raise DetectionServiceError("视频检测任务不存在或无权访问")
            task.status = "processing"
            db.commit()
            if progress_callback:
                progress_callback(2, "正在读取视频信息")

            scene = self._resolve_scene(db, task.scene_id)
            model_path, _model_version_id = self._resolve_model(db, scene.id)
            capture = cv2.VideoCapture(str(path))
            if not capture.isOpened():
                raise DetectionServiceError("无法打开视频，请确认文件编码完整")

            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if total_frames <= 0:
                raise DetectionServiceError("无法读取视频总帧数")
            if not math.isfinite(fps) or fps <= 0:
                fps = 30.0
            duration_seconds = total_frames / fps

            if tracking:
                return self._detect_video_tracked(
                    db,
                    task=task,
                    scene=scene,
                    model_path=model_path,
                    path=path,
                    capture=capture,
                    total_frames=total_frames,
                    fps=fps,
                    width=width,
                    height=height,
                    duration_seconds=duration_seconds,
                    conf=conf,
                    iou=iou,
                    image_size=image_size,
                    progress_callback=progress_callback,
                )

            model = self._load_model(model_path)
            effective_interval = max(
                frame_sample_rate,
                math.ceil(total_frames / max_frames),
            )
            sample_indices = list(range(0, total_frames, effective_interval))[:max_frames]
            task.total_images = len(sample_indices)
            db.commit()

            items: list[dict[str, Any]] = []
            class_counts: Counter[str] = Counter()
            total_objects = 0
            total_inference = 0.0
            for position, frame_index in enumerate(sample_indices, start=1):
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok or frame is None:
                    logger.warning("跳过无法读取的视频帧: %s#%d", path.name, frame_index)
                    continue
                device = self._get_device()
                with _PREDICT_LOCK:
                    prediction = model.predict(
                        source=frame,
                        conf=conf,
                        iou=iou,
                        imgsz=image_size,
                        device=device,
                        half=self._use_half(device),
                        verbose=False,
                    )[0]
                frame_path = Path(f"{path.name}.frame_{frame_index:06d}.jpg")
                item = self._serialize_prediction(prediction, frame_path)
                item.update(
                    {
                        "frame_index": frame_index,
                        "timestamp_seconds": round(frame_index / fps, 2),
                    }
                )
                self._persist_results(db, task, frame_path, item)
                items.append(item)
                class_counts.update(item["class_counts"])
                total_objects += item["object_count"]
                total_inference += item["inference_time_ms"]
                task.total_objects = total_objects
                task.total_inference_time = round(total_inference, 2)
                db.commit()
                if progress_callback:
                    progress = 5 + round(position / len(sample_indices) * 90)
                    progress_callback(
                        min(progress, 95),
                        f"正在检测关键帧 {position}/{len(sample_indices)}",
                    )

            if not items:
                raise DetectionServiceError("视频中没有可读取的关键帧")
            task.status = "completed"
            task.total_images = len(items)
            task.total_objects = total_objects
            task.total_inference_time = round(total_inference, 2)
            task.completed_at = datetime.now()
            db.commit()
            result = {
                "task_id": task.id,
                "source": "video",
                "scene": scene.display_name,
                "model": model_path.name,
                "filename": path.name,
                "total_frames": total_frames,
                "processed_frames": len(items),
                "total_images": len(items),
                "frame_sample_rate": effective_interval,
                "fps": round(fps, 2),
                "duration_seconds": round(duration_seconds, 2),
                "video_resolution": {"width": width, "height": height},
                "total_objects": total_objects,
                "object_count_mode": "sampled_detections",
                "class_counts": dict(class_counts),
                "total_inference_time_ms": round(total_inference, 2),
                "items": items,
            }
            if progress_callback:
                progress_callback(100, "视频检测完成")
            return result
        except Exception as exc:
            db.rollback()
            task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = str(exc)
                db.commit()
            if isinstance(exc, DetectionServiceError):
                raise
            logger.error("视频检测失败: %s", exc, exc_info=True)
            raise DetectionServiceError(f"视频检测失败: {exc}") from exc
        finally:
            if capture is not None:
                capture.release()
            db.close()

    def _detect_video_tracked(
        self,
        db,
        *,
        task: DetectionTask,
        scene: DetectionScene,
        model_path: Path,
        path: Path,
        capture: Any,
        total_frames: int,
        fps: float,
        width: int,
        height: int,
        duration_seconds: float,
        conf: float,
        iou: float,
        image_size: int,
        progress_callback: Callable[[int, str], None] | None,
    ) -> dict[str, Any]:
        """Track consecutive frames with ByteTrack and count unique tracks."""
        max_seconds = settings.VIDEO_TRACKING_MAX_SECONDS
        if max_seconds > 0 and duration_seconds > max_seconds:
            raise DetectionServiceError(
                f"视频时长 {duration_seconds:.0f} 秒，超过跟踪上限 {max_seconds} 秒，请裁剪后重新上传"
            )
        stride = max(1, settings.VIDEO_TRACK_FRAME_STRIDE)

        model = self._load_fresh_model(model_path)
        registry = TrackRegistry(min_hits=3, max_misses=3, min_confidence=conf)
        device = self._get_device()
        evidence: dict[int, bytes] = {}
        total_inference = 0.0
        processed = 0
        expected = max(1, math.ceil(total_frames / stride))
        last_percent = 5
        frame_index = -1

        annotated_dir = Path(settings.MEDIA_ROOT).resolve() / "video-annotated"
        annotated_dir.mkdir(parents=True, exist_ok=True)
        annotated_path = annotated_dir / f"task_{task.id}.mp4"
        video_writer = None
        output_fps = max(1.0, fps / stride)
        try:
            import imageio.v2 as imageio
            video_writer = imageio.get_writer(
                str(annotated_path),
                fps=output_fps,
                codec="libx264",
                quality=8,
                macro_block_size=1,
            )
        except Exception as exc:
            logger.warning("imageio 标注视频初始化失败，尝试 OpenCV MJPG: %s", exc)
            try:
                import cv2
                annotated_path = annotated_path.with_suffix(".avi")
                fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                writer = cv2.VideoWriter(str(annotated_path), fourcc, output_fps, (width, height))
                if writer.isOpened():
                    video_writer = writer
                else:
                    writer.release()
                    logger.warning("标注视频写入器初始化失败，将跳过视频生成: %s", annotated_path)
            except Exception as cv_exc:
                logger.warning("标注视频初始化异常，将跳过视频生成: %s", cv_exc)
                video_writer = None

        if progress_callback:
            progress_callback(5, "正在初始化轨迹跟踪")

        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            frame_index += 1
            if frame_index % stride != 0:
                continue
            with _PREDICT_LOCK:
                result = model.track(
                    source=frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    conf=conf,
                    iou=iou,
                    imgsz=image_size,
                    device=device,
                    half=self._use_half(device),
                    save=False,
                    verbose=False,
                )[0]
            total_inference += float((result.speed or {}).get("inference", 0))
            tracks = self._serialize_tracks(result)
            peaks = registry.update(frame_index, frame_index / fps, tracks)
            self._capture_evidence(evidence, peaks, tracks, frame)
            if video_writer is not None:
                try:
                    annotated_frame = result.plot()
                    if annotated_frame is not None and annotated_frame.size > 0:
                        frame_height, frame_width = annotated_frame.shape[:2]
                        if (frame_width, frame_height) != (width, height):
                            annotated_frame = cv2.resize(annotated_frame, (width, height))
                        if hasattr(video_writer, "append_data"):
                            video_writer.append_data(cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB))
                        else:
                            video_writer.write(annotated_frame)
                except Exception as exc:
                    logger.warning("标注视频帧写入失败，停止生成视频: %s", exc)
                    if hasattr(video_writer, "close"):
                        video_writer.close()
                    else:
                        video_writer.release()
                    video_writer = None
            processed += 1
            if progress_callback:
                percent = min(5 + round(processed / expected * 90), 95)
                if percent > last_percent:
                    last_percent = percent
                    progress_callback(percent, f"正在跟踪视频帧 {processed}/{expected}")

        if processed == 0:
            if video_writer is not None:
                if hasattr(video_writer, "close"):
                    video_writer.close()
                else:
                    video_writer.release()
            raise DetectionServiceError("视频中没有可读取的帧")

        if video_writer is not None:
            if hasattr(video_writer, "close"):
                video_writer.close()
            else:
                video_writer.release()
        annotated_video_url = f"/media/video-annotated/{annotated_path.name}" if annotated_path.is_file() else None

        summaries, items, price_summary = self._finalize_tracked_video(
            db,
            task=task,
            registry=registry,
            evidence=evidence,
            path=path,
            width=width,
            height=height,
            total_inference=total_inference,
            processed=processed,
        )
        task.status = "completed"
        task.total_images = processed
        task.total_objects = registry.total_unique
        task.total_inference_time = round(total_inference, 2)
        task.completed_at = datetime.now()
        db.commit()
        if progress_callback:
            progress_callback(100, "视频跟踪检测完成")
        return {
            "task_id": task.id,
            "source": "video",
            "scene": scene.display_name,
            "model": model_path.name,
            "filename": path.name,
            "total_frames": total_frames,
            "processed_frames": processed,
            "total_images": processed,
            "frame_sample_rate": stride,
            "fps": round(fps, 2),
            "duration_seconds": round(duration_seconds, 2),
            "video_resolution": {"width": width, "height": height},
            "total_objects": registry.total_unique,
            "object_count_mode": "bytetrack_unique_tracks",
            "class_counts": registry.dedup_class_counts(),
            "peak_simultaneous": registry.peak_simultaneous,
            "tracks": summaries,
            "total_inference_time_ms": round(total_inference, 2),
            "items": items,
            "price_summary": price_summary,
            "annotated_video_url": annotated_video_url,
        }

    @staticmethod
    def _serialize_tracks(result: Any) -> list[dict[str, Any]]:
        """Extract track observations from one ultralytics track result."""
        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return []
        names = result.names
        tracks = []
        ids = boxes.id.int().cpu().tolist()
        classes = boxes.cls.int().cpu().tolist()
        confidences = boxes.conf.cpu().tolist()
        xyxy = boxes.xyxy.cpu().tolist()
        for track_id, class_id, confidence, bbox in zip(ids, classes, confidences, xyxy):
            tracks.append(
                {
                    "track_id": int(track_id),
                    "class_id": int(class_id),
                    "class_name": str(names[int(class_id)]),
                    "confidence": round(float(confidence), 4),
                    "bbox": [round(float(value), 2) for value in bbox],
                }
            )
        return tracks

    @staticmethod
    def _capture_evidence(
        evidence: dict[int, bytes],
        peak_track_ids: list[int],
        tracks: list[dict[str, Any]],
        frame: Any,
    ) -> None:
        """Cache a bbox crop for each track that hit its confidence peak this frame."""
        if not peak_track_ids:
            return
        import cv2

        height, width = frame.shape[:2]
        by_id = {track["track_id"]: track for track in tracks}
        for track_id in peak_track_ids:
            track = by_id.get(track_id)
            if track is None:
                continue
            x1, y1, x2, y2 = track["bbox"]
            margin_x = (x2 - x1) * 0.1
            margin_y = (y2 - y1) * 0.1
            crop = frame[
                max(0, int(y1 - margin_y)): min(height, int(y2 + margin_y)),
                max(0, int(x1 - margin_x)): min(width, int(x2 + margin_x)),
            ]
            if crop.size == 0:
                continue
            ok, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                evidence[track_id] = encoded.tobytes()

    def _finalize_tracked_video(
        self,
        db,
        *,
        task: DetectionTask,
        registry: TrackRegistry,
        evidence: dict[int, bytes],
        path: Path,
        width: int,
        height: int,
        total_inference: float,
        processed: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        """Persist one row per confirmed track and build summaries/items/price."""
        evidence_dir = Path(settings.MEDIA_ROOT).resolve() / "video-evidence" / f"task_{task.id}"
        average_inference = round(total_inference / max(processed, 1), 2)
        summaries: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        count_by_class_id: Counter[int] = Counter()
        name_map: dict[int, str] = {}
        for record in registry.confirmed_tracks():
            evidence_url = None
            blob = evidence.get(record.track_id)
            if blob:
                evidence_dir.mkdir(parents=True, exist_ok=True)
                filename = f"track_{record.track_id}.jpg"
                (evidence_dir / filename).write_bytes(blob)
                evidence_url = f"/media/video-evidence/task_{task.id}/{filename}"
            db.add(
                DetectionResult(
                    task_id=task.id,
                    image_path=f"{path.name}.track_{record.track_id:06d}.jpg",
                    annotated_image_url=evidence_url,
                    class_name=record.class_name,
                    class_id=record.class_id,
                    confidence=round(record.best_confidence, 4),
                    bbox=[round(value, 2) for value in record.best_bbox],
                    inference_time=average_inference,
                    image_width=width,
                    image_height=height,
                )
            )
            count_by_class_id[record.class_id] += 1
            name_map[record.class_id] = record.class_name
            summary = record.summary()
            summary["evidence_url"] = evidence_url
            summaries.append(summary)
            items.append(
                {
                    "filename": f"{path.name}.track_{record.track_id:06d}.jpg",
                    "track_id": record.track_id,
                    "class_name": record.class_name,
                    "duration": summary["duration"],
                    "best_confidence": round(record.best_confidence, 4),
                    "frame_index": record.best_frame_index,
                    "timestamp_seconds": round(record.best_timestamp, 2),
                    "object_count": 1,
                    "class_counts": {record.class_name: 1},
                    "detections": [
                        {
                            "class_id": record.class_id,
                            "class_name": record.class_name,
                            "confidence": round(record.best_confidence, 4),
                            "bbox": [round(value, 2) for value in record.best_bbox],
                        }
                    ],
                    "inference_time_ms": average_inference,
                    "annotated_image": evidence_url or "",
                }
            )
        price_summary = self.calculate_price(
            db,
            dict(count_by_class_id),
            name_map,
            model_version_id=task.model_version_id,
        )
        return summaries, items, price_summary

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
    def _calculate_total_price(
        db,
        detections: list[dict[str, Any]],
        model_version_id: int | None = None,
    ) -> dict[str, Any]:
        """根据逐个检测框汇总类别数量并计算总价。"""
        counts: dict[int, int] = Counter()
        name_map: dict[int, str] = {}
        for detection in detections:
            class_id = int(detection["class_id"])
            counts[class_id] += 1
            name_map[class_id] = detection["class_name"]

        return DetectionService.calculate_price(
            db,
            counts,
            name_map,
            model_version_id=model_version_id,
        )

    @staticmethod
    def calculate_price(
        db,
        class_counts: dict[int, int],
        class_names: dict[int, str] | None = None,
        model_version_id: int | None = None,
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

        mappings: dict[int, DatasetClassMapping] = {}
        if model_version_id is not None:
            model_version = db.query(ModelVersion).filter(ModelVersion.id == model_version_id).first()
            if model_version and model_version.dataset_version_id:
                mappings = {
                    item.class_index: item
                    for item in db.query(DatasetClassMapping)
                    .filter(DatasetClassMapping.dataset_version_id == model_version.dataset_version_id)
                    .all()
                }

        product_ids = [
            mappings[class_id].product_id
            for class_id in counts
            if class_id in mappings and mappings[class_id].product_id is not None
        ]
        prices_by_product = {
            price.product_id: price
            for price in db.query(ProductPrice)
            .filter(ProductPrice.product_id.in_(product_ids))
            .all()
        } if product_ids else {}
        products = {
            product.id: product
            for product in db.query(Product).filter(Product.id.in_(product_ids)).all()
        } if product_ids else {}

        category_ids = [class_id + 1 for class_id in counts]
        legacy_prices = {
            price.category_id: price
            for price in db.query(ProductPrice)
            .filter(ProductPrice.category_id.in_(category_ids))
            .all()
        }
        missing = []
        if missing:
            logger.warning("以下 category_id 未设置价格，暂不计入总价: %s", missing)

        items = []
        total_price = Decimal("0.00")
        priced_objects = 0
        unpriced_objects = 0
        for class_id, count in sorted(counts.items()):
            mapping = mappings.get(class_id)
            product_id = mapping.product_id if mapping else None
            product = products.get(product_id)
            category_id = mapping.category_id if mapping and mapping.category_id else class_id + 1
            price = prices_by_product.get(product_id) if product_id is not None else None
            if price is None and mapping is None:
                price = legacy_prices.get(category_id)
            has_price = price is not None
            if not has_price:
                missing.append(category_id)
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
                    "product_id": product_id,
                    "product_key": mapping.product_key if mapping else None,
                    "class_name": name_map.get(class_id) or (mapping.class_name if mapping else "") or (price.sku_name if price else ""),
                    "sku_name": price.sku_name if price else None,
                    "name": (price.name if price and price.name else (product.name if product else None)),
                    "barcode": (price.barcode if price and price.barcode else (product.barcode if product else None)),
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
            "missing_category_ids": sorted(set(missing)),
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
            device = self._get_device()
            with _PREDICT_LOCK:
                raw_results = model.predict(
                    source=[str(path) for path in paths],
                    conf=conf,
                    iou=iou,
                    imgsz=image_size,
                    device=device,
                    half=self._use_half(device),
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
            price_summary = self._calculate_total_price(
                db,
                all_detections,
                model_version_id=model_version_id,
            )

            return {
                "task_id": task.id,
                "source": source,
                "scene": scene.display_name,
                "model": model_path.name,
                "model_version_id": model_version_id,
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
