import json

from app.agent.tools import dataset_tools


class _FakeDb:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_list_dataset_versions_returns_all_versions(monkeypatch):
    db = _FakeDb()
    calls = []
    expected = {
        "total": 4,
        "items": [{"id": index, "version": f"v{index}"} for index in range(1, 5)],
    }

    def fake_list(session, **kwargs):
        calls.append((session, kwargs))
        return expected

    monkeypatch.setattr(dataset_tools, "SessionLocal", lambda: db)
    monkeypatch.setattr(dataset_tools.dataset_service, "list", fake_list)
    tool = next(
        item
        for item in dataset_tools.build_dataset_tools(1, "session")
        if item.name == "list_dataset_versions"
    )

    result = json.loads(tool.invoke({}))

    assert result == expected
    assert calls[0][1]["current_only"] is False
    assert calls[0][1]["limit"] == 100
    assert db.closed is True


def test_request_dataset_sample_form_is_non_mutating_and_has_defaults():
    tool = next(
        item
        for item in dataset_tools.build_dataset_tools(1, "session")
        if item.name == "request_dataset_sample_form"
    )

    result = json.loads(
        tool.invoke({"dataset_id": 6, "dataset_version": "mutation-smoke-v2"})
    )

    assert result["form_type"] == "dataset_add_samples"
    assert result["defaults"] == {
        "dataset_id": 6,
        "dataset_version": "mutation-smoke-v2",
        "mode": "train_new",
    }
