"""Dataset version management API.

Training and model deployment are intentionally out of scope for this router.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config.settings import settings
from app.database.session import get_db
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
from app.services.dataset_service import (
    DatasetConflictError,
    DatasetLifecycleError,
    DatasetNotFoundError,
    dataset_service,
)

router = APIRouter(prefix="/api/datasets", tags=["数据集版本"])


def _raise_service_error(exc: ValueError) -> None:
    if isinstance(exc, DatasetNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, DatasetConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    "/{dataset_id}/products/stage",
    response_model=DatasetProductStagingResponse,
    summary="暂存商品图片并自动生成候选检测框",
)
async def stage_dataset_product_images(
    dataset_id: int,
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
            files=uploads,
        )
    except (DatasetNotFoundError, DatasetConflictError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/{dataset_id}/products/commit",
    response_model=DatasetMutationResponse,
    summary="确认审核后的检测框并写入商品图片与 YOLO 标注",
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
            images=payload.images,
        )
        dataset, product, added = dataset_workspace_service.add_product(
            db,
            dataset_id=dataset_id,
            name=payload.name,
            unit_price=payload.unit_price,
            files=[item[:3] for item in reviewed_files],
            annotations=[item[3] for item in reviewed_files],
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
            "product_id": product.id,
            "product_key": product.product_key,
            "images_added": added,
        }
    except (DatasetNotFoundError, DatasetConflictError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


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
    summary="向派生草稿添加商品图片并生成全图 YOLO 标注",
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
    del current_user
    uploads: list[tuple[str, str, bytes]] = []
    for split, items in (
        ("train", train_files),
        ("val", val_files),
        ("test", test_files),
    ):
        for item in items:
            uploads.append((split, item.filename or "image.jpg", await item.read()))
    try:
        dataset, product, added = dataset_workspace_service.add_product(
            db,
            dataset_id=dataset_id,
            name=name,
            unit_price=unit_price,
            files=uploads,
            class_name=class_name,
            barcode=barcode,
            product_key=product_key,
        )
        return {
            "dataset": dataset_service.serialize(dataset),
            "product_id": product.id,
            "product_key": product.product_key,
            "images_added": added,
        }
    except (DatasetNotFoundError, DatasetConflictError, DatasetLifecycleError) as exc:
        db.rollback()
        _raise_service_error(exc)


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
