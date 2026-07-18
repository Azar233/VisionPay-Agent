"""Deterministic grounding policy and structured source serialization."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Iterable


KNOWLEDGE_TOOL = "search_management_knowledge"
FAULT_TOOL = "search_fault_cases"

_LOW_INFORMATION_MESSAGES = {
    "你好",
    "您好",
    "嗨",
    "hi",
    "hello",
    "谢谢",
    "好的",
    "好",
    "知道了",
    "明白了",
}
_MEMORY_ACTION_CUES = (
    "记住",
    "记一下",
    "保存偏好",
    "保存到长期记忆",
    "忘记",
    "忘掉",
    "删除记忆",
    "修改记忆",
    "查看记忆",
    "列出记忆",
    "回忆我",
)
_FAULT_CUES = (
    "报错",
    "错误",
    "异常",
    "失败",
    "崩溃",
    "闪退",
    "无法",
    "不能输入",
    "页面运行出错",
    "未找到",
    "找不到",
    "覆盖",
    "401",
    "403",
    "404",
    "409",
    "422",
    "500",
    "min should not be greater than max",
)


def forced_retrieval_tools(message: str) -> tuple[str, ...]:
    """Return retrieval tools that must run before Knowledge Agent generation."""
    normalized = re.sub(r"[\s，。！？、,.!?]+", "", str(message or "")).lower()
    if not normalized or normalized in _LOW_INFORMATION_MESSAGES:
        return ()
    lowered = str(message or "").lower()
    if "knowledge.remember" in lowered or any(cue in lowered for cue in _MEMORY_ACTION_CUES):
        return ()
    if any(cue in lowered for cue in _FAULT_CUES):
        return (FAULT_TOOL, KNOWLEDGE_TOOL)
    return (KNOWLEDGE_TOOL,)


def _source_title(source: str, metadata: dict[str, Any]) -> str:
    explicit = str(metadata.get("title") or "").strip()
    if explicit:
        return explicit
    name = PurePosixPath(source).stem if source else "参考知识"
    return name.replace("_", " ").replace("-", " ").strip() or "参考知识"


def structured_retrieval_result(
    *,
    tool_name: str,
    result: Any,
    excerpt_chars: int = 320,
) -> dict[str, Any]:
    """Convert one retriever response into a stable frontend/audit contract."""
    collection = "fault_cases" if tool_name == FAULT_TOOL else "knowledge"
    payload = result if isinstance(result, dict) else {}
    sources: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        source = str(metadata.get("source") or item.get("id") or "unknown")
        content = str(item.get("content") or "").strip()
        excerpt = content[:excerpt_chars] + ("…" if len(content) > excerpt_chars else "")
        sources.append(
            {
                "id": str(item.get("id") or source),
                "collection": collection,
                "source": source,
                "title": _source_title(source, metadata),
                "domain": str(metadata.get("domain") or payload.get("domain") or "general"),
                "similarity": round(float(item.get("similarity") or 0.0), 4),
                "rank": int(item.get("rank") or len(sources) + 1),
                "excerpt": excerpt,
            }
        )
    return {
        "tool": tool_name,
        "collection": collection,
        "original_query": str(payload.get("original_query") or ""),
        "rewritten_query": str(payload.get("rewritten_query") or payload.get("original_query") or ""),
        "domain": payload.get("domain"),
        "purpose": payload.get("purpose"),
        "context_used": bool(payload.get("context_used")),
        "error": str(payload.get("error") or "") or None,
        "sources": sources,
    }


def merge_retrieval_results(
    query: str, retrievals: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    items = list(retrievals)
    sources: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for retrieval in items:
        for source in retrieval.get("sources") or []:
            key = (str(source.get("collection") or ""), str(source.get("id") or ""))
            if key in seen:
                continue
            seen.add(key)
            sources.append(source)
    return {
        "query": str(query or ""),
        "forced": True,
        "has_knowledge": bool(sources),
        "sources": sources,
        "retrievals": [
            {key: value for key, value in item.items() if key != "sources"}
            for item in items
        ],
    }
