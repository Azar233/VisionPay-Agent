"""Dataset version management API.

Training and model deployment are intentionally out of scope for this router.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config.settings import settings
from app.database.session import SessionLocal, get_db
from app.entity.db_models import DatasetVersion
from app.entity.schemas import (
    DatasetValidationRequest,
    DatasetValidationResponse,
    DatasetBaselineImportRequest,
    DatasetDeriveRequest,
    DatasetMutationResponse,
    DatasetProductCommitRequest,
    DatasetProductDeleteRequest,
    DatasetProductStagingResponse,
    DatasetVersionCreate,
    DatasetVersionListResponse,
    DatasetVersionResponse,
    DatasetVersionUpdate,
)
from app.services.dataset_annotation_service import dataset_annotation_service
from app.services.dataset_workspace_service import dataset_workspace_service
from app.services.model_import_service import model_import_service
from app.services.model_version_service import model_version_service
from app.services.dataset_service import (
    DatasetConflictError,
    DatasetLifecycleError,
    DatasetNotFoundError,
    dataset_service,
)
from app.storage.dataset_operation_store import dataset_operation_store

router = APIRouter(prefix="/api/datasets", tags=["数据集版本"])
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _raise_service_error(exc: ValueError) -> None:
    if isinstance(exc, DatasetNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, DatasetConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _operation_progress(task_id: str):
    last_update = {"progress": -1, "time": 0.0}

    def update(progress: int, message: str) -> None:
        normalized = max(0, min(99, int(progress)))
        now = time.monotonic()
        if normalized == last_update["progress"] and now - last_update["time"] < 0.5:
            return
        dataset_operation_store.update(
            task_id,
            status="running",
            progress=normalized,
            message=message,
        )
        last_update.update(progress=normalized, time=now)

    return update


def _fail_operation(task_id: str, exc: Exception) -> None:
    current = dataset_operation_store.get(task_id) or {}
    dataset_operation_store.update(
        task_id,
        status="failed",
        progress=min(99, int(current.get("progress", 0))),
        message=str(exc) or "数据集操作失败",
        result=None,
    )


def _run_derive_operation(
    *,
    task_id: str,
    parent_id: int,
    payload: dict,
    user_id: int,
    bind=None,
) -> None:
    db = SessionLocal() if bind is None else Session(bind=bind)
    try:
        dataset = dataset_workspace_service.derive(
            db,
            parent_id=parent_id,
            **payload,
            user_id=user_id,
            progress_callback=_operation_progress(task_id),
        )
        dataset_operation_store.update(
            task_id,
            status="completed",
            progress=100,
            message="派生版本已创建",
            result={"dataset": jsonable_encoder(dataset_service.serialize(dataset))},
        )
    except Exception as exc:  # noqa: BLE001 - surfaced through the task status endpoint.
        db.rollback()
        _fail_operation(task_id, exc)
    finally:
        db.close()


def _run_add_product_operation(
    *,
    task_id: str,
    dataset_id: int,
    payload: DatasetProductCommitRequest,
    user_id: int,
    bind=None,
) -> None:
    db = SessionLocal() if bind is None else Session(bind=bind)
    try:
        dataset_operation_store.update(
            task_id,
            status="running",
            progress=1,
            message="正在读取已审核的图片与检测框",
        )
        reviewed_files = dataset_annotation_service.reviewed_files(
            token=payload.staging_token,
            dataset_id=dataset_id,
            user_id=user_id,
            mode=payload.mode,
            images=payload.images,
        )
        dataset, product, added = dataset_workspace_service.add_samples(
            db,
            dataset_id=dataset_id,
            mode=payload.mode,
            files=[item[:3] for item in reviewed_files],
            annotations=[item[3] for item in reviewed_files],
            existing_product_id=payload.existing_product_id,
            name=payload.name,
            unit_price=payload.unit_price,
            class_name=payload.class_name,
            barcode=payload.barcode,
            product_key=payload.product_key,
            progress_callback=_operation_progress(task_id),
        )
        try:
            dataset_annotation_service.discard(
                token=payload.staging_token,
                dataset_id=dataset_id,
                user_id=user_id,
            )
        except DatasetLifecycleError:
            pass
        dataset_operation_store.update(
            task_id,
            status="completed",
            progress=100,
            message="人工样本、标注与索引已更新",
            result={
                "dataset": jsonable_encoder(dataset_service.serialize(dataset)),
                "product_id": product.id if product else None,
                "product_key": product.product_key if product else None,
                "images_added": added,
            },
        )
    except Exception as exc:  # noqa: BLE001 - surfaced through the task status endpoint.
        db.rollback()
        _fail_operation(task_id, exc)
    finally:
        db.close()


def _run_delete_product_operation(
    *,
    task_id: str,
    dataset_id: int,
    product_id: int,
    deactivate_product: bool,
    bind=None,
) -> None:
    db = SessionLocal() if bind is None else Session(bind=bind)
    try:
        dataset, images_deleted, annotations_deleted, classes_reindexed = (
            dataset_workspace_service.delete_product(
                db,
                dataset_id=dataset_id,
                product_id=product_id,
                deactivate_product=deactivate_product,
                progress_callback=_operation_progress(task_id),
            )
        )
        dataset_operation_store.update(
            task_id,
            status="completed",
            progress=100,
            message="商品样本已删除，类别与数据集索引已重建",
            result={
                "dataset": jsonable_encoder(dataset_service.serialize(dataset)),
                "product_id": product_id,
                "images_deleted": images_deleted,
                "annotations_deleted": annotations_deleted,
                "classes_reindexed": classes_reindexed,
            },
        )
    except Exception as exc:  # noqa: BLE001 - surfaced through the task status endpoint.
        db.rollback()
        _fail_operation(task_id, exc)
    finally:
        db.close()


def _run_delete_draft_operation(*, task_id: str, dataset_id: int, bind=None) -> None:
    db = SessionLocal() if bind is None else Session(bind=bind)
    try:
        dataset_service.delete_draft(
            db,
            dataset_id=dataset_id,
            progress_callback=_operation_progress(task_id),
        )
        dataset_operation_store.update(
            task_id,
            status="completed",
            progress=100,
            message="草稿已删除",
            result={"dataset_id": dataset_id},
        )
    except Exception as exc:  # noqa: BLE001 - surfaced through the task status endpoint.
        db.rollback()
        _fail_operation(task_id, exc)
    finally:
        db.close()


@router.get("/operations/{task_id}", summary="查询数据集操作进度")
def get_dataset_operation_status(
    task_id: str,
    current_user=Depends(get_current_user),
):
    operation = dataset_operation_store.get(task_id)
    if operation is None or int(operation.get("user_id", 0)) != current_user.id:
        raise HTTPException(status_code=404, detail="数据集操作任务不存在或已过期")
    return {key: value for key, value in operation.items() if key != "user_id"}


@router.get("", response_model=DatasetVersionListResponse, summary="数据集版本列表")
def list_dataset_versions(
    scene_id: int | None = Query(None, ge=1),
    dataset_status: Literal["draft", "ready", "archived"] | None = Query(
        None,
        alias="status",
    ),
    current_only: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return dataset_service.list(
        db,
        scene_id=scene_id,
        status=dataset_status,
        current_only=current_only,
        offset=offset,
        limit=limit,
    )


@router.get("/current", response_model=DatasetVersionResponse, summary="获取当前数据集版本")
def get_current_dataset_version(
    scene_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dataset = (
        db.query(DatasetVersion)
        .filter(
            DatasetVersion.scene_id == scene_id,
            DatasetVersion.is_current.is_(True),
        )
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="该场景尚未设置当前数据集")
    return dataset_service.serialize(dataset)


@router.post(
    "",
    response_model=DatasetVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建数据集草稿",
)
def create_dataset_version(
    payload: DatasetVersionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        dataset = dataset_service.create(
            db,
            payload=payload,
            user_id=current_user.id,
        )
        return dataset_service.serialize(dataset)
    except (DatasetNotFoundError, DatasetConflictError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/import-baseline",
    response_model=DatasetVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="导入 YOLO 基线数据集并建立稳定商品索引",
)
def import_baseline_dataset(
    payload: DatasetBaselineImportRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        dataset = dataset_workspace_service.import_baseline(
            db,
            **payload.model_dump(),
            user_id=current_user.id,
        )
        return dataset_service.serialize(dataset)
    except (DatasetNotFoundError, DatasetConflictError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/import-available-model",
    status_code=status.HTTP_201_CREATED,
    summary="导入可直接用于检测的 YOLO 模型及类别目录",
)
async def import_available_model(
    scene_id: int = Form(..., ge=1),
    version: str = Form(..., min_length=1, max_length=50),
    name: str = Form(..., min_length=1, max_length=150),
    description: str | None = Form(None),
    source_path: str | None = Form(None),
    set_current: bool = Form(True),
    set_default: bool = Form(True),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Accept one best.pt upload or a path visible to the backend host."""
    uploaded = file is not None and bool(file.filename)
    path_value = (source_path or "").strip()
    if uploaded == bool(path_value):
        raise HTTPException(status_code=422, detail="请上传 best.pt 或填写服务器文件路径，且只能选择一种方式")

    staged_path: Path | None = None
    source_name = Path(file.filename or "best.pt").name if uploaded else Path(path_value).name
    try:
        if uploaded:
            if Path(source_name).suffix.lower() != ".pt":
                raise HTTPException(status_code=422, detail="模型文件必须是 .pt 格式")
            staging_root = Path(settings.DATASET_STAGING_ROOT).expanduser()
            if not staging_root.is_absolute():
                staging_root = (BACKEND_ROOT / staging_root).resolve()
            staging_root = staging_root / "model-imports"
            staging_root.mkdir(parents=True, exist_ok=True)
            staged_path = staging_root / f"{uuid.uuid4().hex}.pt"
            max_bytes = settings.MODEL_IMPORT_MAX_FILE_MB * 1024 * 1024
            size = 0
            with staged_path.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"模型文件超过 {settings.MODEL_IMPORT_MAX_FILE_MB} MB 限制",
                        )
                    output.write(chunk)
            import_source = staged_path
        else:
            candidate = Path(path_value).expanduser()
            import_source = candidate if candidate.is_absolute() else (BACKEND_ROOT / candidate).resolve()

        dataset, model_version = model_import_service.import_available_model(
            db,
            scene_id=scene_id,
            source_path=import_source,
            source_name=source_name,
            version=version,
            name=name,
            description=description,
            set_current=set_current,
            set_default=set_default,
            user_id=current_user.id,
        )
        return {
            "dataset": dataset_service.serialize(dataset),
            "model_version": model_version_service.serialize(db, model_version),
        }
    except (DatasetNotFoundError, DatasetConflictError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)
    finally:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
        if file is not None:
            await file.close()


@router.get("/{dataset_id}", response_model=DatasetVersionResponse, summary="数据集版本详情")
def get_dataset_version(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return dataset_service.serialize(dataset_service.get(db, dataset_id))
    except DatasetNotFoundError as exc:
        _raise_service_error(exc)


@router.put("/{dataset_id}", response_model=DatasetVersionResponse, summary="修改数据集草稿")
def update_dataset_version(
    dataset_id: int,
    payload: DatasetVersionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        dataset = dataset_service.update(db, dataset_id=dataset_id, payload=payload)
        return dataset_service.serialize(dataset)
    except (DatasetNotFoundError, DatasetConflictError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/{dataset_id}/derive",
    response_model=DatasetVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="从冻结版本创建可编辑派生版本",
)
def derive_dataset_version(
    dataset_id: int,
    payload: DatasetDeriveRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        dataset = dataset_workspace_service.derive(
            db,
            parent_id=dataset_id,
            **payload.model_dump(),
            user_id=current_user.id,
        )
        return dataset_service.serialize(dataset)
    except (DatasetNotFoundError, DatasetConflictError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/{dataset_id}/derive-task",
    status_code=status.HTTP_202_ACCEPTED,
    summary="后台创建派生版本并返回实时进度任务",
)
def create_derive_dataset_task(
    dataset_id: int,
    payload: DatasetDeriveRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    operation = dataset_operation_store.create(
        operation="derive",
        user_id=current_user.id,
        message="派生版本已创建，等待处理",
    )
    background_tasks.add_task(
        _run_derive_operation,
        task_id=operation["task_id"],
        parent_id=dataset_id,
        payload=payload.model_dump(),
        user_id=current_user.id,
        bind=db.get_bind(),
    )
    return {key: value for key, value in operation.items() if key != "user_id"}


@router.post(
    "/{dataset_id}/products/stage",
    response_model=DatasetProductStagingResponse,
    summary="暂存待人工矩形框标注的训练或场景图片",
)
async def stage_dataset_product_images(
    dataset_id: int,
    mode: Literal["train_new", "train_existing", "scene"] = Form(...),
    train_files: list[UploadFile] = File(default=[]),
    val_files: list[UploadFile] = File(default=[]),
    test_files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    uploads: list[tuple[str, str, bytes]] = []
    max_upload_bytes = int(settings.DATASET_MAX_UPLOAD_MB) * 1024 * 1024
    if len(train_files) + len(val_files) + len(test_files) > int(settings.DATASET_MAX_BATCH_SIZE):
        raise HTTPException(
            status_code=400,
            detail=f"单次最多上传 {settings.DATASET_MAX_BATCH_SIZE} 张图片",
        )
    for split, items in (
        ("train", train_files),
        ("val", val_files),
        ("test", test_files),
    ):
        for item in items:
            uploads.append(
                (
                    split,
                    item.filename or "image.jpg",
                    await item.read(max_upload_bytes + 1),
                )
            )
    try:
        return dataset_annotation_service.stage(
            db,
            dataset_id=dataset_id,
            user_id=current_user.id,
            mode=mode,
            files=uploads,
        )
    except (DatasetNotFoundError, DatasetConflictError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/{dataset_id}/products/commit",
    response_model=DatasetMutationResponse,
    summary="确认人工检测框并写入训练或 val/test 场景样本",
)
def commit_dataset_product_images(
    dataset_id: int,
    payload: DatasetProductCommitRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        reviewed_files = dataset_annotation_service.reviewed_files(
            token=payload.staging_token,
            dataset_id=dataset_id,
            user_id=current_user.id,
            mode=payload.mode,
            images=payload.images,
        )
        dataset, product, added = dataset_workspace_service.add_samples(
            db,
            dataset_id=dataset_id,
            mode=payload.mode,
            files=[item[:3] for item in reviewed_files],
            annotations=[item[3] for item in reviewed_files],
            existing_product_id=payload.existing_product_id,
            name=payload.name,
            unit_price=payload.unit_price,
            class_name=payload.class_name,
            barcode=payload.barcode,
            product_key=payload.product_key,
        )
        try:
            dataset_annotation_service.discard(
                token=payload.staging_token,
                dataset_id=dataset_id,
                user_id=current_user.id,
            )
        except DatasetLifecycleError:
            pass
        return {
            "dataset": dataset_service.serialize(dataset),
            "product_id": product.id if product else None,
            "product_key": product.product_key if product else None,
            "images_added": added,
        }
    except (DatasetNotFoundError, DatasetConflictError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/{dataset_id}/products/commit-task",
    status_code=status.HTTP_202_ACCEPTED,
    summary="后台写入人工样本与标注并返回实时进度任务",
)
def create_commit_dataset_product_task(
    dataset_id: int,
    payload: DatasetProductCommitRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    operation = dataset_operation_store.create(
        operation="add_samples",
        user_id=current_user.id,
        message="添加样本任务已创建，等待处理",
    )
    background_tasks.add_task(
        _run_add_product_operation,
        task_id=operation["task_id"],
        dataset_id=dataset_id,
        payload=payload,
        user_id=current_user.id,
        bind=db.get_bind(),
    )
    return {key: value for key, value in operation.items() if key != "user_id"}


@router.delete(
    "/{dataset_id}/products/stage/{staging_token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="放弃尚未写入数据集的商品图片暂存批次",
)
def discard_dataset_product_stage(
    dataset_id: int,
    staging_token: str,
    current_user=Depends(get_current_user),
):
    try:
        dataset_annotation_service.discard(
            token=staging_token,
            dataset_id=dataset_id,
            user_id=current_user.id,
        )
        return None
    except DatasetLifecycleError as exc:
        _raise_service_error(exc)


@router.post(
    "/{dataset_id}/products",
    response_model=DatasetMutationResponse,
    summary="已停用：旧版全图自动标注入口",
)
async def add_dataset_product(
    dataset_id: int,
    name: str = Form(...),
    unit_price: float = Form(..., ge=0),
    class_name: str | None = Form(None),
    barcode: str | None = Form(None),
    product_key: str | None = Form(None),
    train_files: list[UploadFile] = File(default=[]),
    val_files: list[UploadFile] = File(default=[]),
    test_files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    del dataset_id, name, unit_price, class_name, barcode, product_key
    del train_files, val_files, test_files, db, current_user
    raise HTTPException(
        status_code=410,
        detail="全图自动标注接口已停用，请使用图片暂存、人工矩形框标注和提交接口",
    )


@router.delete(
    "/{dataset_id}/products/{product_id}",
    response_model=DatasetMutationResponse,
    summary="从派生草稿删除商品及相关样本并重排类别",
)
def delete_dataset_product(
    dataset_id: int,
    product_id: int,
    payload: DatasetProductDeleteRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    del current_user
    try:
        request = payload or DatasetProductDeleteRequest()
        dataset, images_deleted, annotations_deleted, classes_reindexed = (
            dataset_workspace_service.delete_product(
                db,
                dataset_id=dataset_id,
                product_id=product_id,
                deactivate_product=request.deactivate_product,
            )
        )
        return {
            "dataset": dataset_service.serialize(dataset),
            "product_id": product_id,
            "images_deleted": images_deleted,
            "annotations_deleted": annotations_deleted,
            "classes_reindexed": classes_reindexed,
        }
    except (DatasetNotFoundError, DatasetConflictError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/{dataset_id}/products/{product_id}/delete-task",
    status_code=status.HTTP_202_ACCEPTED,
    summary="后台删除商品样本并返回实时进度任务",
)
def create_delete_dataset_product_task(
    dataset_id: int,
    product_id: int,
    background_tasks: BackgroundTasks,
    payload: DatasetProductDeleteRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    request = payload or DatasetProductDeleteRequest()
    operation = dataset_operation_store.create(
        operation="delete_product",
        user_id=current_user.id,
        message="删除商品任务已创建，等待处理",
    )
    background_tasks.add_task(
        _run_delete_product_operation,
        task_id=operation["task_id"],
        dataset_id=dataset_id,
        product_id=product_id,
        deactivate_product=request.deactivate_product,
        bind=db.get_bind(),
    )
    return {key: value for key, value in operation.items() if key != "user_id"}


@router.post(
    "/{dataset_id}/validate",
    response_model=DatasetValidationResponse,
    summary="校验数据集定义",
)
def validate_dataset_version(
    dataset_id: int,
    payload: DatasetValidationRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        request = payload or DatasetValidationRequest()
        return dataset_service.validate(
            db,
            dataset_id=dataset_id,
            check_filesystem=request.check_filesystem,
        )
    except DatasetNotFoundError as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/{dataset_id}/freeze",
    response_model=DatasetVersionResponse,
    summary="冻结数据集版本",
)
def freeze_dataset_version(
    dataset_id: int,
    payload: DatasetValidationRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        request = payload or DatasetValidationRequest()
        dataset = dataset_service.freeze(
            db,
            dataset_id=dataset_id,
            check_filesystem=request.check_filesystem,
        )
        return dataset_service.serialize(dataset)
    except (DatasetNotFoundError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/{dataset_id}/set-current",
    response_model=DatasetVersionResponse,
    summary="设为当前数据集版本",
)
def set_current_dataset_version(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return dataset_service.serialize(dataset_service.set_current(db, dataset_id=dataset_id))
    except (DatasetNotFoundError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/{dataset_id}/archive",
    response_model=DatasetVersionResponse,
    summary="归档数据集版本",
)
def archive_dataset_version(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return dataset_service.serialize(dataset_service.archive(db, dataset_id=dataset_id))
    except (DatasetNotFoundError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.delete(
    "/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除数据集草稿",
)
def delete_dataset_version(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        dataset_service.delete_draft(db, dataset_id=dataset_id)
        return None
    except (DatasetNotFoundError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/{dataset_id}/delete-task",
    status_code=status.HTTP_202_ACCEPTED,
    summary="后台删除数据集草稿并返回实时进度任务",
)
def create_delete_dataset_task(
    dataset_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    operation = dataset_operation_store.create(
        operation="delete_draft",
        user_id=current_user.id,
        message="删除草稿任务已创建，等待处理",
    )
    background_tasks.add_task(
        _run_delete_draft_operation,
        task_id=operation["task_id"],
        dataset_id=dataset_id,
        bind=db.get_bind(),
    )
    return {key: value for key, value in operation.items() if key != "user_id"}
