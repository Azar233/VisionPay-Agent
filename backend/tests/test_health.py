def test_health_check(client):
    """测试基础健康检查接口"""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert data["code"] == 200
    assert data["message"] == "ok"
    assert data["data"]["status"] == "healthy"
    assert "app_name" in data["data"]
    assert "version" in data["data"]


def test_root(client):
    """测试根路径欢迎接口"""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert "message" in data
    assert "version" in data
    assert "docs" in data
