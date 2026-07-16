"""Authenticated confirmation API for Agent-initiated business writes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.database.session import get_db
from app.services.agent_confirmation_service import (
    AgentConfirmationError,
    agent_confirmation_service,
)

router = APIRouter(prefix="/api/agent/operations", tags=["Agent 操作确认"])


class PreviewRequest(BaseModel):
    session_uuid: str = Field(..., min_length=1, max_length=100)
    action: str = Field(..., min_length=1, max_length=100)
    parameters: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(None, min_length=1, max_length=100)


class ConfirmRequest(BaseModel):
    confirmation_token: str = Field(..., min_length=20, max_length=200)
    idempotency_key: str = Field(..., min_length=1, max_length=100)


def _raise(exc: AgentConfirmationError):
    status = {
        "not_found": 404,
        "conflict": 409,
        "idempotency_conflict": 409,
        "invalid_token": 403,
        "expired_token": 410,
        "execution_failed": 422,
    }.get(exc.code, 400)
    raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/preview", summary="生成影响范围和待确认操作")
def create_preview(
    request: PreviewRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return agent_confirmation_service.create_preview(
            db,
            user_id=int(current_user.id),
            username=current_user.username,
            session_uuid=request.session_uuid,
            action=request.action,
            parameters=request.parameters,
            idempotency_key=request.idempotency_key,
        )
    except AgentConfirmationError as exc:
        db.rollback()
        _raise(exc)


@router.get("", summary="查询当前用户的待确认与历史操作")
def list_operations(
    session_uuid: str | None = Query(None, max_length=100),
    status: str | None = Query(None, max_length=30),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "items": agent_confirmation_service.list(
            db,
            user_id=int(current_user.id),
            session_uuid=session_uuid,
            status=status,
        )
    }


@router.get("/{operation_uuid}", summary="查询待确认操作详情")
def get_operation(
    operation_uuid: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        operation = agent_confirmation_service.get(
            db, operation_uuid=operation_uuid, user_id=int(current_user.id)
        )
        return agent_confirmation_service.serialize(operation)
    except AgentConfirmationError as exc:
        _raise(exc)


@router.post("/{operation_uuid}/token", summary="为未完成操作换发一次性确认令牌")
def rotate_token(
    operation_uuid: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return agent_confirmation_service.rotate_token(
            db,
            operation_uuid=operation_uuid,
            user_id=int(current_user.id),
            username=current_user.username,
        )
    except AgentConfirmationError as exc:
        db.rollback()
        _raise(exc)


@router.post("/{operation_uuid}/confirm", summary="使用一次性令牌确认并执行")
def confirm_operation(
    operation_uuid: str,
    request: ConfirmRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return agent_confirmation_service.confirm(
            db,
            operation_uuid=operation_uuid,
            user_id=int(current_user.id),
            username=current_user.username,
            confirmation_token=request.confirmation_token,
            idempotency_key=request.idempotency_key,
        )
    except AgentConfirmationError as exc:
        db.rollback()
        _raise(exc)


@router.post("/{operation_uuid}/cancel", summary="取消待确认操作")
def cancel_operation(
    operation_uuid: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return agent_confirmation_service.cancel(
            db,
            operation_uuid=operation_uuid,
            user_id=int(current_user.id),
            username=current_user.username,
        )
    except AgentConfirmationError as exc:
        db.rollback()
        _raise(exc)
