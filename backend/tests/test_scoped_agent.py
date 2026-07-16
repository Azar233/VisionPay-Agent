import pytest

from app.agent.scoped_agent import ScopedToolAgent


class _FakeExecutor:
    async def astream_events(self, payload, version):
        yield {
            "event": "on_tool_end",
            "name": "prepare_add_samples_handoff",
            "data": {
                "output": (
                    '{"handoff_uuid":"handoff-1","page_url":"/datasets?handoff_id=handoff-1",'
                    '"status":"ready_for_handoff","context":{"dataset_id":7}}'
                )
            },
        }


class _FakeConfirmationExecutor:
    async def astream_events(self, payload, version):
        yield {
            "event": "on_tool_end",
            "name": "preview_update_product_price",
            "data": {
                "output": (
                    '{"operation_uuid":"operation-1","status":"pending","risk_level":"R2",'
                    '"confirmation_token":"secret-token","impact":{"title":"更新商品价格"}}'
                )
            },
        }


class _FakeInputFormExecutor:
    async def astream_events(self, payload, version):
        yield {
            "event": "on_tool_end",
            "name": "request_dataset_sample_form",
            "data": {
                "output": (
                    '{"form_type":"dataset_add_samples","title":"补充样品信息",'
                    '"defaults":{"dataset_id":6,"mode":"train_new"}}'
                )
            },
        }


@pytest.mark.asyncio
async def test_dataset_handoff_tool_emits_structured_event():
    agent = ScopedToolAgent.__new__(ScopedToolAgent)
    agent.name = "dataset"
    agent.executor = _FakeExecutor()

    events = [event async for event in agent.stream("继续")]

    handoff = next(event for event in events if event["type"] == "handoff_required")
    assert handoff["agent"] == "dataset"
    assert handoff["handoff_id"] == "handoff-1"
    assert handoff["page_url"].endswith("handoff-1")
    assert handoff["context"]["dataset_id"] == 7


@pytest.mark.asyncio
async def test_preview_tool_emits_confirmation_required_event():
    agent = ScopedToolAgent.__new__(ScopedToolAgent)
    agent.name = "catalog"
    agent.executor = _FakeConfirmationExecutor()

    events = [event async for event in agent.stream("把价格改为 4.2")]

    confirmation = next(
        event for event in events if event["type"] == "confirmation_required"
    )
    assert confirmation["agent"] == "catalog"
    assert confirmation["operation"]["operation_uuid"] == "operation-1"
    assert confirmation["operation"]["confirmation_token"] == "secret-token"


@pytest.mark.asyncio
async def test_dataset_form_tool_emits_structured_input_form_event():
    agent = ScopedToolAgent.__new__(ScopedToolAgent)
    agent.name = "dataset"
    agent.executor = _FakeInputFormExecutor()

    events = [event async for event in agent.stream("添加新商品")]

    form_event = next(event for event in events if event["type"] == "input_form")
    assert form_event["agent"] == "dataset"
    assert form_event["form"]["form_type"] == "dataset_add_samples"
    assert form_event["form"]["defaults"]["dataset_id"] == 6
