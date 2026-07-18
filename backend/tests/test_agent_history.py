from app.agent.history import build_chat_history


def test_assistant_messages_are_labeled_with_producing_agent():
    history = [
        {"role": "user", "content": "今天检测了多少任务"},
        {"role": "assistant", "content": "我这边只负责训练相关的查询", "agent": "training"},
        {"role": "assistant", "content": "没有标注的旧消息"},
    ]

    messages = build_chat_history(history)

    assert messages[1].content == "[training Agent 的回复]\n我这边只负责训练相关的查询"
    # 没有 agent 标记的历史消息保持原样，兼容旧数据。
    assert messages[2].content == "没有标注的旧消息"


def test_user_and_system_messages_are_not_relabeled():
    history = [
        {"role": "system", "content": "结构化会话状态"},
        {"role": "user", "content": "你好", "agent": ""},
    ]

    messages = build_chat_history(history)

    assert messages[0].content == "结构化会话状态"
    assert messages[1].content == "你好"


def test_empty_history_returns_empty_list():
    assert build_chat_history(None) == []
    assert build_chat_history([]) == []
