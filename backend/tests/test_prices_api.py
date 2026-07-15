def _auth_headers(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "price_user",
            "email": "price_user@example.com",
            "password": "123456",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "price_user", "password": "123456"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_price_category_200_can_be_created_and_updated(client):
    headers = _auth_headers(client)
    created = client.post(
        "/api/prices",
        headers=headers,
        json={
            "category_id": 200,
            "sku_name": "stationery",
            "name": "文具",
            "barcode": "6900000000200",
            "unit_price": 2.5,
            "currency": "CNY",
        },
    )
    assert created.status_code == 201

    updated = client.put(
        "/api/prices/200",
        headers=headers,
        json={
            "sku_name": "stationery-updated",
            "name": "文具（已更新）",
            "barcode": "6900000000201",
            "unit_price": 3.75,
            "currency": "CNY",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["category_id"] == 200
    assert updated.json()["name"] == "文具（已更新）"
    assert updated.json()["unit_price"] == 3.75

    fetched = client.get("/api/prices/200", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["barcode"] == "6900000000201"
