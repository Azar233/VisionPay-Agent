"""YOLO training service.

The service owns training task lifecycle management:
    - create TrainingTask records
    - run Ultralytics training in a background thread
    - persist task status and epoch metrics
    - parse results.csv after training
"""

from __future__ import annotations

import csv
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import TrainingMetric, TrainingTask

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_running_tasks: dict[str, Any] = {}
_running_lock = threading.Lock()


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        task_uuid = uuid.uuid4().hex[:8]
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
        try:
            task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
            if task is None:
                logger.error("Training task not found | id=%s", task_id)
                return

            data_yaml = Path(config["data_yaml"])
            if not data_yaml.exists():
                raise FileNotFoundError(f"data.yaml not found: {data_yaml}")

            task.status = "running"
            task.started_at = datetime.now()
            db.commit()

            TrainingService._prepare_ultralytics_env()
            from ultralytics import YOLO

            model_name = _clean_model_name(config.get("model_name"))
            weights = _weights_name(model_name)
            model = YOLO(weights)

            with _running_lock:
                _running_tasks[task_uuid] = model

            def on_train_epoch_end(trainer):
                TrainingService._record_epoch_from_trainer(
                    db=db,
                    task_id=task_id,
                    task_uuid=task_uuid,
                    trainer=trainer,
                    total_epochs=int(config.get("epochs", 50)),
                )

            model.add_callback("on_train_epoch_end", on_train_epoch_end)

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
            logger.info("YOLO training begins | task=%s data=%s", task_uuid, data_yaml)
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

        except Exception as exc:  # noqa: BLE001 - persisted for task status visibility.
            logger.error("YOLO training failed | task=%s error=%s", task_uuid, exc, exc_info=True)
            db.rollback()
            if task is None:
                task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
            if task is not None:
                task.status = "failed"
                task.error_message = str(exc)[:2000]
                task.completed_at = datetime.now()
                db.commit()
        finally:
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
            if existing is not None:
                return

            metrics = getattr(trainer, "metrics", {}) or {}
            loss_names = list(getattr(trainer, "loss_names", []) or [])
            loss_items = getattr(trainer, "loss_items", None)
            losses: dict[str, float | None] = {}
            if loss_items is not None and loss_names:
                try:
                    values = loss_items.detach().cpu().tolist()
                except AttributeError:
                    values = list(loss_items)
                losses = {
                    name.replace("train/", "").replace("_loss", ""): _safe_float(value)
                    for name, value in zip(loss_names, values)
                }

            metric = TrainingMetric(
                task_id=task_id,
                epoch=epoch,
                box_loss=losses.get("box")
                or _safe_float(metrics.get("train/box_loss") or metrics.get("metrics/box_loss")),
                cls_loss=losses.get("cls")
                or _safe_float(metrics.get("train/cls_loss") or metrics.get("metrics/cls_loss")),
                dfl_loss=losses.get("dfl")
                or _safe_float(metrics.get("train/dfl_loss") or metrics.get("metrics/dfl_loss")),
                precision=_safe_float(metrics.get("metrics/precision(B)")),
                recall=_safe_float(metrics.get("metrics/recall(B)")),
                map50=_safe_float(metrics.get("metrics/mAP50(B)")),
                map50_95=_safe_float(metrics.get("metrics/mAP50-95(B)")),
            )
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
            existing_epochs = {
                metric.epoch
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
                    if metric.epoch in existing_epochs:
                        continue
                    db.add(metric)
                    existing_epochs.add(metric.epoch)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse results.csv | path=%s error=%s", results_csv, exc)
            db.rollback()

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
        return {"message": "training task cancelled", "task_id": task_id}

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


training_service = TrainingService()
