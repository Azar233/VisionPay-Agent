"""Training API routes."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import get_db
from app.entity.db_models import DatasetVersion, DetectionScene, TrainingTask
from app.entity.schemas import (
    ModelExportRequest,
    ModelValidateRequest,
    TrainingRunImportRequest,
    TrainingTaskCreate,
)
from app.services.model_version_service import model_version_service
from app.training.training_service import training_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/training", tags=["模型训练"])
BACKEND_ROOT = Path(__file__).resolve().parents[2]


@router.get("/model-versions", summary="获取可用的检测模型版本")
def list_detection_model_versions(
    scene_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    del current_user
    return {"items": model_version_service.list(db, scene_id=scene_id)}


@router.post("/model-versions/{model_version_id}/set-default", summary="切换场景当前检测模型")
def set_default_detection_model(
    model_version_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    del current_user
    try:
        model = model_version_service.set_default(db, model_version_id=model_version_id)
        return model_version_service.serialize(db, model)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (BACKEND_ROOT / path).resolve()


def _dataset_candidates(scene: DetectionScene, request: TrainingTaskCreate) -> list[Path]:
    candidates: list[Path] = []
    explicit_dataset = _resolve_path(request.dataset_path)
    if explicit_dataset is not None:
        candidates.append(explicit_dataset)

    candidates.extend(
        [
            BACKEND_ROOT / settings.DATASET_BASE_DIR / "vision_pay",
            BACKEND_ROOT / settings.DATASET_BASE_DIR / scene.name,
            BACKEND_ROOT / settings.DATASET_BASE_DIR / scene.name / "yolo_dataset",
        ]
    )

    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve())
        if key not in seen:
            seen.add(key)
            unique_candidates.append(candidate)
    return unique_candidates


def _get_registered_dataset(
    db: Session,
    *,
    scene_id: int,
    dataset_version_id: int | None,
    use_current: bool = False,
    allow_archived: bool = False,
) -> DatasetVersion | None:
    query = db.query(DatasetVersion).filter(DatasetVersion.scene_id == scene_id)
    if dataset_version_id is not None:
        dataset = query.filter(DatasetVersion.id == dataset_version_id).first()
        if dataset is None:
            raise HTTPException(status_code=404, detail="数据集版本不存在或不属于当前场景")
    elif use_current:
        dataset = query.filter(DatasetVersion.is_current.is_(True)).first()
    else:
        dataset = None

    if dataset is None:
        return None
    allowed_statuses = {"ready", "archived"} if allow_archived else {"ready"}
    if dataset.status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="只有已冻结的数据集版本可以用于训练")
    return dataset


def _registered_dataset_config(
    dataset: DatasetVersion,
    *,
    require_files: bool,
) -> dict[str, Any]:
    if "://" in dataset.storage_path:
        raise HTTPException(
            status_code=422,
            detail="当前训练器只支持本地或集群挂载目录，不能直接训练远程 URI",
        )
    dataset_path = _resolve_path(dataset.storage_path)
    yaml_path = Path(dataset.data_yaml_path).expanduser()
    data_yaml = yaml_path.resolve() if yaml_path.is_absolute() else (dataset_path / yaml_path).resolve()
    if require_files:
        if not dataset_path.is_dir():
            raise HTTPException(status_code=400, detail=f"数据集目录不存在: {dataset_path}")
        if not data_yaml.is_file():
            raise HTTPException(status_code=400, detail=f"data.yaml 不存在: {data_yaml}")
    return {
        "dataset_version_id": dataset.id,
        "dataset_content_hash": dataset.content_hash,
        "dataset_path": str(dataset_path),
        "data_yaml": str(data_yaml),
        "dataset_size": (
            dataset.train_image_count + dataset.val_image_count + dataset.test_image_count
        ),
    }


def _build_training_config(
    db: Session,
    scene: DetectionScene,
    request: TrainingTaskCreate,
) -> dict[str, Any]:
    registered_dataset = _get_registered_dataset(
        db,
        scene_id=scene.id,
        dataset_version_id=request.dataset_version_id,
        use_current=request.dataset_version_id is None,
    )
    if registered_dataset is not None:
        dataset_config = _registered_dataset_config(registered_dataset, require_files=True)
        return {
            "model_name": request.model_name,
            "epochs": request.epochs,
            "img_size": request.img_size,
            "batch_size": request.batch_size,
            "device": request.device,
            "optimizer": request.optimizer,
            "lr0": request.lr0,
            "augment_config": request.augment_config,
            **dataset_config,
        }

    data_yaml = _resolve_path(request.data_yaml)
    dataset_path: Path | None = _resolve_path(request.dataset_path)

    if data_yaml is None:
        for candidate in _dataset_candidates(scene, request):
            yaml_candidate = candidate / "data.yaml"
            if yaml_candidate.exists():
                dataset_path = candidate
                data_yaml = yaml_candidate
                break

    if data_yaml is None or not data_yaml.exists():
        searched = [str(path / "data.yaml") for path in _dataset_candidates(scene, request)]
        raise HTTPException(
            status_code=400,
            detail={
                "message": "data.yaml 不存在，请先完成数据集准备",
                "searched": searched,
            },
        )

    if dataset_path is None:
        dataset_path = data_yaml.parent

    return {
        "model_name": request.model_name,
        "epochs": request.epochs,
        "img_size": request.img_size,
        "batch_size": request.batch_size,
        "device": request.device,
        "optimizer": request.optimizer,
        "lr0": request.lr0,
        "augment_config": request.augment_config,
        "dataset_path": str(dataset_path),
        "data_yaml": str(data_yaml),
    }


def _get_owned_task(db: Session, task_id: int, user_id: int) -> TrainingTask:
    task = (
        db.query(TrainingTask)
        .filter(TrainingTask.id == task_id, TrainingTask.user_id == user_id)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    return task


@router.post("/start")
async def start_training(
    request: TrainingTaskCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create and start a YOLO training task."""

    scene = db.query(DetectionScene).filter(DetectionScene.id == request.scene_id).first()
    if scene is None:
        raise HTTPException(status_code=404, detail="检测场景不存在")

    config = _build_training_config(db, scene, request)
    try:
        task = training_service.start_training(
            db=db,
            user_id=current_user.id,
            scene_id=request.scene_id,
            config=config,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("启动训练失败：%s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"启动训练失败：{exc}") from exc

    logger.info(
        "用户 %s 启动训练任务：scene=%s, model=%s, epochs=%s",
        current_user.username,
        scene.name,
        task.model_name,
        task.epochs,
    )
    return {
        "id": task.id,
        "task_uuid": task.task_uuid,
        "status": task.status,
        "model_name": task.model_name,
        "epochs": task.epochs,
        "dataset_size": task.dataset_size,
        "dataset_version_id": getattr(task, "dataset_version_id", None),
        "dataset_version": getattr(getattr(task, "dataset_version", None), "version", None),
        "message": "训练任务已创建，正在后台启动",
    }


@router.post("/import-run")
async def import_training_run(
    request: TrainingRunImportRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Import an offline/sbatch Ultralytics training run into task metrics."""

    scene = db.query(DetectionScene).filter(DetectionScene.id == request.scene_id).first()
    if scene is None:
        raise HTTPException(status_code=404, detail="检测场景不存在")

    config = request.model_dump(exclude_none=True)
    if request.dataset_version_id is not None:
        dataset = _get_registered_dataset(
            db,
            scene_id=scene.id,
            dataset_version_id=request.dataset_version_id,
            allow_archived=True,
        )
        config.update(_registered_dataset_config(dataset, require_files=False))

    try:
        result = training_service.import_training_run(
            db=db,
            user_id=current_user.id,
            scene_id=request.scene_id,
            config=config,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("导入离线训练结果失败：%s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"导入离线训练结果失败：{exc}") from exc

    logger.info(
        "用户 %s 导入离线训练结果：scene=%s, task=%s",
        current_user.username,
        scene.name,
        result.get("task", {}).get("task_uuid"),
    )
    return result


@router.get("/tasks")
async def list_training_tasks(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List current user's training tasks."""

    tasks = training_service.get_task_list(db, user_id=current_user.id)
    return {"total": len(tasks), "items": tasks}


@router.get("/status/{task_id}")
async def get_training_status(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get task status and latest metric."""

    _get_owned_task(db, task_id, current_user.id)
    status = training_service.get_training_status(db, task_id)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return status


@router.get("/metrics/{task_id}")
async def get_training_metrics(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all epoch metrics for a training task."""

    _get_owned_task(db, task_id, current_user.id)
    metrics = training_service.get_training_metrics(db, task_id)
    return {"task_id": task_id, "total": len(metrics), "metrics": metrics}


@router.get("/logs/{task_id}")
async def get_training_log(
    task_id: int,
    lines: int = 200,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Read the tail of a task-specific training log file."""

    task = _get_owned_task(db, task_id, current_user.id)
    max_lines = min(max(lines, 1), 2000)
    log = training_service.read_task_log(task.task_uuid, max_lines=max_lines)
    return {
        "task_id": task.id,
        "task_uuid": task.task_uuid,
        "exists": log["exists"],
        "path": log["path"],
        "lines": log["lines"],
    }




@router.post("/validate/{task_id}")
async def validate_training_task(
    task_id: int,
    request: ModelValidateRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Run validation for a completed training task and return an evaluation report."""

    _get_owned_task(db, task_id, current_user.id)
    request = request or ModelValidateRequest()
    try:
        return training_service.validate_model(
            db=db,
            task_id=task_id,
            split=request.split,
            device=request.device,
            img_size=request.img_size,
            conf=request.conf,
            iou=request.iou,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("模型评估失败：%s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"模型评估失败：{exc}") from exc


@router.post("/export/{task_id}")
async def export_training_model(
    task_id: int,
    request: ModelExportRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Export best.pt to backend/models and create a model version record."""

    _get_owned_task(db, task_id, current_user.id)
    request = request or ModelExportRequest()
    try:
        return training_service.export_model(
            db=db,
            task_id=task_id,
            version=request.version,
            description=request.description,
            set_default=request.set_default,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("模型导出失败：%s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"模型导出失败：{exc}") from exc


@router.get("/download/{task_id}")
async def download_training_model(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Download the best.pt weights file for a training task."""

    _get_owned_task(db, task_id, current_user.id)
    try:
        download = training_service.get_model_download_path(db, task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileResponse(
        path=str(download["path"]),
        media_type="application/octet-stream",
        filename=download["filename"],
    )


@router.post("/predict")
async def predict_training_image(
    task_id: int = Form(...),
    conf: float = Form(0.25),
    iou: float = Form(0.45),
    device: str = Form("cpu"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Upload a test image and run the trained best.pt for quick visual validation."""

    _get_owned_task(db, task_id, current_user.id)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        raise HTTPException(status_code=400, detail="仅支持 JPG/PNG/BMP/WEBP 图片")

    upload_dir = BACKEND_ROOT / settings.LOG_DIR / "predict_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"{uuid.uuid4().hex}{suffix}"
    try:
        upload_path.write_bytes(await file.read())
        if upload_path.stat().st_size == 0:
            raise HTTPException(status_code=400, detail="上传文件为空")
        return training_service.predict_test_image(
            db=db,
            task_id=task_id,
            image_path=upload_path,
            conf=conf,
            iou=iou,
            device=device,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("测试图验证失败：%s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"测试图验证失败：{exc}") from exc
    finally:
        try:
            upload_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("清理测试图临时文件失败：%s", upload_path)


@router.post("/stop/{task_id}")
async def stop_training(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Stop a running training task."""

    _get_owned_task(db, task_id, current_user.id)
    result = training_service.stop_training(db, task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/results/{task_uuid}")
async def get_results_csv(
    task_uuid: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Download the raw Ultralytics results.csv file."""

    task = (
        db.query(TrainingTask)
        .filter(TrainingTask.task_uuid == task_uuid, TrainingTask.user_id == current_user.id)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="训练任务不存在")

    results_path = BACKEND_ROOT / settings.TRAIN_OUTPUT_DIR / f"task_{task_uuid}" / "results.csv"
    if not results_path.exists():
        raise HTTPException(status_code=404, detail="results.csv 文件不存在")

    return FileResponse(
        path=str(results_path),
        media_type="text/csv",
        filename=f"training_results_{task_uuid}.csv",
    )
