import pytest

from app.agent.routing import AgentRouter, RouteDecision
from app.config.settings import settings


@pytest.fixture(autouse=True)
def disable_external_embedding(monkeypatch):
    """Route unit tests must not call DashScope or require an API key."""
    monkeypatch.setattr(settings, "AGENT_ROUTING_MODE", "hybrid")
    monkeypatch.setattr(AgentRouter, "_embedding_route", lambda self, message: None)


def test_keyword_routes_cover_management_domains():
    router = AgentRouter()

    assert router.route("查看当前数据集版本").agent == "dataset"
    assert router.route("最近训练到第几轮了").agent == "training"
    assert router.route("查询可乐的价格").agent == "catalog"
    assert router.route("检测这张商品图").agent == "detection"


def test_attachment_always_routes_to_detection():
    decision = AgentRouter().route("帮我处理一下", has_attachments=True)

    assert decision.agent == "detection"
    assert decision.method == "attachment"
    assert decision.confidence == 1.0


def test_dataset_conversation_keeps_attachment_in_dataset_agent():
    decision = AgentRouter().route(
        "我把样品图发来了",
        has_attachments=True,
        preferred_agent="dataset",
    )

    assert decision.agent == "dataset"
    assert decision.method == "conversation_context"


def test_active_dataset_handoff_keeps_attachment_in_dataset_agent():
    decision = AgentRouter().route(
        "继续处理",
        has_attachments=True,
        active_workflow_agent="dataset",
    )

    assert decision.agent == "dataset"
    assert decision.method == "active_workflow"


def test_explicit_detection_request_overrides_dataset_context():
    decision = AgentRouter().route(
        "请检测这张图片",
        has_attachments=True,
        preferred_agent="dataset",
        active_workflow_agent="dataset",
    )

    assert decision.agent == "detection"
    assert decision.method == "attachment_intent"


@pytest.mark.parametrize(
    "message",
    ["识别图片", "检测图片", "批量识别这些照片", "识别图像中的商品"],
)
def test_short_detection_command_overrides_knowledge_context(message):
    decision = AgentRouter().route(
        message,
        has_attachments=True,
        preferred_agent="knowledge",
    )

    assert decision.agent == "detection"
    assert decision.method == "attachment_intent"
    assert decision.confidence == 1.0


def test_ambiguous_image_attachment_is_not_captured_by_knowledge_context():
    decision = AgentRouter().route(
        "帮我看一下",
        has_attachments=True,
        preferred_agent="knowledge",
    )

    assert decision.agent == "detection"
    assert decision.method == "attachment"


def test_detection_attachment_overrides_knowledge_embedding(monkeypatch):
    monkeypatch.setattr(
        AgentRouter,
        "_embedding_route",
        lambda self, message: RouteDecision(
            "knowledge", "embedding", 0.82, "test semantic candidate"
        ),
    )

    decision = AgentRouter().route("检测下面的商品", has_attachments=True)

    assert decision.agent == "detection"
    assert decision.method == "attachment_intent"


def test_dataset_field_reply_keeps_conversation_context():
    decision = AgentRouter().route(
        "商品名称可乐，类别英文名 cola，价格 3.5 元",
        preferred_agent="dataset",
    )

    assert decision.agent == "dataset"
    assert decision.method == "conversation_context"


def test_explicit_price_change_overrides_dataset_conversation():
    decision = AgentRouter().route(
        "把数据集 1 中商品 ID 1 的价格改为 4 元",
        preferred_agent="dataset",
    )

    assert decision.agent == "catalog"
    assert decision.method == "explicit_intent"


def test_explicit_training_start_overrides_dataset_conversation():
    decision = AgentRouter().route(
        "使用数据集 2 启动训练",
        preferred_agent="dataset",
    )

    assert decision.agent == "training"
    assert decision.method == "explicit_intent"


def test_dataset_sample_edit_overrides_training_keywords_in_dataset_context():
    decision = AgentRouter().route(
        "我现在要向这个新的模型中添加一个新的商品的训练集",
        preferred_agent="dataset",
    )

    assert decision.agent == "dataset"
    assert decision.method == "explicit_intent"


def test_dataset_sample_edit_with_version_context_routes_to_dataset():
    decision = AgentRouter().route("向新派生版本添加一个新商品的训练集")

    assert decision.agent == "dataset"
    assert decision.method == "explicit_intent"


def test_dataset_creation_overrides_knowledge_embedding(monkeypatch):
    monkeypatch.setattr(
        AgentRouter,
        "_embedding_route",
        lambda self, message: RouteDecision(
            "knowledge", "embedding", 0.79, "test semantic candidate"
        ),
    )

    decision = AgentRouter().route("帮我创建新的数据集")

    assert decision.agent == "dataset"
    assert decision.method == "explicit_intent"


def test_named_dataset_product_addition_overrides_stale_training_context():
    decision = AgentRouter().route(
        "我现在要向 mutation-smoke-v2 中添加新的商品",
        preferred_agent="training",
        active_workflow_agent="training",
    )

    assert decision.agent == "dataset"
    assert decision.method == "explicit_intent"


def test_dataset_sample_attachment_overrides_stale_training_context():
    decision = AgentRouter().route(
        "添加新的商品训练图",
        has_attachments=True,
        preferred_agent="training",
    )

    assert decision.agent == "dataset"
    assert decision.method == "explicit_intent"


def test_embedding_is_consulted_but_cannot_override_dataset_edit(monkeypatch):
    observed = []
    semantic = RouteDecision("training", "embedding", 0.91, "test semantic candidate")
    monkeypatch.setattr(
        AgentRouter,
        "_embedding_route",
        lambda self, message: observed.append(message) or semantic,
    )

    decision = AgentRouter().route("向 mutation-smoke-v2 中添加新的商品")

    assert observed == ["向 mutation-smoke-v2 中添加新的商品"]
    assert decision.agent == "dataset"
    assert decision.method == "explicit_intent"


def test_embedding_is_primary_when_no_strong_intent(monkeypatch):
    semantic = RouteDecision("knowledge", "embedding", 0.81, "test semantic candidate")
    monkeypatch.setattr(AgentRouter, "_embedding_route", lambda self, message: semantic)

    assert AgentRouter().route("帮我梳理一下最近的经营资料") == semantic


def test_embedding_only_mode_skips_all_deterministic_routing(monkeypatch):
    semantic = RouteDecision("catalog", "embedding", 0.88, "test semantic candidate")
    monkeypatch.setattr(settings, "AGENT_ROUTING_MODE", "embedding_only")
    monkeypatch.setattr(AgentRouter, "_embedding_route", lambda self, message: semantic)

    decision = AgentRouter().route(
        "请检测这张图片并添加一个新商品",
        has_attachments=True,
        preferred_agent="dataset",
        active_workflow_agent="dataset",
    )

    assert decision == semantic


def test_embedding_only_mode_safely_falls_back_when_embedding_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_ROUTING_MODE", "embedding_only")
    monkeypatch.setattr(AgentRouter, "_embedding_route", lambda self, message: None)

    decision = AgentRouter().route("请检测这张图片", has_attachments=True)

    assert decision.agent == "knowledge"
    assert decision.method == "embedding_unavailable"


@pytest.mark.parametrize("message", ["你是什么工作的？", "什么是 loss？"])
def test_general_explanations_override_stale_domain_context(message):
    decision = AgentRouter().route(
        message,
        preferred_agent="training",
        active_workflow_agent="dataset",
    )

    assert decision.agent == "knowledge"
    assert decision.method == "general_knowledge"


def test_general_explanation_still_consults_embedding(monkeypatch):
    observed = []
    monkeypatch.setattr(
        AgentRouter,
        "_embedding_route",
        lambda self, message: observed.append(message)
        or RouteDecision("training", "embedding", 0.9, "test semantic candidate"),
    )

    decision = AgentRouter().route("什么是 loss？", preferred_agent="training")

    assert observed == ["什么是 loss？"]
    assert decision.agent == "knowledge"
    assert decision.method == "general_knowledge"


@pytest.mark.parametrize(
    ("message", "semantic_agent"),
    [
        ("Training agent 的主要职责是什么？", "training"),
        ("Catalog agent 的职责是什么？", "catalog"),
    ],
)
def test_agent_capability_questions_override_domain_embedding(
    monkeypatch, message, semantic_agent
):
    monkeypatch.setattr(
        AgentRouter,
        "_embedding_route",
        lambda self, text: RouteDecision(
            semantic_agent, "embedding", 0.91, "test semantic candidate"
        ),
    )

    decision = AgentRouter().route(message)

    assert decision.agent == "knowledge"
    assert decision.method == "general_knowledge"


def test_actual_training_status_stays_with_training_agent():
    decision = AgentRouter().route("查看这次训练任务的 loss 曲线")

    assert decision.agent == "training"
    assert decision.method == "explicit_intent"


def test_ambiguous_message_uses_embedding_route(monkeypatch):
    expected = RouteDecision("dataset", "embedding", 0.83, "test")
    monkeypatch.setattr(AgentRouter, "_embedding_route", lambda self, message: expected)

    assert AgentRouter().route("帮我处理一下新一批资料") == expected


def test_ambiguous_message_falls_back_to_knowledge(monkeypatch):
    monkeypatch.setattr(AgentRouter, "_embedding_route", lambda self, message: None)

    decision = AgentRouter().route("你好")

    assert decision.agent == "knowledge"
    assert decision.method == "fallback"
