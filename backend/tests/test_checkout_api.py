from io import BytesIO

from PIL import Image

from app.entity.db_models import ProductPrice


def _auth_headers(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "checkout_user",
            "email": "checkout_user@example.com",
            "password": "123456",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "checkout_user", "password": "123456"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _image_bytes():
    stream = BytesIO()
    Image.new("RGB", (24, 24), color=(30, 130, 220)).save(stream, format="JPEG")
    return stream.getvalue()


def test_checkout_routes_require_auth(client):
    assert client.post("/api/checkout/detect").status_code == 401
    assert client.post(
        "/api/checkout/calculate",
        json={"items": [{"class_id": 0, "quantity": 1}]},
    ).status_code == 401


def test_checkout_detect_uses_detection_service(client, monkeypatch):
    from app.api import checkout as checkout_api

    captured = {}

    def fake_detect(path, **kwargs):
        captured.update(kwargs)
        assert path.is_file()
        return {
            "task_id": 11,
            "source": "single",
            "total_images": 1,
            "total_objects": 1,
            "items": [],
            "price_summary": {"total_price": 4.0, "pricing_complete": True},
        }

    monkeypatch.setattr(checkout_api.detection_service, "detect_single", fake_detect)
    response = client.post(
        "/api/checkout/detect",
        headers=_auth_headers(client),
        data={"scene_id": "2", "conf": "0.4", "iou": "0.5"},
        files={"file": ("checkout.jpg", _image_bytes(), "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["price_summary"]["total_price"] == 4.0
    assert captured["scene_id"] == 2
    assert captured["conf"] == 0.4
    assert captured["iou"] == 0.5
    assert isinstance(captured["user_id"], int)


def test_checkout_recalculates_with_database_prices(client, db_session):
    db_session.add_all(
        [
            ProductPrice(
                category_id=1,
                sku_name="1_puffed_food",
                name="薯片",
                unit_price=3.35,
                currency="CNY",
            ),
            ProductPrice(
                category_id=3,
                sku_name="3_drink",
                name="饮料",
                unit_price=2.5,
                currency="CNY",
            ),
        ]
    )
    db_session.commit()

    response = client.post(
        "/api/checkout/calculate",
        headers=_auth_headers(client),
        json={
            "items": [
                {"class_id": 0, "quantity": 2, "unit_price": 0.01},
                {"class_id": 0, "quantity": 3},
                {"class_id": 2, "quantity": 2},
            ]
        },
    )

    assert response.status_code == 200
    summary = response.json()
    assert summary["total_price"] == 21.75
    assert summary["pricing_complete"] is True
    assert summary["priced_objects"] == 7
    assert summary["unpriced_objects"] == 0
    assert summary["items"][0]["count"] == 5
    assert summary["items"][0]["unit_price"] == 3.35
    assert summary["items"][0]["subtotal"] == 16.75


def test_checkout_rejects_invalid_quantities(client):
    headers = _auth_headers(client)
    assert client.post(
        "/api/checkout/calculate",
        headers=headers,
        json={"items": []},
    ).status_code == 422
    assert client.post(
        "/api/checkout/calculate",
        headers=headers,
        json={"items": [{"class_id": 0, "quantity": 100}]},
    ).status_code == 422
    assert client.post(
        "/api/checkout/calculate",
        headers=headers,
        json={
            "items": [
                {"class_id": 0, "quantity": 60},
                {"class_id": 0, "quantity": 40},
            ]
        },
    ).status_code == 422
