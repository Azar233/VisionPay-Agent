import pytest

from app.config.settings import settings
from app.memory import LongTermMemoryStore, SensitiveMemoryError


class FakeEmbedding:
    @staticmethod
    def embed_query(text):
        normalized = str(text).lower()
        if "简洁" in normalized or "简短" in normalized:
            return [1.0, 0.0, 0.0]
        if "中文" in normalized:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


def _store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "LONG_TERM_MEMORY_MIN_SIMILARITY", 0.55)
    monkeypatch.setattr(settings, "LONG_TERM_MEMORY_DEDUPE_SIMILARITY", 0.90)
    store = LongTermMemoryStore()
    store.embedding = FakeEmbedding()
    return store


def test_memory_deduplicates_overrides_filters_and_blocks_sensitive_content(
    tmp_path, monkeypatch
):
    store = _store(tmp_path, monkeypatch)

    created = store.remember(
        user_id=1,
        content="回答保持简洁",
        category="output_format",
        session_uuid="s1",
    )
    duplicate = store.remember(
        user_id=1,
        content="回答保持简洁",
        category="output_format",
    )
    updated = store.remember(
        user_id=1,
        content="回答尽量简短",
        category="output_format",
    )
    other = store.remember(
        user_id=1,
        content="默认使用中文回答",
        category="preference",
    )

    assert created["action"] == "created"
    assert duplicate["action"] == "deduplicated"
    assert duplicate["id"] == created["id"]
    assert updated["action"] == "updated"
    assert updated["id"] == created["id"]
    assert updated["metadata"]["revision"] == 2
    assert store.list(user_id=1)["total"] == 2
    assert store.list(user_id=1, category="output_format")["items"][0]["id"] == created["id"]
    assert store.recall(
        user_id=1, query="希望回答简洁", category="output_format"
    )[0]["content"] == "回答尽量简短"
    assert store.recall(user_id=1, query="完全无关的任务") == []

    changed = store.update(
        user_id=1,
        memory_id=other["id"],
        content="始终使用中文回答",
        category="preference",
    )
    assert changed["metadata"]["revision"] == 2
    assert store.get(user_id=1, memory_id=other["id"])["content"] == "始终使用中文回答"
    assert store.delete(user_id=1, memory_id=other["id"])["deleted"] is True

    with pytest.raises(SensitiveMemoryError):
        store.remember(user_id=1, content="请记住 API Key: sk-sensitive-value")
    with pytest.raises(SensitiveMemoryError):
        store.update(
            user_id=1,
            memory_id=created["id"],
            content="我的密码是 123456",
        )


def test_memory_is_user_scoped(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    item = store.remember(user_id=1, content="回答保持简洁", category="preference")
    store.remember(user_id=2, content="回答保持简洁", category="preference")

    assert store.list(user_id=1)["total"] == 1
    assert store.list(user_id=2)["total"] == 1
    with pytest.raises(ValueError):
        store.get(user_id=2, memory_id=item["id"])


def test_memory_crud_api_and_user_isolation(client, tmp_path, monkeypatch):
    from app.memory import long_term as memory_module

    monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", str(tmp_path / "api-chroma"))
    monkeypatch.setattr(memory_module, "DashScopeEmbeddingClient", FakeEmbedding)
    client.post(
        "/api/auth/register",
        json={"username": "memory_owner", "email": "memory_owner@example.com", "password": "123456"},
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "memory_owner", "password": "123456"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    created = client.post(
        "/api/knowledge/memory",
        headers=headers,
        json={"content": "回答保持简洁", "category": "output_format"},
    )
    assert created.status_code == 200
    memory_id = created.json()["id"]
    assert client.get("/api/knowledge/memory", headers=headers).json()["total"] == 1
    assert client.get(
        "/api/knowledge/memory?category=output_format", headers=headers
    ).json()["items"][0]["id"] == memory_id
    changed = client.put(
        f"/api/knowledge/memory/{memory_id}",
        headers=headers,
        json={"content": "回答尽量简短", "category": "output_format"},
    )
    assert changed.status_code == 200
    assert changed.json()["content"] == "回答尽量简短"

    client.post(
        "/api/auth/register",
        json={"username": "memory_other", "email": "memory_other@example.com", "password": "123456"},
    )
    other_login = client.post(
        "/api/auth/login",
        json={"username": "memory_other", "password": "123456"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    assert client.get(
        f"/api/knowledge/memory/{memory_id}", headers=other_headers
    ).status_code == 404
    assert client.delete(
        f"/api/knowledge/memory/{memory_id}", headers=headers
    ).json()["deleted"] is True
    blocked = client.post(
        "/api/knowledge/memory",
        headers=headers,
        json={"content": "请保存我的 Token: abcdefghijklmnop"},
    )
    assert blocked.status_code == 400
