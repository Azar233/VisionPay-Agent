def _register_and_login(client):
    assert (
        client.post(
            "/api/auth/register",
            json={
                "username": "customer_mode_user",
                "email": "customer-mode@example.com",
                "password": "account-password",
            },
        ).status_code
        == 200
    )
    response = client.post(
        "/api/auth/login",
        json={"username": "customer_mode_user", "password": "account-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_customer_mode_password_defaults_and_can_be_changed(client):
    headers = _register_and_login(client)

    status = client.get("/api/user/customer-mode-password", headers=headers)
    assert status.status_code == 200
    assert status.json() == {"configured": False, "uses_default": True}

    default_password = client.post(
        "/api/user/customer-mode-password/verify",
        headers=headers,
        json={"password": "123456"},
    )
    assert default_password.status_code == 200
    assert default_password.json() == {"valid": True}

    updated = client.put(
        "/api/user/customer-mode-password",
        headers=headers,
        json={"password": "654321"},
    )
    assert updated.status_code == 200
    assert updated.json()["configured"] is True

    assert (
        client.post(
            "/api/user/customer-mode-password/verify",
            headers=headers,
            json={"password": "123456"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/user/customer-mode-password/verify",
            headers=headers,
            json={"password": "654321"},
        ).status_code
        == 200
    )


def test_customer_mode_password_requires_six_digits(client):
    headers = _register_and_login(client)

    response = client.put(
        "/api/user/customer-mode-password",
        headers=headers,
        json={"password": "abcdef"},
    )
    assert response.status_code == 422
