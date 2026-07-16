"""Persistent human-in-the-loop handoffs for management workflows."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.entity.db_models import AgentHandoff, ChatSession, DatasetClassMapping
from app.services.dataset_service import DatasetLifecycleError, dataset_service

HANDOFF_TRANSITIONS = {
    "ready_for_handoff": {"selecting_files", "cancelled"},
    "selecting_files": {"annotating", "cancelled", "failed"},
    "annotating": {"submitting", "cancelled", "failed"},
    "submitting": {"completed", "failed"},
    "failed": {"selecting_files", "cancelled"},
    "completed": set(),
    "cancelled": set(),
    "expired": set(),
}


class AgentHandoffError(ValueError):
    pass


class AgentHandoffService:
    @staticmethod
    def serialize(handoff: AgentHandoff) -> dict:
        return {
            "handoff_uuid": handoff.handoff_uuid,
            "user_id": handoff.user_id,
            "session_uuid": handoff.session_uuid,
            "domain": handoff.domain,
            "action": handoff.action,
            "status": handoff.status,
            "context": handoff.context or {},
            "result": handoff.result,
            "error_message": handoff.error_message,
            "page_url": f"/datasets?handoff_id={handoff.handoff_uuid}",
            "expires_at": handoff.expires_at,
            "created_at": handoff.created_at,
            "updated_at": handoff.updated_at,
        }

    @staticmethod
    def _expire_if_needed(db: Session, handoff: AgentHandoff) -> AgentHandoff:
        if handoff.status not in {"completed", "cancelled", "expired"} and handoff.expires_at <= datetime.now():
            handoff.status = "expired"
            db.commit()
            db.refresh(handoff)
        return handoff

    @classmethod
    def get(cls, db: Session, *, handoff_uuid: str, user_id: int) -> AgentHandoff:
        handoff = db.query(AgentHandoff).filter(
            AgentHandoff.handoff_uuid == handoff_uuid,
            AgentHandoff.user_id == user_id,
        ).first()
        if handoff is None:
            raise AgentHandoffError("页面交接不存在或无权访问")
        return cls._expire_if_needed(db, handoff)

    @classmethod
    def create_dataset_add_samples(
        cls,
        db: Session,
        *,
        user_id: int,
        session_uuid: str,
        dataset_id: int,
        mode: str,
        existing_product_id: int | None = None,
        name: str | None = None,
        class_name: str | None = None,
        unit_price: float | None = None,
        barcode: str | None = None,
    ) -> AgentHandoff:
        session = db.query(ChatSession).filter(
            ChatSession.session_uuid == session_uuid,
            ChatSession.user_id == user_id,
            ChatSession.status == "active",
        ).first()
        if session is None:
            raise AgentHandoffError("对话不存在或已失效")
        dataset = dataset_service.get(db, dataset_id)
        if dataset.status != "draft":
            raise DatasetLifecycleError("添加样品只能针对可编辑草稿数据集")
        if mode not in {"train_new", "train_existing", "scene"}:
            raise AgentHandoffError("不支持的样品模式")
        if mode == "train_new" and not all(
            [str(name or "").strip(), str(class_name or "").strip(), unit_price is not None]
        ):
            raise AgentHandoffError("新建商品训练图必须明确商品名称、类别英文名和价格")
        if mode == "train_existing":
            mapping = db.query(DatasetClassMapping).filter(
                DatasetClassMapping.dataset_version_id == dataset_id,
                DatasetClassMapping.product_id == existing_product_id,
            ).first()
            if mapping is None:
                raise AgentHandoffError("所选已有商品不属于目标数据集版本")

        handoff = AgentHandoff(
            handoff_uuid=uuid4().hex,
            user_id=user_id,
            session_uuid=session_uuid,
            domain="dataset",
            action="add_samples",
            status="ready_for_handoff",
            context={
                "dataset_id": dataset.id,
                "dataset_version": dataset.version,
                "mode": mode,
                "existing_product_id": existing_product_id,
                "name": (name or "").strip() or None,
                "class_name": (class_name or "").strip() or None,
                "unit_price": unit_price,
                "barcode": (barcode or "").strip() or None,
            },
            expires_at=datetime.now() + timedelta(seconds=settings.AGENT_HANDOFF_TTL_SECONDS),
        )
        db.add(handoff)
        db.commit()
        db.refresh(handoff)
        return handoff

    @classmethod
    def update(
        cls,
        db: Session,
        *,
        handoff_uuid: str,
        user_id: int,
        status: str,
        context_updates: dict | None = None,
        result: dict | None = None,
        error_message: str | None = None,
    ) -> AgentHandoff:
        handoff = cls.get(db, handoff_uuid=handoff_uuid, user_id=user_id)
        allowed = HANDOFF_TRANSITIONS.get(handoff.status, set())
        if status != handoff.status and status not in allowed:
            raise AgentHandoffError(f"交接状态不能从 {handoff.status} 变为 {status}")
        if context_updates:
            handoff.context = {**(handoff.context or {}), **context_updates}
        handoff.status = status
        handoff.result = result if result is not None else handoff.result
        handoff.error_message = error_message
        db.commit()
        db.refresh(handoff)
        return handoff


agent_handoff_service = AgentHandoffService()
