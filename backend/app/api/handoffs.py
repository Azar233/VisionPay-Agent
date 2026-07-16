"""Authenticated APIs for Agent-to-page human handoffs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.database.session import get_db
from app.entity.schemas import (
    AgentHandoffResponse,
    AgentHandoffUpdate,
    DatasetAddSamplesHandoffCreate,
)
from app.services.agent_handoff_service import AgentHandoffError, agent_handoff_service
from app.services.dataset_service import DatasetLifecycleError, DatasetNotFoundError

router = APIRouter(prefix="/api/agent/handoffs", tags=["Agent 页面交接"])


def _handoff_error(exc: ValueError) -> None:
    status_code = 404 if isinstance(exc, DatasetNotFoundError) else 400
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post(
    "/dataset/add-samples",
    response_model=AgentHandoffResponse,
    summary="创建 Dataset Agent 人工添加样品交接",
)
def create_dataset_add_samples_handoff(
    payload: DatasetAddSamplesHandoffCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        handoff = agent_handoff_service.create_dataset_add_samples(
            db,
            user_id=current_user.id,
            **payload.model_dump(),
        )
        return agent_handoff_service.serialize(handoff)
    except (AgentHandoffError, DatasetLifecycleError, DatasetNotFoundError) as exc:
        db.rollback()
        _handoff_error(exc)


@router.get(
    "/{handoff_uuid}",
    response_model=AgentHandoffResponse,
    summary="读取当前用户的页面交接",
)
def get_handoff(
    handoff_uuid: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        handoff = agent_handoff_service.get(
            db, handoff_uuid=handoff_uuid, user_id=current_user.id
        )
        return agent_handoff_service.serialize(handoff)
    except AgentHandoffError as exc:
        _handoff_error(exc)


@router.patch(
    "/{handoff_uuid}",
    response_model=AgentHandoffResponse,
    summary="更新人工页面交接状态",
)
def update_handoff(
    handoff_uuid: str,
    payload: AgentHandoffUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        handoff = agent_handoff_service.update(
            db,
            handoff_uuid=handoff_uuid,
            user_id=current_user.id,
            **payload.model_dump(),
        )
        return agent_handoff_service.serialize(handoff)
    except AgentHandoffError as exc:
        db.rollback()
        _handoff_error(exc)
