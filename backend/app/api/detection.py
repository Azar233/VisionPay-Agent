"""Direct detection APIs used by the low-latency workbench controls."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.auth import get_current_user
from app.config.settings import settings
from app.services.detection_service import DetectionServiceError, detection_service

router = APIRouter(prefix="/api/detection", tags=["商品检测"])


def _upload_root() -> Path:
    root = Path(settings.DETECTION_UPLOAD_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(filename: str | None) -> str:
    original = Path(filename or "upload").name
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", original)
    return f"{uuid4().hex}_{clean}"


async def save_upload(file: UploadFile, *, allow_zip: bool = False) -> Path:
    suffix = Path(file.filename or "").suffix.lower()
    allowed = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if allow_zip:
        allowed.add(".zip")
    if suffix not in allowed:
        raise HTTPException(status_code=415, detail="仅支持常见图片格式或 ZIP 文件")

    limit = settings.DETECTION_MAX_FILE_MB * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"单个文件不能超过 {settings.DETECTION_MAX_FILE_MB} MB",
        )
    path = _upload_root() / _safe_name(file.filename)
    path.write_bytes(content)
    return path


def _detection_kwargs(user_id: int, scene_id: int | None, conf: float, iou: float):
    return {"user_id": user_id, "scene_id": scene_id, "conf": conf, "iou": iou}


@router.post("/single", summary="单张商品图片检测")
async def detect_single(
    file: UploadFile = File(...),
    scene_id: int | None = Form(None),
    conf: float = Form(0.25, ge=0.05, le=0.95),
    iou: float = Form(0.45, ge=0.05, le=0.95),
    current_user=Depends(get_current_user),
):
    path = await save_upload(file)
    try:
        return await run_in_threadpool(
            detection_service.detect_single,
            path,
            **_detection_kwargs(current_user.id, scene_id, conf, iou),
        )
    except DetectionServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/batch", summary="批量商品图片检测")
async def detect_batch(
    files: list[UploadFile] = File(...),
    scene_id: int | None = Form(None),
    conf: float = Form(0.25, ge=0.05, le=0.95),
    iou: float = Form(0.45, ge=0.05, le=0.95),
    current_user=Depends(get_current_user),
):
    if len(files) > settings.DETECTION_MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"单次最多上传 {settings.DETECTION_MAX_BATCH_SIZE} 张图片",
        )
    paths = [await save_upload(file) for file in files]
    try:
        return await run_in_threadpool(
            detection_service.detect_batch,
            paths,
            **_detection_kwargs(current_user.id, scene_id, conf, iou),
        )
    except DetectionServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/zip", summary="ZIP 商品图片批量检测")
async def detect_zip(
    file: UploadFile = File(...),
    scene_id: int | None = Form(None),
    conf: float = Form(0.25, ge=0.05, le=0.95),
    iou: float = Form(0.45, ge=0.05, le=0.95),
    current_user=Depends(get_current_user),
):
    path = await save_upload(file, allow_zip=True)
    if path.suffix.lower() != ".zip":
        raise HTTPException(status_code=415, detail="该接口只接受 ZIP 文件")
    try:
        return await run_in_threadpool(
            detection_service.detect_zip,
            path,
            **_detection_kwargs(current_user.id, scene_id, conf, iou),
        )
    except DetectionServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
