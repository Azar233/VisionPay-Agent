import asyncio
from unittest.mock import patch

import pytest

from app.agent.orchestrator import MultiAgentOrchestrator, sanitize_result_payload
from app.agent.routing import RouteDecision


@pytest.fixture
def orchestrator(monkeypatch):
    monkeypatch.setattr(
        "app.agent.orchestrator.retrieval_query_rewriter.rewrite",
        lambda *args, **kwargs: type("R", (), {"rewritten_query": ""})(),
    )
    monkeypatch.setattr(
        "app.agent.orchestrator.LongTermMemoryStore",
        lambda: type("M", (), {"recall": lambda *args, **kwargs: []})(),
    )
    return MultiAgentOrchestrator(
        user_id=1,
        scene_id=None,
        session_uuid="test-session",
    )


def _fake_summary(events=None):
    async def gen(drafts, structural, agents, message, history):
        for event in events or [{"type": "text_chunk", "agent": "supervisor", "content": "汇总结果"}]:
            yield event
    return gen


@pytest.mark.asyncio
async def test_parallel_agents_run_concurrently(orchestrator):
    """Agents should execute concurrently, not sequentially."""
    delays = {"agent_a": 0.2, "agent_b": 0.2}

    async def fake_stream(agent_name, message, attachment_paths, history):
        await asyncio.sleep(delays[agent_name])
        yield {"type": "text_chunk", "content": f"{agent_name} done"}

    orchestrator._management_agent = lambda agent_name: type(
        "A",
        (),
        {"stream": lambda self, *args, **kwargs: fake_stream(agent_name, *args, **kwargs)},
    )()

    start = asyncio.get_event_loop().time()
    results = await orchestrator._execute_parallel_agents(
        "msg", [], [], ["agent_a", "agent_b"]
    )
    elapsed = asyncio.get_event_loop().time() - start

    assert len(results) == 2
    assert elapsed < 0.35, f"agents ran sequentially (elapsed {elapsed}s)"


@pytest.mark.asyncio
async def test_parallel_agent_timeout_does_not_block_others(orchestrator, monkeypatch):
    monkeypatch.setattr("app.agent.orchestrator.PARALLEL_AGENT_TIMEOUT_SECONDS", 0.1)

    async def fast_stream(*args, **kwargs):
        yield {"type": "text_chunk", "content": "fast"}

    async def slow_stream(*args, **kwargs):
        await asyncio.sleep(10)
        yield {"type": "text_chunk", "content": "slow"}

    orchestrator._management_agent = lambda agent: type(
        "A", (), {"stream": fast_stream if agent == "fast" else slow_stream}
    )()

    results = await orchestrator._execute_parallel_agents("msg", [], [], ["fast", "slow"])

    by_agent = {name: events for name, events, _text in results}
    assert any(event.get("type") == "text_chunk" for event in by_agent["fast"])
    assert any(
        event.get("type") == "error" and "超时" in event.get("content", "")
        for event in by_agent["slow"]
    )


@pytest.mark.asyncio
async def test_parallel_agent_exception_does_not_break_pipeline(orchestrator):
    async def ok_stream(*args, **kwargs):
        yield {"type": "text_chunk", "content": "ok"}

    async def bad_stream(*args, **kwargs):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    orchestrator._management_agent = lambda agent: type(
        "A", (), {"stream": ok_stream if agent == "ok" else bad_stream}
    )()

    results = await orchestrator._execute_parallel_agents("msg", [], [], ["ok", "bad"])

    by_agent = {name: events for name, events, _text in results}
    assert any(event.get("type") == "text_chunk" for event in by_agent["ok"])
    assert any(
        event.get("type") == "error" and "boom" in event.get("content", "")
        for event in by_agent["bad"]
    )


@pytest.mark.asyncio
async def test_parallel_stream_withholds_text_and_summarizes(orchestrator, monkeypatch):
    """Parallel stream yields structural events live, withholds drafts, then summarizes."""
    monkeypatch.setattr(orchestrator, "_supervisor_summary", _fake_summary())

    async def stream_a(self, message, history, runtime_context):
        yield {"type": "tool_call", "tool": "tool_a"}
        yield {"type": "text_chunk", "content": "draft A"}
        yield {"type": "tool_result", "tool": "tool_a", "content": "{}"}

    async def stream_b(self, message, history, runtime_context):
        yield {"type": "text_chunk", "content": "draft B"}

    orchestrator._management_agent = lambda agent: type(
        "A", (), {"stream": stream_a if agent == "a" else stream_b}
    )()

    decision = RouteDecision.multi(
        agents=["a", "b"],
        mode="parallel",
        tasks={"a": "子任务A", "b": "子任务B"},
        method="llm",
        confidence=0.9,
        reason="test",
    )
    events = [event async for event in orchestrator._parallel_stream("msg", [], [], decision)]

    types = [event.get("type") for event in events]
    # 各 Agent 的文字草稿不直接流出，只出现 supervisor 的汇总文字。
    assert "tool_call" in types
    assert "tool_result" in types
    text_events = [e for e in events if e.get("type") == "text_chunk"]
    assert len(text_events) == 1
    assert text_events[0]["content"] == "汇总结果"
    assert text_events[0]["agent"] == "supervisor"
    assert types[0] == "parallel_progress"


@pytest.mark.asyncio
async def test_parallel_stream_distributes_sub_tasks(orchestrator, monkeypatch):
    """Each parallel agent receives its scoped sub-task, not the raw message."""
    monkeypatch.setattr(orchestrator, "_supervisor_summary", _fake_summary())
    received = {}

    def spy_stream(agent):
        async def gen(self, message, history, runtime_context):
            received[agent] = message
            yield {"type": "text_chunk", "content": "ok"}
        return gen

    orchestrator._management_agent = lambda agent: type(
        "A", (), {"stream": spy_stream(agent)}
    )()

    decision = RouteDecision.multi(
        agents=["a", "b"],
        mode="parallel",
        tasks={"a": "只回答A部分", "b": "只回答B部分"},
        method="llm",
        confidence=0.9,
        reason="test",
    )
    async for _event in orchestrator._parallel_stream("原始消息", [], [], decision):
        pass

    assert received == {"a": "只回答A部分", "b": "只回答B部分"}


@pytest.mark.asyncio
async def test_parallel_management_agents_receive_collaboration_context(orchestrator, monkeypatch):
    """Collaboration mode forbids input forms via injected runtime context."""
    from app.agent.orchestrator import COLLABORATION_CONTEXT

    monkeypatch.setattr(orchestrator, "_supervisor_summary", _fake_summary())
    seen_contexts = []

    def spy(agent):
        async def gen(self, message, history, runtime_context):
            seen_contexts.append((agent, runtime_context))
            yield {"type": "text_chunk", "content": "ok"}
        return gen

    orchestrator._management_agent = lambda agent: type("A", (), {"stream": spy(agent)})()

    decision = RouteDecision.parallel(agents=["a", "b"], method="parallel", confidence=0.9, reason="t")
    async for _event in orchestrator._parallel_stream("msg", [], [], decision):
        pass

    assert len(seen_contexts) == 2
    for _agent, ctx in seen_contexts:
        assert COLLABORATION_CONTEXT in ctx


@pytest.mark.asyncio
async def test_single_agent_stream_has_no_collaboration_context(orchestrator):
    """Single-agent conversations keep the normal form-enabled behavior."""
    from app.agent.orchestrator import COLLABORATION_CONTEXT

    seen_contexts = []

    async def gen(self, message, history, runtime_context):
        seen_contexts.append(runtime_context)
        yield {"type": "text_chunk", "content": "ok"}

    orchestrator._management_agent = lambda agent: type("A", (), {"stream": gen})()

    decision = RouteDecision.single("knowledge", "test", 1.0, "t")
    async for _event in orchestrator.stream("msg", [], [], decision=decision):
        pass

    assert seen_contexts
    assert all(COLLABORATION_CONTEXT not in (ctx or "") for ctx in seen_contexts)


@pytest.mark.asyncio
async def test_parallel_stream_summarizes_despite_interactive(orchestrator):
    """Interactive cards stream through live, and the remaining agents' answers
    are still summarized instead of being discarded."""
    summary_called = []

    async def fake_summary(drafts, structural, agents, message, history):
        summary_called.append(True)
        yield {"type": "text_chunk", "content": "汇总"}

    orchestrator._supervisor_summary = fake_summary

    async def form_stream(self, message, history, runtime_context):
        yield {"type": "input_form", "form": {"form_type": "x"}}
        yield {"type": "text_chunk", "content": "draft"}

    orchestrator._management_agent = lambda agent: type("A", (), {"stream": form_stream})()

    decision = RouteDecision.parallel(agents=["a", "b"], method="parallel", confidence=0.9, reason="t")
    events = [event async for event in orchestrator._parallel_stream("msg", [], [], decision)]

    assert summary_called == [True]
    assert any(event.get("type") == "input_form" for event in events)
    assert any(event.get("type") == "text_chunk" and event.get("content") == "汇总" for event in events)


@pytest.mark.asyncio
async def test_pipeline_stream_feeds_upstream_and_summarizes(orchestrator, monkeypatch):
    """Pipeline runs sequentially, injects upstream context, then summarizes."""
    monkeypatch.setattr(orchestrator, "_supervisor_summary", _fake_summary())
    seen_contexts = []

    async def detection_stream(message, attachment_paths, history, extra_context=None):
        yield {"type": "detection_result", "result": {"items": ["cola"]}}
        yield {"type": "text_chunk", "content": "found cola"}

    async def catalog_stream(message, history, runtime_context):
        seen_contexts.append(runtime_context)
        yield {"type": "text_chunk", "content": "price is 5"}

    orchestrator.detection_agent_factory = lambda **kwargs: type(
        "D",
        (),
        {"stream": lambda self, m, a, h: detection_stream(m, a, h)},
    )()
    orchestrator._management_agent = lambda agent: type(
        "C", (), {"stream": lambda self, m, h, c: catalog_stream(m, h, c)}
    )()

    decision = RouteDecision.multi(
        agents=["detection", "catalog"],
        mode="pipeline",
        tasks={"detection": "识别商品", "catalog": "查询价格"},
        method="llm",
        confidence=0.9,
        reason="test",
    )
    events = [event async for event in orchestrator._pipeline_stream("msg", [], [], decision)]

    assert any(event.get("type") == "detection_result" for event in events)
    # catalog 应通过 runtime_context 收到 detection 的结果。
    assert any("cola" in (ctx or "") for ctx in seen_contexts)
    text_events = [e for e in events if e.get("type") == "text_chunk"]
    assert [e["content"] for e in text_events] == ["汇总结果"]


@pytest.mark.asyncio
async def test_pipeline_stops_downstream_on_primary_failure(orchestrator, monkeypatch):
    """Primary failure stops downstream agents; summary still reports the error."""
    monkeypatch.setattr(orchestrator, "_supervisor_summary", _fake_summary())
    called = []

    async def bad_detection(*args, **kwargs):
        raise RuntimeError("detection failed")
        yield

    async def catalog_stream(*args, **kwargs):
        called.append("catalog")
        yield {"type": "text_chunk", "content": "price"}

    orchestrator.detection_agent_factory = lambda **kwargs: type(
        "D", (), {"stream": lambda self, *args, **kwargs: bad_detection(*args, **kwargs)}
    )()
    orchestrator._management_agent = lambda agent: type(
        "C", (), {"stream": lambda self, *args, **kwargs: catalog_stream(*args, **kwargs)}
    )()

    decision = RouteDecision.pipeline(
        agents=["detection", "catalog"], method="pipeline", confidence=0.9, reason="t"
    )
    events = [event async for event in orchestrator._pipeline_stream("msg", [], [], decision)]

    assert called == []
    assert any(
        event.get("type") == "error" and "detection failed" in event.get("content", "")
        for event in events
    )


def test_sanitize_result_payload_strips_images_and_caps_strings():
    payload = {
        "object_count": 2,
        "detections": [{"class_name": "cola", "bbox": [1, 2, 3, 4]}],
        "annotated_image": "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
        "nested": {"annotated_frame": "data:image/jpeg;base64,AAAA"},
        "long_text": "x" * 5000,
    }

    cleaned = sanitize_result_payload(payload)

    assert "annotated_image" not in cleaned
    assert "annotated_frame" not in cleaned["nested"]
    assert cleaned["object_count"] == 2
    assert cleaned["detections"][0]["class_name"] == "cola"
    assert cleaned["long_text"].endswith("...[截断]")
    assert sanitize_result_payload("data:image/png;base64,xx") == "[图片数据已省略]"


@pytest.mark.asyncio
async def test_supervisor_summary_excludes_base64_from_llm_input(orchestrator):
    """The summary LLM must receive detection results without the base64 image."""
    captured = {}

    class FakeChunk:
        def __init__(self, content):
            self.content = content

    class FakeLLM:
        def __init__(self, **kwargs):
            pass

        async def astream_events(self, messages, version="v2"):
            captured["messages"] = messages
            yield {"event": "on_chat_model_stream", "data": {"chunk": FakeChunk("done")}, "run_id": "r1"}

    structural = {
        "detection": [
            {
                "type": "detection_result",
                "result": {
                    "object_count": 7,
                    "annotated_image": "data:image/jpeg;base64,/9j/HUGE",
                },
            }
        ]
    }

    with patch("langchain_openai.ChatOpenAI", FakeLLM):
        async for _event in orchestrator._supervisor_summary({}, structural, ["detection"], "msg", []):
            pass

    prompt_text = "".join(
        str(getattr(m, "content", "")) for m in captured["messages"]
    )
    assert "data:image" not in prompt_text
    assert "/9j/HUGE" not in prompt_text
    assert "object_count" in prompt_text


@pytest.mark.asyncio
async def test_pipeline_upstream_context_excludes_base64(orchestrator, monkeypatch):
    """Downstream pipeline agents receive upstream results without base64 images."""
    monkeypatch.setattr(orchestrator, "_supervisor_summary", _fake_summary())
    seen_contexts = []

    async def detection_stream(message, attachment_paths, history):
        yield {
            "type": "detection_result",
            "result": {"items": ["cola"], "annotated_image": "data:image/jpeg;base64,HUGE"},
        }

    async def catalog_stream(self, message, history, runtime_context):
        seen_contexts.append(runtime_context)
        yield {"type": "text_chunk", "content": "price"}

    orchestrator.detection_agent_factory = lambda **kwargs: type(
        "D", (), {"stream": lambda self, m, a, h: detection_stream(m, a, h)}
    )()
    orchestrator._management_agent = lambda agent: type(
        "C", (), {"stream": catalog_stream}
    )()

    decision = RouteDecision.pipeline(
        agents=["detection", "catalog"], method="pipeline", confidence=0.9, reason="t"
    )
    async for _event in orchestrator._pipeline_stream("msg", [], [], decision):
        pass

    assert seen_contexts
    assert all("data:image" not in (ctx or "") for ctx in seen_contexts)
    assert any("cola" in (ctx or "") for ctx in seen_contexts)


@pytest.mark.asyncio
async def test_supervisor_summary_streams_llm(orchestrator):
    """Summary LLM streams text chunks tagged as supervisor."""
    drafts = {"a": "草稿A", "b": "草稿B"}
    structural = {"a": [], "b": []}

    class FakeChunk:
        def __init__(self, content):
            self.content = content

    class FakeLLM:
        def __init__(self, **kwargs):
            pass

        async def astream_events(self, messages, version="v2"):
            for text in ["统一", "回复"]:
                yield {"event": "on_chat_model_stream", "data": {"chunk": FakeChunk(text)}, "run_id": "r1"}

    with patch("langchain_openai.ChatOpenAI", FakeLLM):
        events = [
            event
            async for event in orchestrator._supervisor_summary(
                drafts, structural, ["a", "b"], "msg", []
            )
        ]

    texts = [e["content"] for e in events if e.get("type") == "text_chunk"]
    assert texts == ["统一", "回复"]
    assert all(e["agent"] == "supervisor" for e in events if e.get("type") == "text_chunk")
    assert any(e.get("status") == "summarizing" for e in events if e.get("type") == "parallel_progress")


@pytest.mark.asyncio
async def test_supervisor_summary_includes_custom_instructions(orchestrator):
    """User custom instructions must reach the summary LLM like any other agent."""
    orchestrator.custom_instructions = "用活泼的语气回答"
    captured = {}

    class FakeChunk:
        def __init__(self, content):
            self.content = content

    class FakeLLM:
        def __init__(self, **kwargs):
            pass

        async def astream_events(self, messages, version="v2"):
            captured["messages"] = messages
            yield {"event": "on_chat_model_stream", "data": {"chunk": FakeChunk("done")}, "run_id": "r1"}

    with patch("langchain_openai.ChatOpenAI", FakeLLM):
        async for _event in orchestrator._supervisor_summary({"a": "草稿"}, {}, ["a"], "msg", []):
            pass

    system_text = str(captured["messages"][0].content)
    assert "用活泼的语气回答" in system_text
    assert "用户自定义响应指令" in system_text


@pytest.mark.asyncio
async def test_supervisor_summary_falls_back_on_llm_failure(orchestrator):
    drafts = {"a": "草稿A"}
    structural = {"a": [{"type": "tool_result", "tool": "t", "content": "data"}]}

    with patch("langchain_openai.ChatOpenAI", side_effect=RuntimeError("LLM down")):
        events = [
            event
            async for event in orchestrator._supervisor_summary(drafts, structural, ["a"], "msg", [])
        ]

    text = "".join(e["content"] for e in events if e.get("type") == "text_chunk")
    assert "草稿A" in text
    assert "data" in text


@pytest.mark.asyncio
async def test_supervisor_summary_handles_empty_material(orchestrator):
    events = [
        event
        async for event in orchestrator._supervisor_summary({}, {}, ["a"], "msg", [])
    ]
    assert len(events) == 1
    assert "未返回可汇总" in events[0]["content"]


@pytest.mark.asyncio
async def test_aroute_defers_write_intents_to_llm_then_keyword_fallback(orchestrator, monkeypatch):
    """Write intents go to the LLM router first; the deterministic keyword chain
    only serves as the fallback when the LLM is unavailable."""
    llm_called = []

    async def fake_llm_route(*args, **kwargs):
        llm_called.append(True)
        return None

    monkeypatch.setattr(orchestrator.router, "route_llm", fake_llm_route)
    decision = await orchestrator.aroute("把可乐的价格改为 5 元")

    # LLM 路由不可用 → 降级到 route() 的关键词兜底，仍能路由到 catalog。
    assert llm_called == [True]
    assert decision.agent == "catalog"
    assert decision.method == "explicit_intent"


@pytest.mark.asyncio
async def test_aroute_uses_llm_then_fallback(orchestrator, monkeypatch):
    expected = RouteDecision.multi(
        agents=["knowledge"], mode="single", tasks={"knowledge": "解释 mAP"},
        method="llm", confidence=0.9, reason="test",
    )

    async def fake_llm(*args, **kwargs):
        return expected

    monkeypatch.setattr(orchestrator.router, "route_llm", fake_llm)
    monkeypatch.setattr(
        orchestrator.router, "deterministic_safety", lambda *args, **kwargs: None
    )
    assert await orchestrator.aroute("什么是 mAP") == expected

    async def none_llm(*args, **kwargs):
        return None

    monkeypatch.setattr(orchestrator.router, "route_llm", none_llm)
    monkeypatch.setattr(
        orchestrator.router,
        "route",
        lambda *args, **kwargs: RouteDecision.single("knowledge", "fallback", 0.3, "fb"),
    )
    decision = await orchestrator.aroute("什么是 mAP")
    assert decision.method == "fallback"
