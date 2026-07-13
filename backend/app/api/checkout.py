"""Checkout APIs for product recognition and authoritative price calculation."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.auth import get_current_user
from app.api.detection import save_upload
from app.database.session import get_db
from app.entity.schemas import CheckoutCalculateRequest
from app.services.detection_service import DetectionServiceError, detection_service

router = APIRouter(prefix="/api/checkout", tags=["商品结算"])


@router.post("/detect", summary="识别结算图片并计算初始总价")
async def detect_checkout(
    file: UploadFile = File(...),
    scene_id: int | None = Form(None),
    conf: float = Form(0.25, ge=0.05, le=0.95),
    iou: float = Form(0.45, ge=0.05, le=0.95),
    current_user=Depends(get_current_user),
):
    """Run single-image detection and return the detected cart with prices."""
    path = await save_upload(file)
    try:
        return await run_in_threadpool(
            detection_service.detect_single,
            path,
            user_id=current_user.id,
            scene_id=scene_id,
            conf=conf,
            iou=iou,
        )
    except DetectionServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/calculate", summary="按确认后的商品数量重新计算总价")
def calculate_checkout(
    payload: CheckoutCalculateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Recalculate using database prices; the client never supplies unit prices."""
    del current_user  # Authentication is required even though prices are shared.
    counts: Counter[int] = Counter()
    for item in payload.items:
        next_count = counts[item.class_id] + item.quantity
        if next_count > 99:
            raise HTTPException(status_code=422, detail="单个商品数量不能超过 99")
        counts[item.class_id] = next_count
    return detection_service.calculate_price(db, dict(counts))
