"""Authenticated dashboard aggregate endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.database.session import get_db
from app.services.dashboard_service import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["数据看板"])


@router.get("/statistics", summary="检测业务汇总")
def get_statistics(
    days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dashboard_service.get_statistics(db, current_user.id, days)


@router.get("/trend", summary="每日识别趋势")
def get_trend(
    days: int = Query(30, ge=1, le=365),
    hours: int | None = Query(None, ge=1, le=168),
    bucket_hours: int = Query(1, ge=1, le=24),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dashboard_service.get_trend(db, current_user.id, days, hours, bucket_hours)


@router.get("/class-dist", summary="商品类别分布")
def get_class_distribution(
    days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dashboard_service.get_class_distribution(db, current_user.id, days)


@router.get("/scene-dist", summary="业务场景分布")
def get_scene_distribution(
    days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dashboard_service.get_scene_distribution(db, current_user.id, days)


@router.get("/type-dist", summary="识别方式分布")
def get_type_distribution(
    days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dashboard_service.get_type_distribution(db, current_user.id, days)


@router.get("/model-usage", summary="大模型与 Agent 调用概览")
def get_model_usage(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(8, ge=1, le=50),
    hours: int | None = Query(None, ge=1, le=168),
    bucket_hours: int = Query(1, ge=1, le=24),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dashboard_service.get_model_usage(
        db, current_user.id, days, limit, hours, bucket_hours
    )
