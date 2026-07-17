"""Normalize token usage metadata emitted by OpenAI-compatible chat models."""

from __future__ import annotations

from typing import Any


def usage_metadata(chunk: Any) -> dict[str, int] | None:
    usage = getattr(chunk, "usage_metadata", None) or {}
    if not usage:
        response = getattr(chunk, "response_metadata", None) or {}
        usage = response.get("token_usage") or response.get("usage") or {}
    if not isinstance(usage, dict):
        return None
    normalized = {
        "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
        "output_tokens": usage.get("output_tokens", usage.get("completion_tokens")),
        "total_tokens": usage.get("total_tokens"),
    }
    if (
        normalized["total_tokens"] is None
        and isinstance(normalized["input_tokens"], int)
        and isinstance(normalized["output_tokens"], int)
    ):
        normalized["total_tokens"] = (
            normalized["input_tokens"] + normalized["output_tokens"]
        )
    result = {
        key: int(value)
        for key, value in normalized.items()
        if isinstance(value, int)
    }
    return result or None
