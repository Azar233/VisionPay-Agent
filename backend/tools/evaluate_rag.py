"""Run the VisionPay offline RAG retrieval benchmark against local indexes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.rag.evaluation import (  # noqa: E402
    evaluate_retrieval_cases,
    load_evaluation_suite,
    threshold_failures,
)
from app.rag.retriever import KnowledgeRetriever  # noqa: E402


DEFAULT_CASES = BACKEND_ROOT / "evaluation" / "rag_cases.json"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估本地 RAG 索引的检索质量")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json", action="store_true", help="只输出 JSON 结果")
    parser.add_argument(
        "--enforce-thresholds",
        action="store_true",
        help="指标未达到评测集 thresholds 时返回非零退出码",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    suite = load_evaluation_suite(args.cases.resolve())
    retrievers = {
        "knowledge": KnowledgeRetriever(),
        "fault_cases": KnowledgeRetriever(KnowledgeRetriever.FAULT_COLLECTION),
    }

    def retrieve(case: dict) -> dict:
        return retrievers[case.get("collection", "knowledge")].retrieve(
            case["query"],
            context_state=case.get("context_state"),
        )

    report = evaluate_retrieval_cases(suite["cases"], retrieve)
    failures = threshold_failures(report["metrics"], suite.get("thresholds") or {})
    report["threshold_failures"] = failures

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        metrics = report["metrics"]
        print(f"RAG 评测完成：{metrics['case_count']} 个用例")
        print(
            "来源命中率={source_hit_rate:.2%}  MRR={mrr:.4f}  "
            "领域准确率={domain_accuracy:.2%}  关键词覆盖率={keyword_coverage_rate:.2%}  "
            "无结果率={no_result_rate:.2%}".format(**metrics)
        )
        for detail in report["details"]:
            state = "PASS" if detail["source_hit"] else "MISS"
            print(
                f"[{state}] {detail['id']} rank={detail['first_relevant_rank']} "
                f"sources={detail['actual_sources']}"
            )
        if failures:
            print("未达到阈值：" + "; ".join(failures))

    return 1 if args.enforce_thresholds and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
