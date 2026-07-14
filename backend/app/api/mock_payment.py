"""Public, token-protected mock payment APIs for local demonstrations."""

from __future__ import annotations

import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.session import get_db
from app.entity.db_models import MockPaymentOrder
from app.entity.schemas import (
    CheckoutCalculateRequest,
    MockPaymentConfirmRequest,
    MockPaymentOrderCreated,
    MockPaymentOrderView,
    MockPaymentStatusResponse,
)
from app.services.detection_service import detection_service

router = APIRouter(prefix="/api/mock-pay", tags=["模拟支付"])


def _utc_timestamp(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _serialize_order(order: MockPaymentOrder, include_token: bool = False) -> dict:
    payload = {
        "order_uuid": order.order_uuid,
        "status": order.status,
        "currency": order.currency,
        "amount": float(order.amount),
        "item_count": order.item_count,
        "items": order.items_snapshot,
        "payment_method": order.payment_method,
        "created_at": _utc_timestamp(order.created_at),
        "expires_at": _utc_timestamp(order.expires_at),
        "paid_at": _utc_timestamp(order.paid_at),
    }
    if include_token:
        payload["payment_token"] = order.payment_token
    return payload


def _expire_if_needed(db: Session, order: MockPaymentOrder) -> MockPaymentOrder:
    if order.status == "pending" and order.expires_at <= datetime.utcnow():
        db.query(MockPaymentOrder).filter(
            MockPaymentOrder.id == order.id,
            MockPaymentOrder.status == "pending",
        ).update(
            {"status": "expired", "updated_at": datetime.utcnow()},
            synchronize_session=False,
        )
        db.commit()
        db.refresh(order)
    return order


def _get_by_token(db: Session, payment_token: str) -> MockPaymentOrder:
    order = db.query(MockPaymentOrder).filter(
        MockPaymentOrder.payment_token == payment_token
    ).first()
    if order is None:
        raise HTTPException(status_code=404, detail="支付订单不存在")
    return _expire_if_needed(db, order)


@router.post(
    "/orders",
    response_model=MockPaymentOrderCreated,
    status_code=status.HTTP_201_CREATED,
    summary="创建模拟支付订单",
)
def create_mock_payment_order(
    payload: CheckoutCalculateRequest,
    db: Session = Depends(get_db),
):
    counts: Counter[int] = Counter()
    for item in payload.items:
        next_count = counts[item.class_id] + item.quantity
        if next_count > 99:
            raise HTTPException(status_code=422, detail="单个商品数量不能超过 99")
        counts[item.class_id] = next_count

    summary = detection_service.calculate_price(db, dict(counts))
    if not summary["pricing_complete"]:
        raise HTTPException(status_code=422, detail="订单中存在未定价商品，无法创建支付订单")
    if Decimal(str(summary["total_price"])) <= 0:
        raise HTTPException(status_code=422, detail="订单金额必须大于 0")

    now = datetime.utcnow()
    order = MockPaymentOrder(
        order_uuid=str(uuid4()),
        payment_token=secrets.token_urlsafe(32),
        status="pending",
        currency=summary["currency"],
        amount=Decimal(str(summary["total_price"])),
        item_count=sum(counts.values()),
        items_snapshot=summary["items"],
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=settings.MOCK_PAYMENT_EXPIRE_MINUTES),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return _serialize_order(order, include_token=True)


@router.get(
    "/orders/{order_uuid}/status",
    response_model=MockPaymentStatusResponse,
    summary="查询模拟订单支付状态",
)
def get_mock_payment_status(order_uuid: str, db: Session = Depends(get_db)):
    order = db.query(MockPaymentOrder).filter(
        MockPaymentOrder.order_uuid == order_uuid
    ).first()
    if order is None:
        raise HTTPException(status_code=404, detail="支付订单不存在")
    order = _expire_if_needed(db, order)
    return {
        "order_uuid": order.order_uuid,
        "status": order.status,
        "expires_at": _utc_timestamp(order.expires_at),
        "paid_at": _utc_timestamp(order.paid_at),
    }


@router.get(
    "/{payment_token}",
    response_model=MockPaymentOrderView,
    summary="读取手机端模拟付款订单",
)
def get_mock_payment_order(payment_token: str, db: Session = Depends(get_db)):
    return _serialize_order(_get_by_token(db, payment_token))


@router.post(
    "/{payment_token}/confirm",
    response_model=MockPaymentOrderView,
    summary="确认模拟付款",
)
def confirm_mock_payment(
    payment_token: str,
    payload: MockPaymentConfirmRequest,
    db: Session = Depends(get_db),
):
    order = _get_by_token(db, payment_token)
    if order.status == "expired":
        raise HTTPException(status_code=410, detail="支付二维码已过期")
    if order.status == "paid":
        return _serialize_order(order)

    paid_at = datetime.utcnow()
    updated = db.query(MockPaymentOrder).filter(
        MockPaymentOrder.id == order.id,
        MockPaymentOrder.status == "pending",
        MockPaymentOrder.expires_at > paid_at,
    ).update(
        {
            "status": "paid",
            "payment_method": payload.payment_method,
            "paid_at": paid_at,
            "updated_at": paid_at,
        },
        synchronize_session=False,
    )
    db.commit()
    db.refresh(order)

    if updated == 0:
        order = _expire_if_needed(db, order)
        if order.status != "paid":
            raise HTTPException(status_code=410, detail="支付二维码已过期")
    return _serialize_order(order)
