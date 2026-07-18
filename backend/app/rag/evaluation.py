"""Offline retrieval evaluation helpers with deterministic metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def load_evaluation_suite(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("RAG 评测集必须包含非空 cases 数组")
    identifiers = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("RAG 评测用例必须是对象")
        case_id = str(case.get("id") or "").strip()
        query = str(case.get("query") or "").strip()
        collection = str(case.get("collection") or "knowledge")
        expected_sources = case.get("expected_sources")
        if not case_id or not query:
            raise ValueError("每个 RAG 评测用例必须包含 id 和 query")
        if case_id in identifiers:
            raise ValueError(f"RAG 评测用例 ID 重复：{case_id}")
        if collection not in {"knowledge", "fault_cases"}:
            raise ValueError(f"RAG 评测集合无效：{collection}")
        if not isinstance(expected_sources, list) or not expected_sources:
            raise ValueError(f"RAG 评测用例缺少 expected_sources：{case_id}")
        identifiers.add(case_id)
    return payload


def evaluate_retrieval_cases(
    cases: list[dict[str, Any]],
    retrieve: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Run cases and calculate source hit, MRR, domain and content coverage."""
    details = []
    source_hits = 0
    reciprocal_rank_sum = 0.0
    domain_checks = 0
    domain_hits = 0
    keyword_checks = 0
    keyword_hits = 0
    no_result_count = 0

    for case in cases:
        result = retrieve(case)
        items = result.get("items") if isinstance(result, dict) else []
        items = items if isinstance(items, list) else []
        actual_sources = [
            str((item.get("metadata") or {}).get("source") or "")
            for item in items
            if isinstance(item, dict)
        ]
        expected_sources = {str(item) for item in case.get("expected_sources") or []}
        first_rank = next(
            (
                index + 1
                for index, source in enumerate(actual_sources)
                if source in expected_sources
            ),
            None,
        )
        source_hit = first_rank is not None
        if source_hit:
            source_hits += 1
            reciprocal_rank_sum += 1.0 / first_rank
        if not items:
            no_result_count += 1

        expected_domain = case.get("expected_domain")
        domain_hit = None
        if expected_domain:
            domain_checks += 1
            domain_hit = result.get("domain") == expected_domain
            domain_hits += int(domain_hit)

        content = "\n".join(str(item.get("content") or "") for item in items)
        expected_keywords = [str(item) for item in case.get("expected_keywords") or []]
        found_keywords = [keyword for keyword in expected_keywords if keyword in content]
        keyword_checks += len(expected_keywords)
        keyword_hits += len(found_keywords)

        details.append(
            {
                "id": case["id"],
                "query": case["query"],
                "collection": case.get("collection", "knowledge"),
                "rewritten_query": result.get("rewritten_query"),
                "domain": result.get("domain"),
                "source_hit": source_hit,
                "first_relevant_rank": first_rank,
                "domain_hit": domain_hit,
                "expected_sources": sorted(expected_sources),
                "actual_sources": actual_sources,
                "found_keywords": found_keywords,
                "missing_keywords": [
                    keyword for keyword in expected_keywords if keyword not in found_keywords
                ],
            }
        )

    total = len(cases)
    metrics = {
        "case_count": total,
        "source_hit_rate": round(source_hits / total, 4),
        "mrr": round(reciprocal_rank_sum / total, 4),
        "domain_accuracy": round(domain_hits / domain_checks, 4) if domain_checks else None,
        "keyword_coverage_rate": (
            round(keyword_hits / keyword_checks, 4) if keyword_checks else None
        ),
        "no_result_rate": round(no_result_count / total, 4),
    }
    return {"metrics": metrics, "details": details}


def threshold_failures(
    metrics: dict[str, Any], thresholds: dict[str, Any]
) -> list[str]:
    failures = []
    minimums = thresholds.get("minimum") or {}
    maximums = thresholds.get("maximum") or {}
    for name, expected in minimums.items():
        actual = metrics.get(name)
        if actual is None or float(actual) < float(expected):
            failures.append(f"{name}={actual} < {expected}")
    for name, expected in maximums.items():
        actual = metrics.get(name)
        if actual is None or float(actual) > float(expected):
            failures.append(f"{name}={actual} > {expected}")
    return failures
