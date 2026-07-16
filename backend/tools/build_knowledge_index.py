"""Build VisionPay Chroma indexes after DASHSCOPE_API_KEY is available."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.routing import AgentRouter  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.rag import KnowledgeRetriever  # noqa: E402


def main() -> int:
    if not settings.DASHSCOPE_API_KEY:
        print("DASHSCOPE_API_KEY 不可见。setx 后请重新打开终端，再激活 agentenv。")
        return 2
    root = BACKEND_ROOT / "knowledge_base"
    result = KnowledgeRetriever().index_directory(root)
    # A deliberately ambiguous message warms and seeds the vector route collection.
    decision = AgentRouter().route("请帮我处理一批新的经营资料")
    print(
        f"知识库构建完成: files={result['files']}, chunks={result['chunks']}, "
        f"total={result['total']}"
    )
    print(
        f"向量路由已初始化: agent={decision.agent}, method={decision.method}, "
        f"confidence={decision.confidence:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
