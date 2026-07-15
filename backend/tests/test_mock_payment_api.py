from datetime import datetime, timedelta

from app.entity.db_models import MockPaymentOrder, ProductPrice


def _auth_headers(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "mock_payment_user",
            "email": "mock_payment_user@example.com",
            "password": "123456",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "mock_payment_user", "password": "123456"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _seed_prices(db_session):
    db_session.add_all(
        [
            ProductPrice(category_id=1, sku_name="chips", name="薯片", unit_price=3.35, currency="CNY"),
            ProductPrice(category_id=3, sku_name="drink", name="饮料", unit_price=2.50, currency="CNY"),
        ]
    )
    db_session.commit()


def _create_order(client, headers):
    return client.post(
        "/api/mock-pay/orders",
        headers=headers,
        json={
            "items": [
                {"class_id": 0, "quantity": 2},
                {"class_id": 2, "quantity": 1},
            ]
        },
    )


def test_mock_payment_creation_is_authenticated_and_payment_is_public(client, db_session):
    _seed_prices(db_session)
    headers = _auth_headers(client)

    response = _create_order(client, headers)
    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "pending"
    assert created["amount"] == 9.2
    assert created["item_count"] == 3
    assert len(created["payment_token"]) >= 40
    assert created["items"][0]["unit_price"] == 3.35
    assert datetime.fromisoformat(created["expires_at"].replace("Z", "+00:00")).tzinfo is not None
    order = db_session.query(MockPaymentOrder).filter_by(order_uuid=created["order_uuid"]).one()
    assert order.user_id is not None

    mobile = client.get(f"/api/mock-pay/{created['payment_token']}")
    assert mobile.status_code == 200
    assert "payment_token" not in mobile.json()
    assert mobile.json()["order_uuid"] == created["order_uuid"]

    status = client.get(f"/api/mock-pay/orders/{created['order_uuid']}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "pending"

    paid = client.post(
        f"/api/mock-pay/{created['payment_token']}/confirm",
        json={"payment_method": "wechat"},
    )
    assert paid.status_code == 200
    first_result = paid.json()
    assert first_result["status"] == "paid"
    assert first_result["payment_method"] == "wechat"
    assert first_result["paid_at"] is not None

    repeated = client.post(
        f"/api/mock-pay/{created['payment_token']}/confirm",
        json={"payment_method": "alipay"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["payment_method"] == "wechat"
    assert repeated.json()["paid_at"] == first_result["paid_at"]

    final_status = client.get(f"/api/mock-pay/orders/{created['order_uuid']}/status")
    assert final_status.json()["status"] == "paid"


def test_mock_payment_expires_and_cannot_be_paid(client, db_session):
    _seed_prices(db_session)
    created = _create_order(client, _auth_headers(client)).json()

    order = db_session.query(MockPaymentOrder).filter(
        MockPaymentOrder.order_uuid == created["order_uuid"]
    ).one()
    order.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    mobile = client.get(f"/api/mock-pay/{created['payment_token']}")
    assert mobile.status_code == 200
    assert mobile.json()["status"] == "expired"

    confirm = client.post(
        f"/api/mock-pay/{created['payment_token']}/confirm",
        json={"payment_method": "wechat"},
    )
    assert confirm.status_code == 410


def test_mock_payment_rejects_unpriced_or_invalid_orders(client, db_session):
    _seed_prices(db_session)
    headers = _auth_headers(client)

    unpriced = client.post(
        "/api/mock-pay/orders",
        headers=headers,
        json={"items": [{"class_id": 10, "quantity": 1}]},
    )
    assert unpriced.status_code == 422

    duplicate_overflow = client.post(
        "/api/mock-pay/orders",
        headers=headers,
        json={
            "items": [
                {"class_id": 0, "quantity": 60},
                {"class_id": 0, "quantity": 40},
            ]
        },
    )
    assert duplicate_overflow.status_code == 422


def test_mock_payment_uses_detection_model_version_for_pricing(client, monkeypatch):
    from app.api import mock_payment as mock_payment_api

    captured = {}

    def fake_calculate_price(db, counts, model_version_id=None):
        del db
        captured["counts"] = counts
        captured["model_version_id"] = model_version_id
        return {
            "total_price": 4.50,
            "currency": "CNY",
            "pricing_complete": True,
            "items": [
                {
                    "class_id": 0,
                    "count": 1,
                    "unit_price": 4.50,
                    "subtotal": 4.50,
                }
            ],
        }

    monkeypatch.setattr(
        mock_payment_api.detection_service,
        "calculate_price",
        fake_calculate_price,
    )

    response = client.post(
        "/api/mock-pay/orders",
        headers=_auth_headers(client),
        json={
            "items": [{"class_id": 0, "quantity": 1}],
            "model_version_id": 42,
        },
    )

    assert response.status_code == 201
    assert captured == {"counts": {0: 1}, "model_version_id": 42}
