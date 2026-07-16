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


def test_dataset_tools_leave_parameter_collection_to_shared_interaction_tool():
    names = {item.name for item in dataset_tools.build_dataset_tools(1, "session")}

    assert "request_dataset_sample_form" not in names
    assert "prepare_add_samples_handoff" in names
