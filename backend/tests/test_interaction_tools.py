import json

import pytest

from app.agent.tools.interaction_tools import (
    build_interaction_tools,
    validate_form_submission,
)
from app.agent.tools.form_templates import FORM_TEMPLATES


def _training_form():
    tool = build_interaction_tools("training")[0]
    return json.loads(
        tool.invoke(
            {
                "purpose": "training.start",
                "known_values": {"dataset_version": "mutation-smoke-v1"},
                "option_overrides": {
                    "dataset_version_id": [
                        {"label": "mutation-smoke-v1（ID 2）", "value": 2}
                    ]
                },
            }
        )
    )


def test_shared_form_tool_generates_versioned_agent_scoped_schema():
    form = _training_form()

    assert form["form_type"] == "dynamic_parameters"
    assert form["schema_version"] == 1
    assert form["template_version"] == 1
    assert form["agent"] == "training"
    assert len(form["form_id"]) == 32
    assert form["purpose"] == "training.start"
    assert form["known_values"]["dataset_version"] == "mutation-smoke-v1"
    dataset_field = next(
        field for field in form["fields"] if field["name"] == "dataset_version_id"
    )
    assert dataset_field["type"] == "select"
    assert dataset_field["options"][0]["value"] == 2
    assert [field["name"] for field in form["fields"]] == [
        "scene_id", "dataset_version_id", "model_name", "epochs", "img_size",
        "batch_size", "device", "optimizer", "lr0",
    ]


def test_same_purpose_always_produces_same_schema():
    first = _training_form()
    second = _training_form()

    first.pop("form_id")
    second.pop("form_id")
    assert first == second


@pytest.mark.parametrize("purpose", list(FORM_TEMPLATES))
def test_every_registered_operation_has_a_deterministic_schema(purpose):
    agent_name = purpose.split(".", 1)[0]
    tool = build_interaction_tools(agent_name)[0]

    first = json.loads(tool.invoke({"purpose": purpose}))
    second = json.loads(tool.invoke({"purpose": purpose}))
    first.pop("form_id")
    second.pop("form_id")

    assert first == second
    assert first["fields"]
    assert len({field["name"] for field in first["fields"]}) == len(first["fields"])


def test_agent_cannot_request_another_domain_form():
    tool = build_interaction_tools("catalog")[0]

    with pytest.raises(ValueError, match="无权生成"):
        tool.invoke({"purpose": "training.start"})


def test_dynamic_dataset_version_options_filled_server_side(monkeypatch):
    """LLM 未提供 option_overrides 时，表单构建器应自行填充数据集版本下拉。"""
    from app.services import dataset_service as dataset_service_module

    expected = {
        "total": 2,
        "items": [
            {"id": 5, "version": "v5", "status": "published", "is_current": True},
            {"id": 3, "version": "v3", "status": "draft", "is_current": False},
        ],
    }

    class _FakeDb:
        def close(self):
            pass

    monkeypatch.setattr("app.database.session.SessionLocal", lambda: _FakeDb())
    monkeypatch.setattr(
        dataset_service_module.dataset_service,
        "list",
        lambda session, **kwargs: expected,
    )

    tool = build_interaction_tools("catalog")[0]
    form = json.loads(tool.invoke({"purpose": "catalog.list_prices"}))

    field = next(f for f in form["fields"] if f["name"] == "dataset_version_id")
    assert [option["value"] for option in field["options"]] == [5, 3]
    assert "v5" in field["options"][0]["label"]
    assert "当前" in field["options"][0]["label"]


def test_dynamic_option_resolver_failure_does_not_break_form(monkeypatch):
    """选项解析失败时表单仍应生成，下拉留空而不是整体报错。"""
    monkeypatch.setattr(
        "app.agent.tools.interaction_tools._DYNAMIC_OPTION_RESOLVERS",
        {"dataset_version_id": lambda: (_ for _ in ()).throw(RuntimeError("db down"))},
    )

    tool = build_interaction_tools("catalog")[0]
    form = json.loads(tool.invoke({"purpose": "catalog.list_prices"}))

    field = next(f for f in form["fields"] if f["name"] == "dataset_version_id")
    assert field["options"] == []


def test_submission_validation_normalizes_numbers_and_rejects_options():
    form = _training_form()

    values = validate_form_submission(
        form,
        {
            "scene_id": 1,
            "dataset_version_id": 2,
            "model_name": "yolov11n",
            "epochs": "25",
            "img_size": 640,
            "batch_size": 16,
            "device": "cpu",
            "optimizer": "AdamW",
            "lr0": 0.01,
        },
    )
    assert values["epochs"] == 25
    assert values["optimizer"] == "AdamW"

    with pytest.raises(ValueError, match="无效选项"):
        validate_form_submission(
            form,
            {
                "scene_id": 1,
                "dataset_version_id": 2,
                "model_name": "yolov11n",
                "epochs": 25,
                "img_size": 640,
                "batch_size": 16,
                "device": "cpu",
                "optimizer": "Unknown",
                "lr0": 0.01,
            },
        )


def test_submission_validation_ignores_hidden_conditional_fields():
    form = {
        "form_type": "dynamic_parameters",
        "fields": [
            {
                "name": "mode",
                "label": "模式",
                "type": "select",
                "options": [
                    {"label": "新商品", "value": "new"},
                    {"label": "场景", "value": "scene"},
                ],
            },
            {
                "name": "name",
                "label": "商品名称",
                "type": "text",
                "required": True,
                "visible_when": {"field": "mode", "equals": "new"},
            },
        ],
    }

    assert validate_form_submission(form, {"mode": "scene"}) == {"mode": "scene"}
