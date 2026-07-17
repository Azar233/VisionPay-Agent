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
from app.storage.dataset_operation_store import dataset_operation_store

router = APIRouter(prefix="/api/agent/operations", tags=["Agent 操作确认"])
PROGRESS_ACTIONS = {"dataset.derive", "dataset.delete_draft", "dataset.delete_product"}


def _progress_task_id(operation_uuid: str) -> str:
    return f"agent-{operation_uuid}"


def _serialize_operation(operation, *, confirmation_token: str | None = None, replayed: bool = False):
    result = agent_confirmation_service.serialize(
        operation,
        confirmation_token=confirmation_token,
        replayed=replayed,
    )
    progress = dataset_operation_store.get(_progress_task_id(operation.operation_uuid))
    if progress is not None and int(progress.get("user_id", 0)) == int(operation.user_id):
        result["task_progress"] = {
            key: value for key, value in progress.items() if key not in {"user_id", "result"}
        }
    return result


def _operation_progress(operation_uuid: str):
    task_id = _progress_task_id(operation_uuid)

    def update(progress: int, message: str) -> None:
        normalized = max(0, min(99, int(progress)))
        current = dataset_operation_store.get(task_id) or {}
        history = list(current.get("history") or [])
        last_recorded = int(history[-1]["progress"]) if history else -1
        if normalized > last_recorded and (not history or normalized - last_recorded >= 4):
            history.append({"progress": normalized, "message": message})
            history = history[-16:]
        dataset_operation_store.update(
            task_id,
            status="running",
            progress=normalized,
            message=message,
            history=history,
        )

    return update


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
        return _serialize_operation(operation)
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
    progress_enabled = False
    progress_task_id = _progress_task_id(operation_uuid)
    try:
        operation = agent_confirmation_service.get(
            db,
            operation_uuid=operation_uuid,
            user_id=int(current_user.id),
        )
        if operation.status == "expired":
            raise AgentConfirmationError("确认令牌已过期", code="expired_token")
        progress_enabled = operation.action in PROGRESS_ACTIONS
        if progress_enabled:
            dataset_operation_store.set(
                progress_task_id,
                {
                    "task_id": progress_task_id,
                    "operation": operation.action,
                    "user_id": int(current_user.id),
                    "status": "pending",
                    "progress": 0,
                    "message": "已确认操作，正在准备执行",
                    "history": [{"progress": 0, "message": "已确认操作，正在准备执行"}],
                    "result": None,
                },
            )
        result = agent_confirmation_service.confirm(
            db,
            operation_uuid=operation_uuid,
            user_id=int(current_user.id),
            username=current_user.username,
            confirmation_token=request.confirmation_token,
            idempotency_key=request.idempotency_key,
            progress_callback=_operation_progress(operation_uuid) if progress_enabled else None,
        )
        if progress_enabled:
            current = dataset_operation_store.get(progress_task_id) or {}
            history = list(current.get("history") or [])
            history.append({"progress": 100, "message": "数据集操作已完成"})
            dataset_operation_store.update(
                progress_task_id,
                status="completed",
                progress=100,
                message="数据集操作已完成",
                history=history[-16:],
            )
            operation = agent_confirmation_service.get(
                db,
                operation_uuid=operation_uuid,
                user_id=int(current_user.id),
            )
            result = _serialize_operation(operation, replayed=bool(result.get("replayed")))
        return result
    except AgentConfirmationError as exc:
        db.rollback()
        if progress_enabled:
            current = dataset_operation_store.get(progress_task_id) or {}
            dataset_operation_store.update(
                progress_task_id,
                status="failed",
                progress=min(99, int(current.get("progress", 0))),
                message=str(exc),
            )
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
