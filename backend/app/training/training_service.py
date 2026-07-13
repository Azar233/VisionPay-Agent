"""YOLO training service.

The service owns training task lifecycle management:
    - create TrainingTask records
    - run Ultralytics training in a background thread
    - persist task status and epoch metrics
    - parse results.csv after training
"""

from __future__ import annotations

import base64
from collections import deque
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

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is installed with Ultralytics.
    yaml = None

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import ModelVersion, TrainingMetric, TrainingTask

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_running_tasks: dict[str, Any] = {}
_running_lock = threading.Lock()
_live_progress: dict[str, dict[str, Any]] = {}
_live_progress_lock = threading.Lock()
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
    epoch = max(1, int(float(row.get("epoch", "1"))))
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


def _metric_log_line(metric: TrainingMetric, total_epochs: int) -> str:
    progress = min(100, int(metric.epoch / max(total_epochs, 1) * 100))
    fields = [
        f"training progress epoch={metric.epoch}/{total_epochs}",
        f"progress={progress}%",
        f"box_loss={format(metric.box_loss, '.5f') if metric.box_loss is not None else '-'}",
        f"cls_loss={format(metric.cls_loss, '.5f') if metric.cls_loss is not None else '-'}",
        f"dfl_loss={format(metric.dfl_loss, '.5f') if metric.dfl_loss is not None else '-'}",
        f"precision={format(metric.precision, '.5f') if metric.precision is not None else '-'}",
        f"recall={format(metric.recall, '.5f') if metric.recall is not None else '-'}",
        f"map50={format(metric.map50, '.5f') if metric.map50 is not None else '-'}",
        f"map50_95={format(metric.map50_95, '.5f') if metric.map50_95 is not None else '-'}",
    ]
    return " | ".join(fields)


def _copy_metric_values(target: TrainingMetric, source: TrainingMetric) -> None:
    target.box_loss = source.box_loss
    target.cls_loss = source.cls_loss
    target.dfl_loss = source.dfl_loss
    target.precision = source.precision
    target.recall = source.recall
    target.map50 = source.map50
    target.map50_95 = source.map50_95
    target.lr = source.lr


def _format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "--:--"
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        return "--:--"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _progress_bar(percent: float, width: int = 24) -> str:
    clamped = min(100.0, max(0.0, percent))
    filled = int(round(clamped / 100 * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _tqdm_bar(percent: float, width: int = 10) -> str:
    clamped = min(100.0, max(0.0, percent))
    raw_filled = clamped / 100 * width
    full = min(width, int(raw_filled))
    remainder = raw_filled - full
    partials = "\u258f\u258e\u258d\u258c\u258b\u258a\u2589"
    bar = "\u2588" * full
    if full < width and remainder > 0:
        bar += partials[min(len(partials) - 1, int(remainder * len(partials)))]
    return bar.ljust(width)


def _tqdm_rate_text(rate: float | None) -> str:
    if not rate or rate <= 0:
        return "?it/s"
    if rate < 1:
        return f"{1 / rate:5.2f}s/it"
    return f"{rate:5.2f}it/s"


def _trainer_loader_length(trainer: Any) -> int | None:
    for attr in ("train_loader", "loader", "dataloader"):
        loader = getattr(trainer, attr, None)
        if loader is None:
            continue
        try:
            return max(1, len(loader))
        except TypeError:
            continue
    return None


def _trainer_losses(trainer: Any) -> dict[str, float | None]:
    loss_names = list(getattr(trainer, "loss_names", []) or [])
    loss_items = getattr(trainer, "loss_items", None)
    losses: dict[str, float | None] = {"box_loss": None, "cls_loss": None, "dfl_loss": None}
    if loss_items is None or not loss_names:
        return losses
    try:
        values = loss_items.detach().cpu().tolist()
    except AttributeError:
        try:
            values = list(loss_items)
        except TypeError:
            return losses
    for raw_name, value in zip(loss_names, values):
        name = raw_name.replace("train/", "").replace("_loss", "")
        key = f"{name}_loss" if name in {"box", "cls", "dfl"} else raw_name
        if key in losses:
            losses[key] = _safe_float(value)
    return losses


def _set_live_progress(task_uuid: str, progress: dict[str, Any]) -> None:
    with _live_progress_lock:
        current = _live_progress.get(task_uuid, {})
        current.update(progress)
        current["updated_at"] = datetime.now().isoformat()
        _live_progress[task_uuid] = current


def _get_live_progress(task_uuid: str) -> dict[str, Any] | None:
    with _live_progress_lock:
        progress = _live_progress.get(task_uuid)
        return dict(progress) if progress else None


def _build_tqdm_progress(
    phase: str,
    epoch: int,
    total_epochs: int,
    batch: int | None,
    total_batches: int | None,
    completed_units: int,
    total_units: int,
    elapsed: float,
    losses: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    safe_total_units = max(1, int(total_units or 1))
    safe_completed_units = min(safe_total_units, max(0, int(completed_units or 0)))
    percent = safe_completed_units / safe_total_units * 100
    rate = safe_completed_units / elapsed if elapsed > 0 and safe_completed_units > 0 else None
    eta = (safe_total_units - safe_completed_units) / rate if rate and safe_total_units >= safe_completed_units else None
    rate_text = _tqdm_rate_text(rate)
    elapsed_text = _format_duration(elapsed)
    eta_text = _format_duration(eta)
    bar = _tqdm_bar(percent)
    percent_int = min(100, max(0, int(round(percent))))
    losses = losses or {}
    loss_parts = [
        f"box_loss={losses.get('box_loss'):.4f}" if losses.get("box_loss") is not None else None,
        f"cls_loss={losses.get('cls_loss'):.4f}" if losses.get("cls_loss") is not None else None,
        f"dfl_loss={losses.get('dfl_loss'):.4f}" if losses.get("dfl_loss") is not None else None,
    ]
    loss_text = " ".join(part for part in loss_parts if part)
    tqdm_line = (
        f"{percent_int:3d}%|{bar}| {safe_completed_units}/{safe_total_units} "
        f"[{elapsed_text}<{eta_text}, {rate_text}]"
    )
    if phase == "train" and epoch and total_epochs:
        tqdm_line = f"Epoch {min(epoch, total_epochs)}/{total_epochs} {tqdm_line}"
    elif phase and phase not in {"train", "running"}:
        tqdm_line = f"{phase} {tqdm_line}"
    if loss_text:
        tqdm_line += f" | {loss_text}"
    return {
        "phase": phase,
        "epoch": epoch,
        "total_epochs": total_epochs,
        "batch": batch,
        "total_batches": total_batches,
        "completed_units": safe_completed_units,
        "total_units": safe_total_units,
        "percent": round(min(100.0, max(0.0, percent)), 2),
        "elapsed_seconds": elapsed,
        "elapsed_text": elapsed_text,
        "eta_seconds": eta,
        "eta_text": eta_text,
        "rate": rate,
        "rate_text": rate_text,
        "bar": bar,
        "tqdm_line": tqdm_line,
        **losses,
    }


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

        _set_live_progress(
            task.task_uuid,
            {
                "phase": "pending",
                "epoch": 0,
                "total_epochs": task.epochs,
                "batch": None,
                "total_batches": None,
                "percent": 0.0,
                "elapsed_text": "00:00",
                "eta_text": "--:--",
                "rate_text": "--it/s",
                "bar": _progress_bar(0),
                "tqdm_line": f"pending: {_progress_bar(0)}   0.0% | waiting to start",
            },
        )

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
        results_monitor_stop = threading.Event()
        results_monitor: threading.Thread | None = None
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

            live_started_at = time.perf_counter()
            live_state = {
                "started_at": live_started_at,
                "last_log_time": 0.0,
                "log_interval_seconds": float(config.get("log_interval_seconds", 2.0)),
            }
            initial_live_progress = _build_tqdm_progress(
                phase="train",
                epoch=0,
                total_epochs=int(config.get("epochs", 50)),
                batch=None,
                total_batches=None,
                completed_units=0,
                total_units=max(1, int(config.get("epochs", 50))),
                elapsed=0,
            )
            initial_live_progress["started_at_monotonic"] = live_started_at
            _set_live_progress(task_uuid, initial_live_progress)

            TrainingService._prepare_ultralytics_env()
            from ultralytics import YOLO

            model_name = _clean_model_name(config.get("model_name"))
            weights = _weights_name(model_name)
            _append_task_log(task_uuid, f"loading model weights={weights}")
            model = YOLO(weights)

            with _running_lock:
                _running_tasks[task_uuid] = model
            _append_task_log(task_uuid, "model registered as running")

            def on_train_batch_end(trainer):
                TrainingService._record_live_batch_progress(
                    task_uuid=task_uuid,
                    trainer=trainer,
                    total_epochs=int(config.get("epochs", 50)),
                    state=live_state,
                )

            def on_fit_epoch_end(trainer):
                TrainingService._record_live_batch_progress(
                    task_uuid=task_uuid,
                    trainer=trainer,
                    total_epochs=int(config.get("epochs", 50)),
                    state=live_state,
                    force_log=True,
                )
                TrainingService._record_epoch_from_trainer(
                    db=db,
                    task_id=task_id,
                    task_uuid=task_uuid,
                    trainer=trainer,
                    total_epochs=int(config.get("epochs", 50)),
                )

            # Ultralytics validates after on_train_epoch_end. on_fit_epoch_end is
            # the first epoch callback where current validation metrics exist.
            model.add_callback("on_train_batch_end", on_train_batch_end)
            model.add_callback("on_fit_epoch_end", on_fit_epoch_end)

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

            results_monitor = threading.Thread(
                target=TrainingService._monitor_results_csv,
                args=(
                    task_id,
                    task_uuid,
                    int(config.get("epochs", 50)),
                    output_dir,
                    results_monitor_stop,
                ),
                daemon=True,
                name=f"train-results-monitor-{task_uuid}",
            )
            results_monitor.start()
            _append_task_log(
                task_uuid,
                "results.csv monitor started; progress and losses will update after each epoch",
            )

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

            results_monitor_stop.set()
            if results_monitor is not None:
                results_monitor.join(timeout=10)
            TrainingService._parse_final_results(db, task_id, task_uuid, output_dir)
            _set_live_progress(
                task_uuid,
                _build_tqdm_progress(
                    phase="completed",
                    epoch=int(config.get("epochs", 50)),
                    total_epochs=int(config.get("epochs", 50)),
                    batch=None,
                    total_batches=None,
                    completed_units=int(config.get("epochs", 50)),
                    total_units=max(1, int(config.get("epochs", 50))),
                    elapsed=time.perf_counter() - live_started_at,
                ),
            )
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
            _set_live_progress(
                task_uuid,
                {
                    "phase": "failed",
                    "eta_text": "--:--",
                    "rate_text": "--it/s",
                    "tqdm_line": f"failed: {_progress_bar(0)} error={exc}",
                },
            )
        finally:
            results_monitor_stop.set()
            if results_monitor is not None and results_monitor.is_alive():
                results_monitor.join(timeout=5)
            if file_handler is not None:
                logging.getLogger().removeHandler(file_handler)
                file_handler.close()
            with _running_lock:
                _running_tasks.pop(task_uuid, None)
            db.close()


    @staticmethod
    def _record_live_batch_progress(
        task_uuid: str,
        trainer: Any,
        total_epochs: int,
        state: dict[str, Any],
        force_log: bool = False,
    ) -> None:
        try:
            epoch = int(getattr(trainer, "epoch", 0)) + 1
            total_batches = _trainer_loader_length(trainer)
            raw_batch_i = getattr(trainer, "batch_i", None)
            if raw_batch_i is None:
                fallback_key = f"batch_count_epoch_{epoch}"
                state[fallback_key] = int(state.get(fallback_key, 0)) + 1
                batch = state[fallback_key]
            else:
                batch = int(raw_batch_i) + 1
            if total_batches is None:
                completed_units = max(0, epoch - 1)
                total_units = max(1, total_epochs)
                batch_for_report = None
            else:
                batch = min(max(1, batch), total_batches)
                completed_units = batch
                total_units = total_batches
                batch_for_report = batch
            elapsed = time.perf_counter() - float(state.get("started_at", time.perf_counter()))
            progress = _build_tqdm_progress(
                phase="train",
                epoch=min(epoch, total_epochs),
                total_epochs=total_epochs,
                batch=batch_for_report,
                total_batches=total_batches,
                completed_units=completed_units,
                total_units=total_units,
                elapsed=elapsed,
                losses=_trainer_losses(trainer),
            )
            _set_live_progress(task_uuid, progress)
            now = time.perf_counter()
            log_interval = float(state.get("log_interval_seconds", 2.0))
            if force_log or log_interval <= 0 or now - float(state.get("last_log_time", 0.0)) >= log_interval:
                _append_task_log(task_uuid, progress["tqdm_line"])
                state["last_log_time"] = now
        except Exception as exc:  # noqa: BLE001
            logger.debug("live batch progress callback failed | task=%s error=%s", task_uuid, exc)

    @staticmethod
    def _upsert_metric_from_csv_row(
        db: Session,
        task_id: int,
        task_uuid: str,
        row: dict[str, str],
        total_epochs: int,
        log_progress: bool = False,
    ) -> int | None:
        try:
            metric = _metric_from_csv_row(task_id, row)
        except (TypeError, ValueError):
            return None
        existing = (
            db.query(TrainingMetric)
            .filter(TrainingMetric.task_id == task_id, TrainingMetric.epoch == metric.epoch)
            .first()
        )
        if existing is None:
            db.add(metric)
        else:
            _copy_metric_values(existing, metric)
            metric = existing
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is not None and task.status not in {"completed", "failed", "cancelled"}:
            task.current_epoch = min(metric.epoch, total_epochs)
            task.progress = min(99, int(metric.epoch / max(total_epochs, 1) * 100))
        db.commit()
        if log_progress:
            _append_task_log(task_uuid, _metric_log_line(metric, total_epochs))
        return metric.epoch

    @staticmethod
    def _sync_results_csv(
        db: Session,
        task_id: int,
        task_uuid: str,
        results_csv: Path,
        total_epochs: int,
        logged_epochs: set[int] | None = None,
    ) -> set[int]:
        if logged_epochs is None:
            logged_epochs = set()
        if not results_csv.exists():
            return logged_epochs
        with results_csv.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cleaned = {(key or "").strip(): (value or "").strip() for key, value in row.items()}
                if not cleaned.get("epoch"):
                    continue
                try:
                    source_epoch = int(float(cleaned["epoch"]))
                except (TypeError, ValueError):
                    continue
                saved_epoch = TrainingService._upsert_metric_from_csv_row(
                    db=db,
                    task_id=task_id,
                    task_uuid=task_uuid,
                    row=cleaned,
                    total_epochs=total_epochs,
                    log_progress=source_epoch not in logged_epochs,
                )
                if saved_epoch is not None:
                    logged_epochs.add(source_epoch)
                    metric = _metric_from_csv_row(task_id, cleaned)
                    live = _get_live_progress(task_uuid) or {}
                    start = live.get("started_at_monotonic")
                    elapsed = time.perf_counter() - float(start) if start is not None else 0.0
                    progress = _build_tqdm_progress(
                        phase="train",
                        epoch=min(metric.epoch, total_epochs),
                        total_epochs=total_epochs,
                        batch=None,
                        total_batches=None,
                        completed_units=min(metric.epoch, total_epochs),
                        total_units=max(1, total_epochs),
                        elapsed=max(0.0, elapsed),
                        losses={"box_loss": metric.box_loss, "cls_loss": metric.cls_loss, "dfl_loss": metric.dfl_loss},
                    )
                    if start is not None:
                        progress["started_at_monotonic"] = start
                    _set_live_progress(task_uuid, progress)
        return logged_epochs

    @staticmethod
    def _monitor_results_csv(
        task_id: int,
        task_uuid: str,
        total_epochs: int,
        output_dir: str | Path,
        stop_event: threading.Event,
    ) -> None:
        results_csv = Path(output_dir) / f"task_{task_uuid}" / "results.csv"
        logged_epochs: set[int] = set()
        monitor_db = SessionLocal()
        try:
            while not stop_event.is_set():
                try:
                    logged_epochs = TrainingService._sync_results_csv(
                        db=monitor_db,
                        task_id=task_id,
                        task_uuid=task_uuid,
                        results_csv=results_csv,
                        total_epochs=total_epochs,
                        logged_epochs=logged_epochs,
                    )
                except Exception as exc:  # noqa: BLE001
                    monitor_db.rollback()
                    logger.debug("results.csv monitor tick failed | task=%s error=%s", task_uuid, exc)
                stop_event.wait(5)
            try:
                TrainingService._sync_results_csv(
                    db=monitor_db,
                    task_id=task_id,
                    task_uuid=task_uuid,
                    results_csv=results_csv,
                    total_epochs=total_epochs,
                    logged_epochs=logged_epochs,
                )
            except Exception as exc:  # noqa: BLE001
                monitor_db.rollback()
                logger.debug("final results.csv monitor sync failed | task=%s error=%s", task_uuid, exc)
        finally:
            monitor_db.close()

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
    def import_training_run(
        db: Session,
        user_id: int,
        scene_id: int,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Import an Ultralytics run directory produced outside the web backend."""

        def _as_int(value: Any, default: int) -> int:
            if value is None or value == "":
                return default
            if isinstance(value, (list, tuple)):
                value = value[0] if value else default
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return default

        def _as_float(value: Any, default: float) -> float:
            if value is None or value == "":
                return default
            if isinstance(value, (list, tuple)):
                value = value[0] if value else default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def _as_device(value: Any, default: str = "0") -> str:
            if value is None or value == "":
                return default
            if isinstance(value, (list, tuple)):
                return ",".join(str(item) for item in value)
            return str(value)

        def _safe_task_uuid(value: str) -> str:
            cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)
            cleaned = cleaned.strip("_-")
            return cleaned[:100] or uuid.uuid4().hex[:8]

        run_dir = _resolve_path(config.get("run_dir"))
        if not run_dir.exists() or not run_dir.is_dir():
            raise FileNotFoundError(f"run_dir not found: {run_dir}")

        results_csv = run_dir / "results.csv"
        if not results_csv.exists():
            raise FileNotFoundError(f"results.csv not found: {results_csv}")

        args: dict[str, Any] = {}
        args_yaml = run_dir / "args.yaml"
        if args_yaml.exists() and yaml is not None:
            loaded = yaml.safe_load(args_yaml.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                args = loaded

        raw_uuid = config.get("task_uuid")
        if not raw_uuid:
            raw_uuid = run_dir.name[5:] if run_dir.name.startswith("task_") else run_dir.name
        task_uuid = _safe_task_uuid(str(raw_uuid))

        expected_run_dir = _task_dir(task_uuid)
        if expected_run_dir.resolve() != run_dir.resolve():
            expected_run_dir.parent.mkdir(parents=True, exist_ok=True)
            if not expected_run_dir.exists():
                expected_run_dir.symlink_to(run_dir, target_is_directory=True)
            elif expected_run_dir.resolve() != run_dir.resolve():
                raise ValueError(
                    f"expected task output path already exists and points elsewhere: {expected_run_dir}"
                )

        metrics: list[TrainingMetric] = []
        with results_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cleaned = {(key or "").strip(): (value or "").strip() for key, value in row.items()}
                if not any(cleaned.values()):
                    continue
                metrics.append(_metric_from_csv_row(task_id=0, row=cleaned))
        if not metrics:
            raise ValueError(f"no metrics found in results.csv: {results_csv}")

        max_epoch = max(metric.epoch for metric in metrics)
        model_name = _clean_model_name(str(config.get("model_name") or args.get("model") or "yolov11n"))

        data_yaml_value = config.get("data_yaml") or args.get("data")
        data_yaml = _resolve_path(str(data_yaml_value)) if data_yaml_value else None
        dataset_path_value = config.get("dataset_path")
        if dataset_path_value:
            dataset_path = _resolve_path(str(dataset_path_value))
        elif data_yaml is not None:
            dataset_path = data_yaml.parent
        else:
            dataset_path = run_dir

        epochs = _as_int(config.get("epochs") or args.get("epochs"), max_epoch)
        img_size = _as_int(config.get("img_size") or args.get("imgsz"), 640)
        batch_size = _as_int(config.get("batch_size") or args.get("batch"), 16)
        device = _as_device(config.get("device") or args.get("device"), "0")
        optimizer = str(config.get("optimizer") or args.get("optimizer") or "SGD")
        lr0 = _as_float(config.get("lr0") or args.get("lr0"), 0.01)
        status = str(config.get("status") or "completed")
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("status must be completed, failed, or cancelled")

        augment_config = config.get("augment_config")
        if augment_config is None:
            augment_config = {key: args[key] for key in _TRAIN_AUGMENT_KEYS if key in args}
            if not augment_config:
                augment_config = None
        _training_augment_kwargs(augment_config)

        task = db.query(TrainingTask).filter(TrainingTask.task_uuid == task_uuid).first()
        if task is not None and task.user_id != user_id:
            raise ValueError(f"task_uuid already belongs to another user: {task_uuid}")

        if task is None:
            task = TrainingTask(user_id=user_id, scene_id=scene_id, task_uuid=task_uuid)
            db.add(task)
            db.flush()

        task.scene_id = scene_id
        task.status = status
        task.model_name = model_name
        task.epochs = epochs
        task.current_epoch = max_epoch
        task.progress = 100 if status == "completed" else min(99, int(max_epoch / max(epochs, 1) * 100))
        task.img_size = img_size
        task.batch_size = batch_size
        task.device = device
        task.optimizer = optimizer
        task.lr0 = lr0
        task.augment_config = augment_config
        task.dataset_path = str(dataset_path)
        task.dataset_size = _count_dataset_images(dataset_path) if dataset_path.exists() else None
        task.data_yaml = str(data_yaml) if data_yaml is not None else None
        task.error_message = None if status == "completed" else f"imported offline run as {status}"
        task.started_at = datetime.fromtimestamp(args_yaml.stat().st_mtime if args_yaml.exists() else run_dir.stat().st_mtime)
        if status in {"completed", "failed", "cancelled"}:
            task.completed_at = datetime.fromtimestamp(results_csv.stat().st_mtime)

        db.query(TrainingMetric).filter(TrainingMetric.task_id == task.id).delete()
        for metric in sorted(metrics, key=lambda item: item.epoch):
            metric.task_id = task.id
            db.add(metric)
        db.commit()
        db.refresh(task)

        latest_metric = max(metrics, key=lambda item: item.epoch)
        progress_payload = _build_tqdm_progress(
            phase=status,
            epoch=max_epoch,
            total_epochs=epochs,
            batch=None,
            total_batches=None,
            completed_units=max_epoch,
            total_units=max(epochs, max_epoch, 1),
            elapsed=0,
        )
        progress_payload.update(
            {
                "box_loss": latest_metric.box_loss,
                "cls_loss": latest_metric.cls_loss,
                "dfl_loss": latest_metric.dfl_loss,
                "precision": latest_metric.precision,
                "recall": latest_metric.recall,
                "map50": latest_metric.map50,
                "map50_95": latest_metric.map50_95,
            }
        )
        progress_payload["percent"] = float(task.progress)
        _set_live_progress(task_uuid, progress_payload)

        _append_task_log(
            task_uuid,
            "imported offline training run\n"
            f"run_dir={run_dir}\n"
            f"results_csv={results_csv}\n"
            f"metrics_imported={len(metrics)}\n"
            f"status={status}",
        )

        external_log_value = config.get("log_path")
        external_log = _resolve_path(str(external_log_value)) if external_log_value else run_dir / "train.log"
        task_log = _task_log_path(task_uuid)
        if external_log.exists() and external_log.resolve() != task_log.resolve():
            tail = deque(maxlen=2000)
            with external_log.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    tail.append(line.rstrip("\n"))
            _append_task_log(
                task_uuid,
                "imported external train log tail\n"
                f"source={external_log}\n"
                + "\n".join(tail),
            )

        best_weights = expected_run_dir / "weights" / "best.pt"
        last_weights = expected_run_dir / "weights" / "last.pt"
        return {
            "message": "离线训练结果已导入",
            "task": TrainingService._serialize_task(task),
            "metrics_imported": len(metrics),
            "run_dir": str(expected_run_dir),
            "source_run_dir": str(run_dir),
            "results_csv": str(results_csv),
            "best_weights": str(best_weights) if best_weights.exists() else None,
            "last_weights": str(last_weights) if last_weights.exists() else None,
        }

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
            "live_progress": _get_live_progress(task.task_uuid),
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
