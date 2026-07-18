from pathlib import Path

from app.rag.evaluation import (
    evaluate_retrieval_cases,
    load_evaluation_suite,
    threshold_failures,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_rag_evaluation_suite_references_existing_sources():
    suite = load_evaluation_suite(BACKEND_ROOT / "evaluation" / "rag_cases.json")

    assert len(suite["cases"]) >= 12
    for case in suite["cases"]:
        root = (
            BACKEND_ROOT / "fault_case_base"
            if case.get("collection") == "fault_cases"
            else BACKEND_ROOT / "knowledge_base"
        )
        assert any((root / source).is_file() for source in case["expected_sources"]), case["id"]


def test_rag_evaluation_metrics_are_deterministic():
    cases = [
        {
            "id": "hit-first",
            "query": "q1",
            "collection": "knowledge",
            "expected_domain": "dataset",
            "expected_sources": ["dataset/right.md"],
            "expected_keywords": ["冻结", "草稿"],
        },
        {
            "id": "hit-second",
            "query": "q2",
            "collection": "fault_cases",
            "expected_sources": ["fault/right.md"],
            "expected_keywords": ["401"],
        },
    ]
    outputs = {
        "hit-first": {
            "domain": "dataset",
            "rewritten_query": "rewritten q1",
            "items": [
                {
                    "content": "冻结草稿",
                    "metadata": {"source": "dataset/right.md"},
                }
            ],
        },
        "hit-second": {
            "domain": None,
            "rewritten_query": "q2",
            "items": [
                {"content": "other", "metadata": {"source": "fault/other.md"}},
                {"content": "401", "metadata": {"source": "fault/right.md"}},
            ],
        },
    }

    report = evaluate_retrieval_cases(cases, lambda case: outputs[case["id"]])

    assert report["metrics"] == {
        "case_count": 2,
        "source_hit_rate": 1.0,
        "mrr": 0.75,
        "domain_accuracy": 1.0,
        "keyword_coverage_rate": 1.0,
        "no_result_rate": 0.0,
    }
    assert threshold_failures(
        report["metrics"],
        {"minimum": {"mrr": 0.8}, "maximum": {"no_result_rate": 0.1}},
    ) == ["mrr=0.75 < 0.8"]
