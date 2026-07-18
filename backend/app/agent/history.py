"""Helpers for building LangChain chat history with agent identity labels."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


def build_chat_history(items: list[dict[str, str]] | None) -> list:
    """Convert stored history dicts into LangChain messages.

    Assistant messages are prefixed with the producing agent's name so that a
    mid-conversation agent switch does not leak the previous agent's identity
    into the current one (the model would otherwise role-play whoever replied
    last).
    """
    messages = []
    for item in items or []:
        role = item.get("role")
        content = item.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            agent = str(item.get("agent") or "").strip()
            if agent:
                content = f"[{agent} Agent 的回复]\n{content}"
            messages.append(AIMessage(content=content))
        elif role == "system":
            messages.append(SystemMessage(content=content))
    return messages
