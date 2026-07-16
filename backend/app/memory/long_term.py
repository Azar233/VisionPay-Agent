"""User-scoped long-term memory stored in Chroma."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config.settings import settings
from app.embeddings import DashScopeEmbeddingClient
from app.vectorstore import ChromaStore


class LongTermMemoryStore:
    COLLECTION = "visionpay_long_term_memory"

    def __init__(self) -> None:
        self.embedding = DashScopeEmbeddingClient()
        self.store = ChromaStore(self.COLLECTION)

    def remember(
        self,
        *,
        user_id: int,
        content: str,
        category: str = "preference",
        session_uuid: str | None = None,
    ) -> dict[str, Any]:
        value = str(content or "").strip()
        if not value:
            raise ValueError("长期记忆内容不能为空")
        memory_id = uuid4().hex
        metadata = {
            "user_id": int(user_id),
            "category": category or "preference",
            "session_uuid": session_uuid or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.store.upsert(
            ids=[memory_id],
            documents=[value],
            embeddings=[self.embedding.embed_query(value)],
            metadatas=[metadata],
        )
        return {"id": memory_id, "content": value, "metadata": metadata}

    def recall(
        self,
        *,
        user_id: int,
        query: str,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        if self.store.count == 0:
            return []
        return self.store.query(
            embedding=self.embedding.embed_query(query),
            top_k=top_k or settings.LONG_TERM_MEMORY_TOP_K,
            where={"user_id": int(user_id)},
        )
