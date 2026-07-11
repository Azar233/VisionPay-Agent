"""YOLO training service.

The service owns training task lifecycle management:
    - create TrainingTask records
    - run Ultralytics training in a background thread
    - persist task status and epoch metrics
    - parse results.csv after training
"""

from __future__ import annotations

import base64
import csv
import contextlib
import json
import logging
import math
import os
import platform
import shutil
import socket
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import ModelVersion, TrainingMetric, TrainingTask

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_running_tasks: dict[str, Any] = {}
_running_lock = threading.Lock()
_TRAIN_AUGMENT_KEYS = {
    "hsv_h",
    "hsv_s",
    "hsv_v",
    "degrees",
    "translate",
    "scale",
    "shear",
    "perspective",
    "flipud",
    "fliplr",
    "bgr",
    "mosaic",
    "mixup",
    "copy_paste",
    "copy_paste_mode",
    "erasing",
    "close_mosaic",
}


class _StreamTee:
    """Write stream output to the original stream and the task log file."""

    def __init__(self, *streams: Any) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _first_existing(row: dict[str, str], keys: list[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _clean_model_name(model_name: str | None) -> str:
    model = (model_name or "yolov11n").strip()
    if model.endswith(".pt"):
        model = model[:-3]

    aliases = {
        "v11n": "yolov11n",
        "v11s": "yolov11s",
        "v11m": "yolov11m",
        "v11l": "yolov11l",
        "v11x": "yolov11x",
        "yolo11n": "yolov11n",
        "yolo11s": "yolov11s",
        "yolo11m": "yolov11m",
        "yolo11l": "yolov11l",
        "yolo11x": "yolov11x",
    }
    model = aliases.get(model.lower(), model.lower())

    allowed = {"yolov11n", "yolov11s", "yolov11m", "yolov11l", "yolov11x"}
    if model not in allowed:
        raise ValueError(f"Unsupported model_name: {model_name}")
    return model


def _weights_name(model_name: str) -> str:
    """Map project-facing yolov11* names to Ultralytics weight filenames."""

    # Ultralytics 8.x uses yolo11*.pt filenames for YOLOv11 models.
    if model_name.startswith("yolov11"):
        return model_name.replace("yolov11", "yolo11", 1) + ".pt"
    return model_name + ".pt"


def _normalize_device(device: str | int | None) -> str:
    """Normalize CPU, single-GPU, and multi-GPU device strings for Ultralytics."""

    raw = str(device if device is not None else "cpu").strip().lower().replace(" ", "")
    if raw in {"", "none"}:
        return "cpu"
    if raw in {"cpu", "mps"}:
        return raw
    if raw in {"cuda", "gpu"}:
        return "0"
    if raw == "all":
        return "0,1,2,3,4,5,6,7"

    indices: list[int] = []
    for part in raw.split(","):
        if not part:
            raise ValueError("device contains an empty GPU index")

        if "-" in part:
            bounds = part.split("-", 1)
            if len(bounds) != 2 or not all(bound.isdigit() for bound in bounds):
                raise ValueError(f"Invalid device range: {part}")
            start, end = (int(bound) for bound in bounds)
            if start > end:
                raise ValueError(f"Invalid descending device range: {part}")
            indices.extend(range(start, end + 1))
            continue

        if not part.isdigit():
            raise ValueError(
                "device must be cpu, cuda, all, a GPU index, a comma list, or a range like 0-7"
            )
        indices.append(int(part))

    if len(indices) != len(set(indices)):
        raise ValueError(f"Duplicate GPU indices in device: {device}")
    if any(index < 0 or index > 7 for index in indices):
        raise ValueError("Only GPU indices 0-7 are supported from the training UI")
    return ",".join(str(index) for index in indices)


def _resolve_path(path_value: str | Path | None, default_path: Path | None = None) -> Path:
    path = Path(path_value) if path_value else default_path
    if path is None:
        raise ValueError("Path value is required")
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _task_log_path(task_uuid: str) -> Path:
    return _resolve_path(settings.LOG_DIR) / "training" / f"task_{task_uuid}.log"


def _task_dir(task_uuid: str) -> Path:
    return _resolve_path(settings.TRAIN_OUTPUT_DIR) / f"task_{task_uuid}"


def _best_weights_path(task_uuid: str) -> Path:
    return _task_dir(task_uuid) / "weights" / "best.pt"


def _latest_eval_report_path(task_uuid: str) -> Path | None:
    task_path = _task_dir(task_uuid)
    if not task_path.exists():
        return None
    reports = sorted(
        task_path.rglob("eval_report.json"),
        key=lambda file: file.stat().st_mtime,
        reverse=True,
    )
    return reports[0] if reports else None


def _collect_eval_artifacts(output_dir: Path) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    if not output_dir.exists():
        return artifacts

    expected = {
        "confusion_matrix.png",
        "confusion_matrix_normalized.png",
        "PR_curve.png",
        "F1_curve.png",
        "P_curve.png",
        "R_curve.png",
        "results.png",
    }
    for file in output_dir.iterdir():
        if not file.is_file():
            continue
        if file.name in expected or file.name.startswith("val_batch"):
            artifacts[file.name] = str(file)
    return artifacts


def _class_names(names: Any) -> dict[int, str]:
    if isinstance(names, dict):
        return {int(key): str(value) for key, value in names.items()}
    if isinstance(names, (list, tuple)):
        return {index: str(value) for index, value in enumerate(names)}
    return {}


def _build_eval_report(
    task: TrainingTask | None,
    model: Any,
    metrics: Any,
    output_dir: Path,
    split: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    names = _class_names(getattr(model, "names", {}) or {})
    box_metrics = getattr(metrics, "box", None)
    overall = {
        "precision": _safe_float(getattr(box_metrics, "mp", None)),
        "recall": _safe_float(getattr(box_metrics, "mr", None)),
        "map50": _safe_float(getattr(box_metrics, "map50", None)),
        "map50_95": _safe_float(getattr(box_metrics, "map", None)),
    }

    per_class_ap: dict[str, float | None] = {}
    maps = getattr(box_metrics, "maps", None)
    if maps is not None:
        try:
            maps = maps.tolist()
        except AttributeError:
            maps = list(maps)
        for index, ap_value in enumerate(maps):
            class_name = names.get(index, str(index))
            per_class_ap[class_name] = _safe_float(ap_value)

    weak_classes = sorted(
        [
            {"class_name": class_name, "ap": ap}
            for class_name, ap in per_class_ap.items()
            if ap is not None
        ],
        key=lambda item: item["ap"],
    )[:10]

    return {
        "task_id": task.id if task is not None else None,
        "task_uuid": task.task_uuid if task is not None else None,
        "scene_id": task.scene_id if task is not None else None,
        "model_name": task.model_name if task is not None else None,
        "weights_path": str(_best_weights_path(task.task_uuid)) if task is not None else None,
        "data_yaml": str(config.get("data_yaml")),
        "split": split,
        "device": str(config.get("device")),
        "img_size": int(config.get("img_size", 640)),
        "conf": float(config.get("conf", 0.001)),
        "iou": float(config.get("iou", 0.6)),
        "output_dir": str(output_dir),
        "overall": overall,
        "precision": overall["precision"],
        "recall": overall["recall"],
        "map50": overall["map50"],
        "map50_95": overall["map50_95"],
        "per_class_ap": per_class_ap,
        "weak_classes": weak_classes,
        "artifacts": _collect_eval_artifacts(output_dir),
        "created_at": datetime.now().isoformat(),
    }


def _append_task_log(task_uuid: str, message: str) -> Path:
    log_path = _task_log_path(task_uuid)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] {message.rstrip()}\n")
    return log_path


def _training_env_report(config: dict[str, Any]) -> str:
    lines = [
        "training environment",
        f"hostname={socket.gethostname()}",
        f"python={sys.version.split()[0]}",
        f"platform={platform.platform()}",
        f"cwd={os.getcwd()}",
        f"data_yaml={config.get('data_yaml')}",
        f"dataset_path={config.get('dataset_path')}",
        f"model_name={config.get('model_name')}",
        f"epochs={config.get('epochs')}",
        f"img_size={config.get('img_size')}",
        f"batch_size={config.get('batch_size')}",
        f"device={config.get('device')}",
        f"optimizer={config.get('optimizer')}",
        f"lr0={config.get('lr0')}",
        f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES', '')}",
    ]
    try:
        import torch

        lines.extend(
            [
                f"torch={torch.__version__}",
                f"cuda_available={torch.cuda.is_available()}",
                f"cuda_device_count={torch.cuda.device_count()}",
            ]
        )
        for index in range(torch.cuda.device_count()):
            lines.append(f"cuda_device_{index}={torch.cuda.get_device_name(index)}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"torch_env_error={exc}")
    return "\n".join(lines)


def _count_dataset_images(dataset_path: Path) -> int:
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    image_root = dataset_path / "images"
    if not image_root.exists():
        return 0
    return sum(
        1
        for file in image_root.rglob("*")
        if file.is_file() and file.suffix.lower() in image_exts
    )


def _metric_from_csv_row(task_id: int, row: dict[str, str]) -> TrainingMetric:
    epoch = int(float(row.get("epoch", "0"))) + 1
    return TrainingMetric(
        task_id=task_id,
        epoch=epoch,
        box_loss=_safe_float(
            _first_existing(row, ["train/box_loss", "box_loss", "metrics/box_loss"])
        ),
        cls_loss=_safe_float(
            _first_existing(row, ["train/cls_loss", "cls_loss", "metrics/cls_loss"])
        ),
        dfl_loss=_safe_float(
            _first_existing(row, ["train/dfl_loss", "dfl_loss", "metrics/dfl_loss"])
        ),
        precision=_safe_float(
            _first_existing(row, ["metrics/precision(B)", "metrics/precision"])
        ),
        recall=_safe_float(_first_existing(row, ["metrics/recall(B)", "metrics/recall"])),
        map50=_safe_float(_first_existing(row, ["metrics/mAP50(B)", "metrics/mAP50"])),
        map50_95=_safe_float(
            _first_existing(row, ["metrics/mAP50-95(B)", "metrics/mAP50-95"])
        ),
        lr=_safe_float(_first_existing(row, ["lr/pg0", "lr0", "lr"])),
    )


def _trainer_epoch_values(trainer: Any) -> dict[str, float | None]:
    """Extract epoch-average losses and post-validation metrics from a trainer."""

    metrics = getattr(trainer, "metrics", {}) or {}
    loss_names = list(getattr(trainer, "loss_names", []) or [])
    loss_values = getattr(trainer, "tloss", None)
    if loss_values is None:
        loss_values = getattr(trainer, "loss_items", None)

    losses: dict[str, float | None] = {}
    if loss_values is not None and loss_names:
        try:
            values = loss_values.detach().cpu().tolist()
        except AttributeError:
            values = list(loss_values)
        losses = {
            name.replace("train/", "").replace("_loss", ""): _safe_float(value)
            for name, value in zip(loss_names, values)
        }

    def metric_value(*keys: str) -> float | None:
        for key in keys:
            value = _safe_float(metrics.get(key))
            if value is not None:
                return value
        return None

    return {
        "box_loss": losses.get("box")
        if losses.get("box") is not None
        else metric_value("train/box_loss", "metrics/box_loss"),
        "cls_loss": losses.get("cls")
        if losses.get("cls") is not None
        else metric_value("train/cls_loss", "metrics/cls_loss"),
        "dfl_loss": losses.get("dfl")
        if losses.get("dfl") is not None
        else metric_value("train/dfl_loss", "metrics/dfl_loss"),
        "precision": metric_value("metrics/precision(B)", "metrics/precision"),
        "recall": metric_value("metrics/recall(B)", "metrics/recall"),
        "map50": metric_value("metrics/mAP50(B)", "metrics/mAP50"),
        "map50_95": metric_value("metrics/mAP50-95(B)", "metrics/mAP50-95"),
    }


def _training_augment_kwargs(config: Any) -> dict[str, Any]:
    """Return supported Ultralytics augmentation overrides."""

    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ValueError("augment_config must be an object")
    unknown = sorted(set(config) - _TRAIN_AUGMENT_KEYS)
    if unknown:
        raise ValueError(f"Unsupported augment_config keys: {', '.join(unknown)}")
    return {key: value for key, value in config.items() if value is not None}


class TrainingService:
    """Service for managing YOLO training tasks."""

    @staticmethod
    def start_training(
        db: Session,
        user_id: int,
        scene_id: int,
        config: dict[str, Any],
    ) -> TrainingTask:
        """Create a training task and start it in a background thread."""

        model_name = _clean_model_name(config.get("model_name", "yolov11n"))
        dataset_path = _resolve_path(
            config.get("dataset_path"),
            PROJECT_ROOT / settings.DATASET_BASE_DIR / "vision_pay",
        )
        data_yaml = _resolve_path(config.get("data_yaml"), dataset_path / "data.yaml")

        if not data_yaml.exists():
            raise FileNotFoundError(f"data.yaml not found: {data_yaml}")

        device = _normalize_device(config.get("device", "cpu"))
        _training_augment_kwargs(config.get("augment_config"))
        task_uuid = uuid.uuid4().hex[:8]
        log_path = _append_task_log(
            task_uuid,
            "created training task\n"
            f"user_id={user_id}\n"
            f"scene_id={scene_id}\n"
            f"model_name={model_name}\n"
            f"data_yaml={data_yaml}\n"
            f"dataset_path={dataset_path}\n"
            f"device={device}",
        )
        task = TrainingTask(
            user_id=user_id,
            scene_id=scene_id,
            task_uuid=task_uuid,
            status="pending",
            model_name=model_name,
            epochs=int(config.get("epochs", 50)),
            img_size=int(config.get("img_size", 640)),
            batch_size=int(config.get("batch_size", 8)),
            device=device,
            optimizer=str(config.get("optimizer", "SGD")),
            lr0=float(config.get("lr0", 0.01)),
            augment_config=config.get("augment_config"),
            dataset_path=str(dataset_path),
            dataset_size=_count_dataset_images(dataset_path),
            data_yaml=str(data_yaml),
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        thread_config = {
            **config,
            "model_name": model_name,
            "dataset_path": str(dataset_path),
            "data_yaml": str(data_yaml),
            "epochs": task.epochs,
            "img_size": task.img_size,
            "batch_size": task.batch_size,
            "device": device,
            "optimizer": task.optimizer,
            "lr0": task.lr0,
        }
        thread = threading.Thread(
            target=TrainingService._run_training,
            args=(task.id, task.task_uuid, thread_config),
            daemon=True,
            name=f"train-{task.task_uuid}",
        )
        thread.start()

        logger.info(
            "Training task started | id=%s uuid=%s model=%s epochs=%s device=%s",
            task.id,
            task.task_uuid,
            task.model_name,
            task.epochs,
            task.device,
        )
        logger.info("Training task log initialized | task=%s path=%s", task_uuid, log_path)
        return task

    @staticmethod
    def _prepare_ultralytics_env() -> None:
        yolo_config_dir = _resolve_path(settings.YOLO_CONFIG_DIR)
        yolo_config_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(yolo_config_dir))

    @staticmethod
    def _run_training(task_id: int, task_uuid: str, config: dict[str, Any]) -> None:
        """Run a YOLO training task in a background thread."""

        db = SessionLocal()
        task: TrainingTask | None = None
        file_handler: logging.Handler | None = None
        try:
            log_path = _task_log_path(task_uuid)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
            if task is None:
                logger.error("Training task not found | id=%s", task_id)
                _append_task_log(task_uuid, f"training task not found | id={task_id}")
                return

            data_yaml = Path(config["data_yaml"])
            if not data_yaml.exists():
                raise FileNotFoundError(f"data.yaml not found: {data_yaml}")

            _append_task_log(task_uuid, _training_env_report(config))
            task.status = "running"
            task.started_at = datetime.now()
            db.commit()
            _append_task_log(task_uuid, "status=running")

            TrainingService._prepare_ultralytics_env()
            from ultralytics import YOLO

            model_name = _clean_model_name(config.get("model_name"))
            weights = _weights_name(model_name)
            _append_task_log(task_uuid, f"loading model weights={weights}")
            model = YOLO(weights)

            with _running_lock:
                _running_tasks[task_uuid] = model
            _append_task_log(task_uuid, "model registered as running")

            def on_train_epoch_end(trainer):
                TrainingService._record_epoch_from_trainer(
                    db=db,
                    task_id=task_id,
                    task_uuid=task_uuid,
                    trainer=trainer,
                    total_epochs=int(config.get("epochs", 50)),
                )

            # Ultralytics validates after on_train_epoch_end. on_fit_epoch_end is
            # the first epoch callback where current validation metrics exist.
            model.add_callback("on_fit_epoch_end", on_train_epoch_end)

            output_dir = _resolve_path(settings.TRAIN_OUTPUT_DIR)
            output_dir.mkdir(parents=True, exist_ok=True)

            train_kwargs = {
                "data": str(data_yaml),
                "epochs": int(config.get("epochs", 50)),
                "imgsz": int(config.get("img_size", 640)),
                "batch": int(config.get("batch_size", 8)),
                "device": _normalize_device(config.get("device", "cpu")),
                "optimizer": str(config.get("optimizer", "SGD")),
                "lr0": float(config.get("lr0", 0.01)),
                "project": str(output_dir),
                "name": f"task_{task_uuid}",
                "exist_ok": True,
                "save": True,
                "plots": False,
                "verbose": True,
            }
            train_kwargs.update(_training_augment_kwargs(config.get("augment_config")))
            logger.info("YOLO training begins | task=%s data=%s", task_uuid, data_yaml)
            _append_task_log(task_uuid, f"YOLO training begins\ntrain_kwargs={train_kwargs}")

            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
            )
            logging.getLogger().addHandler(file_handler)

            with log_path.open("a", encoding="utf-8") as log_file:
                stdout = _StreamTee(sys.stdout, log_file)
                stderr = _StreamTee(sys.stderr, log_file)
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    model.train(**train_kwargs)

            task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
            if task is not None and task.status != "cancelled":
                task.status = "completed"
                task.progress = 100
                task.current_epoch = int(config.get("epochs", 50))
                task.completed_at = datetime.now()
                db.commit()

            TrainingService._parse_final_results(db, task_id, task_uuid, output_dir)
            logger.info("YOLO training completed | task=%s", task_uuid)
            _append_task_log(task_uuid, "YOLO training completed")

        except Exception as exc:  # noqa: BLE001 - persisted for task status visibility.
            logger.error("YOLO training failed | task=%s error=%s", task_uuid, exc, exc_info=True)
            _append_task_log(
                task_uuid,
                f"YOLO training failed | error={exc}\n{traceback.format_exc()}",
            )
            db.rollback()
            if task is None:
                task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
            if task is not None:
                task.status = "failed"
                task.error_message = str(exc)[:2000]
                task.completed_at = datetime.now()
                db.commit()
        finally:
            if file_handler is not None:
                logging.getLogger().removeHandler(file_handler)
                file_handler.close()
            with _running_lock:
                _running_tasks.pop(task_uuid, None)
            db.close()

    @staticmethod
    def _record_epoch_from_trainer(
        db: Session,
        task_id: int,
        task_uuid: str,
        trainer: Any,
        total_epochs: int,
    ) -> None:
        """Best-effort epoch metric persistence from Ultralytics callbacks."""

        try:
            epoch = int(getattr(trainer, "epoch", 0)) + 1
            existing = (
                db.query(TrainingMetric)
                .filter(TrainingMetric.task_id == task_id, TrainingMetric.epoch == epoch)
                .first()
            )
            values = _trainer_epoch_values(trainer)
            metric = existing or TrainingMetric(task_id=task_id, epoch=epoch)
            for field, value in values.items():
                setattr(metric, field, value)
            if existing is None:
                db.add(metric)

            task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
            if task is not None:
                task.current_epoch = epoch
                task.progress = min(100, int(epoch / max(total_epochs, 1) * 100))
            db.commit()
            logger.debug("Epoch metric recorded | task=%s epoch=%s", task_uuid, epoch)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Epoch callback failed | task=%s error=%s", task_uuid, exc)
            db.rollback()

    @staticmethod
    def _parse_final_results(
        db: Session,
        task_id: int,
        task_uuid: str,
        output_dir: str | Path | None = None,
    ) -> None:
        output_path = Path(output_dir) if output_dir else _resolve_path(settings.TRAIN_OUTPUT_DIR)
        results_csv = output_path / f"task_{task_uuid}" / "results.csv"
        if not results_csv.exists():
            logger.warning("results.csv not found | path=%s", results_csv)
            return

        try:
            existing_metrics = {
                metric.epoch: metric
                for metric in db.query(TrainingMetric)
                .filter(TrainingMetric.task_id == task_id)
                .all()
            }

            with results_csv.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cleaned = {
                        (key or "").strip(): (value or "").strip()
                        for key, value in row.items()
                    }
                    metric = _metric_from_csv_row(task_id, cleaned)
                    existing = existing_metrics.get(metric.epoch)
                    if existing is None:
                        db.add(metric)
                        existing_metrics[metric.epoch] = metric
                        continue
                    for field in [
                        "box_loss",
                        "cls_loss",
                        "dfl_loss",
                        "precision",
                        "recall",
                        "map50",
                        "map50_95",
                        "lr",
                    ]:
                        setattr(existing, field, getattr(metric, field))
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse results.csv | path=%s error=%s", results_csv, exc)
            db.rollback()

    @staticmethod
    def validate_model(
        db: Session,
        task_id: int,
        split: str = "val",
        device: str | None = None,
        img_size: int | None = None,
        conf: float = 0.001,
        iou: float = 0.6,
    ) -> dict[str, Any]:
        """Run Ultralytics validation for a trained task and persist a JSON report."""

        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            raise ValueError("training task not found")
        if split not in {"train", "val", "test"}:
            raise ValueError("split must be train, val, or test")

        weights_path = _best_weights_path(task.task_uuid)
        if not weights_path.exists():
            raise FileNotFoundError(f"best.pt not found: {weights_path}")

        default_data_yaml = (
            _resolve_path(task.dataset_path) / "data.yaml" if task.dataset_path else None
        )
        data_yaml = _resolve_path(task.data_yaml, default_data_yaml)
        if not data_yaml.exists():
            raise FileNotFoundError(f"data.yaml not found: {data_yaml}")

        eval_device = _normalize_device(device if device is not None else task.device or "cpu")
        eval_img_size = int(img_size or task.img_size or 640)
        task_path = _task_dir(task.task_uuid)
        task_path.mkdir(parents=True, exist_ok=True)
        val_name = f"val_{split}"

        TrainingService._prepare_ultralytics_env()
        from ultralytics import YOLO

        val_kwargs = {
            "data": str(data_yaml),
            "split": split,
            "conf": float(conf),
            "iou": float(iou),
            "imgsz": eval_img_size,
            "device": eval_device,
            "project": str(task_path),
            "name": val_name,
            "exist_ok": True,
            "plots": True,
            "verbose": True,
        }
        _append_task_log(task.task_uuid, f"model validation begins\nval_kwargs={val_kwargs}")
        model = YOLO(str(weights_path))
        log_path = _task_log_path(task.task_uuid)
        with log_path.open("a", encoding="utf-8") as log_file:
            stdout = _StreamTee(sys.stdout, log_file)
            stderr = _StreamTee(sys.stderr, log_file)
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                metrics = model.val(**val_kwargs)

        output_dir = Path(getattr(metrics, "save_dir", task_path / val_name))
        report = _build_eval_report(
            task=task,
            model=model,
            metrics=metrics,
            output_dir=output_dir,
            split=split,
            config={
                "data_yaml": str(data_yaml),
                "device": eval_device,
                "img_size": eval_img_size,
                "conf": conf,
                "iou": iou,
            },
        )
        report_path = output_dir / "eval_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)
        _append_task_log(task.task_uuid, f"model validation completed\nreport_path={report_path}")
        return report

    @staticmethod
    def export_model(
        db: Session,
        task_id: int,
        version: str | None = None,
        description: str | None = None,
        set_default: bool = True,
    ) -> dict[str, Any]:
        """Copy best.pt into backend/models and create a ModelVersion record."""

        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            raise ValueError("training task not found")
        if task.status != "completed":
            raise ValueError("only completed training tasks can be exported")

        weights_path = _best_weights_path(task.task_uuid)
        if not weights_path.exists():
            raise FileNotFoundError(f"best.pt not found: {weights_path}")

        version_value = version or f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        safe_version = "".join(
            char if char.isalnum() or char in {".", "_", "-"} else "_"
            for char in version_value
        )
        model_dir = PROJECT_ROOT / "models" / f"scene_{task.scene_id}_{safe_version}"
        model_dir.mkdir(parents=True, exist_ok=True)
        exported_weights = model_dir / "best.pt"
        shutil.copy2(weights_path, exported_weights)

        report: dict[str, Any] = {}
        report_path = _latest_eval_report_path(task.task_uuid)
        if report_path is not None and report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            shutil.copy2(report_path, model_dir / "eval_report.json")
            for artifact_path in (report.get("artifacts") or {}).values():
                artifact = Path(artifact_path)
                if artifact.exists() and artifact.is_file():
                    shutil.copy2(artifact, model_dir / artifact.name)

        latest_metric = (
            db.query(TrainingMetric)
            .filter(TrainingMetric.task_id == task_id)
            .order_by(TrainingMetric.epoch.desc())
            .first()
        )
        overall = report.get("overall") or {}
        if latest_metric is not None:
            if overall.get("precision") is None:
                overall["precision"] = latest_metric.precision
            if overall.get("recall") is None:
                overall["recall"] = latest_metric.recall
            if overall.get("map50") is None:
                overall["map50"] = latest_metric.map50
            if overall.get("map50_95") is None:
                overall["map50_95"] = latest_metric.map50_95

        if set_default:
            db.query(ModelVersion).filter(ModelVersion.scene_id == task.scene_id).update(
                {"is_default": False}
            )

        model_version = ModelVersion(
            scene_id=task.scene_id,
            training_task_id=task.id,
            version=version_value,
            model_name=f"{task.model_name}_{task.task_uuid}",
            model_type=task.model_name,
            status="active",
            model_path=str(exported_weights),
            minio_url=None,
            map50=_safe_float(overall.get("map50")),
            map50_95=_safe_float(overall.get("map50_95")),
            precision=_safe_float(overall.get("precision")),
            recall=_safe_float(overall.get("recall")),
            per_class_ap=report.get("per_class_ap") or None,
            description=description,
            file_size=exported_weights.stat().st_size,
            is_default=set_default,
        )
        db.add(model_version)
        db.commit()
        db.refresh(model_version)
        _append_task_log(
            task.task_uuid,
            f"model exported\nmodel_version_id={model_version.id}\nmodel_path={exported_weights}",
        )
        return {
            "message": "model exported",
            "model_version": TrainingService._serialize_model_version(model_version),
            "model_path": str(exported_weights),
            "model_dir": str(model_dir),
            "report_path": str(model_dir / "eval_report.json") if report else None,
        }

    @staticmethod
    def get_model_download_path(db: Session, task_id: int) -> dict[str, Any]:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            raise ValueError("training task not found")
        weights_path = _best_weights_path(task.task_uuid)
        if not weights_path.exists():
            raise FileNotFoundError(f"best.pt not found: {weights_path}")
        return {
            "path": weights_path,
            "filename": f"{task.model_name}_{task.task_uuid}_best.pt",
            "file_size": weights_path.stat().st_size,
        }

    @staticmethod
    def predict_test_image(
        db: Session,
        task_id: int,
        image_path: str | Path,
        conf: float = 0.25,
        iou: float = 0.45,
        device: str = "cpu",
    ) -> dict[str, Any]:
        """Run the trained best.pt on a single uploaded image and return detections."""

        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            raise ValueError("training task not found")

        weights_path = _best_weights_path(task.task_uuid)
        if not weights_path.exists():
            raise FileNotFoundError(f"best.pt not found: {weights_path}")

        source_path = Path(image_path)
        if not source_path.exists():
            raise FileNotFoundError(f"image not found: {source_path}")

        TrainingService._prepare_ultralytics_env()
        from ultralytics import YOLO
        import cv2

        model = YOLO(str(weights_path))
        started_at = time.perf_counter()
        results = model.predict(
            source=str(source_path),
            conf=float(conf),
            iou=float(iou),
            imgsz=int(task.img_size or 640),
            device=_normalize_device(device),
            verbose=False,
        )
        elapsed = time.perf_counter() - started_at
        result = results[0]
        names = _class_names(getattr(result, "names", None) or getattr(model, "names", {}) or {})

        detections: list[dict[str, Any]] = []
        class_counts: dict[str, int] = {}
        boxes = getattr(result, "boxes", None)
        if boxes is not None:
            for box in boxes:
                cls_id = int(box.cls.detach().cpu().item())
                score = float(box.conf.detach().cpu().item())
                xyxy = [float(value) for value in box.xyxy[0].detach().cpu().tolist()]
                class_name = names.get(cls_id, str(cls_id))
                class_counts[class_name] = class_counts.get(class_name, 0) + 1
                detections.append(
                    {
                        "class_id": cls_id,
                        "class_name": class_name,
                        "confidence": score,
                        "bbox": xyxy,
                    }
                )

        annotated = result.plot()
        ok, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        annotated_image = None
        if ok:
            annotated_image = "data:image/jpeg;base64," + base64.b64encode(buffer).decode("ascii")

        return {
            "task_id": task.id,
            "task_uuid": task.task_uuid,
            "model_name": task.model_name,
            "total_objects": len(detections),
            "detections": detections,
            "class_counts": class_counts,
            "inference_time": elapsed,
            "annotated_image": annotated_image,
        }

    @staticmethod
    def get_training_status(db: Session, task_id: int) -> dict[str, Any]:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            return {"error": "training task not found"}

        latest_metric = (
            db.query(TrainingMetric)
            .filter(TrainingMetric.task_id == task_id)
            .order_by(TrainingMetric.epoch.desc())
            .first()
        )
        with _running_lock:
            is_running = task.task_uuid in _running_tasks

        return {
            "task": TrainingService._serialize_task(task),
            "latest_metric": TrainingService._serialize_metric(latest_metric)
            if latest_metric
            else None,
            "is_running": is_running,
        }

    @staticmethod
    def get_training_metrics(db: Session, task_id: int) -> list[dict[str, Any]]:
        metrics = (
            db.query(TrainingMetric)
            .filter(TrainingMetric.task_id == task_id)
            .order_by(TrainingMetric.epoch.asc())
            .all()
        )
        return [TrainingService._serialize_metric(metric) for metric in metrics]

    @staticmethod
    def stop_training(db: Session, task_id: int) -> dict[str, Any]:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            return {"error": "training task not found"}
        if task.status != "running":
            return {"error": f"task status is {task.status}, cannot stop"}

        with _running_lock:
            model = _running_tasks.get(task.task_uuid)
            if model is not None and getattr(model, "trainer", None) is not None:
                trainer = model.trainer
                if hasattr(trainer, "stop"):
                    trainer.stop()
                else:
                    setattr(trainer, "stop_training", True)

        task.status = "cancelled"
        task.completed_at = datetime.now()
        db.commit()
        _append_task_log(task.task_uuid, "training task cancelled by user")
        return {"message": "training task cancelled", "task_id": task_id}

    @staticmethod
    def get_task_log_path(task_uuid: str) -> Path:
        return _task_log_path(task_uuid)

    @staticmethod
    def read_task_log(task_uuid: str, max_lines: int = 200) -> dict[str, Any]:
        path = _task_log_path(task_uuid)
        if not path.exists():
            return {"exists": False, "path": str(path), "lines": []}

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if max_lines > 0:
            lines = lines[-max_lines:]
        return {"exists": True, "path": str(path), "lines": lines}

    @staticmethod
    def get_task_list(
        db: Session,
        user_id: int | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query = db.query(TrainingTask)
        if user_id is not None:
            query = query.filter(TrainingTask.user_id == user_id)
        tasks = query.order_by(TrainingTask.created_at.desc()).limit(limit).all()
        return [TrainingService._serialize_task(task) for task in tasks]

    @staticmethod
    def parse_results_csv(results_csv_path: str | Path) -> list[dict[str, Any]]:
        path = Path(results_csv_path)
        if not path.exists():
            return []

        parsed: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cleaned = {(key or "").strip(): (value or "").strip() for key, value in row.items()}
                metric = _metric_from_csv_row(task_id=0, row=cleaned)
                parsed.append(TrainingService._serialize_metric(metric))
        return parsed

    @staticmethod
    def _serialize_task(task: TrainingTask) -> dict[str, Any]:
        return {
            "id": task.id,
            "task_uuid": task.task_uuid,
            "status": task.status,
            "model_name": task.model_name,
            "epochs": task.epochs,
            "current_epoch": task.current_epoch,
            "progress": task.progress,
            "device": task.device,
            "batch_size": task.batch_size,
            "img_size": task.img_size,
            "dataset_size": task.dataset_size,
            "dataset_path": task.dataset_path,
            "data_yaml": task.data_yaml,
            "log_path": str(_task_log_path(task.task_uuid)),
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "error_message": task.error_message,
        }

    @staticmethod
    def _serialize_metric(metric: TrainingMetric) -> dict[str, Any]:
        return {
            "epoch": metric.epoch,
            "box_loss": metric.box_loss,
            "cls_loss": metric.cls_loss,
            "dfl_loss": metric.dfl_loss,
            "precision": metric.precision,
            "recall": metric.recall,
            "map50": metric.map50,
            "map50_95": metric.map50_95,
            "lr": metric.lr,
        }

    @staticmethod
    def _serialize_model_version(model_version: ModelVersion) -> dict[str, Any]:
        scene = getattr(model_version, "scene", None)
        return {
            "id": model_version.id,
            "scene_id": model_version.scene_id,
            "scene_name": getattr(scene, "name", None),
            "training_task_id": model_version.training_task_id,
            "version": model_version.version,
            "model_name": model_version.model_name,
            "model_type": model_version.model_type,
            "status": model_version.status,
            "model_path": model_version.model_path,
            "minio_url": model_version.minio_url,
            "map50": model_version.map50,
            "map50_95": model_version.map50_95,
            "precision": model_version.precision,
            "recall": model_version.recall,
            "per_class_ap": model_version.per_class_ap,
            "description": model_version.description,
            "file_size": model_version.file_size,
            "is_default": model_version.is_default,
            "created_at": model_version.created_at.isoformat()
            if model_version.created_at
            else None,
        }


training_service = TrainingService()
