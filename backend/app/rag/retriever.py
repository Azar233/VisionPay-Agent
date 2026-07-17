"""Shared retrieval for knowledge documents and operational fault cases."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.embeddings import DashScopeEmbeddingClient
from app.rag.chunker import TokenChunker
from app.vectorstore import ChromaStore


class KnowledgeRetriever:
    KNOWLEDGE_COLLECTION = "visionpay_knowledge"
    FAULT_COLLECTION = "visionpay_fault_cases"

    def __init__(self, collection_name: str | None = None) -> None:
        self.embedding = DashScopeEmbeddingClient()
        self.store = ChromaStore(collection_name or self.KNOWLEDGE_COLLECTION)

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.store.count == 0:
            return []
        where = {"domain": domain} if domain else None
        return self.store.query(
            embedding=self.embedding.embed_query(query),
            top_k=top_k or settings.RAG_TOP_K,
            where=where,
        )

    def index_directory(self, root: Path) -> dict[str, int]:
        chunker = TokenChunker()
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []
        files = sorted(
            [*root.rglob("*.md"), *root.rglob("*.txt")]
        ) if root.exists() else []
        for path in files:
            relative = path.relative_to(root).as_posix()
            domain = relative.split("/", 1)[0] if "/" in relative else "general"
            for index, chunk in enumerate(chunker.split(path.read_text(encoding="utf-8"))):
                digest = hashlib.sha256(
                    f"{relative}:{index}:{chunk.content}".encode("utf-8")
                ).hexdigest()
                ids.append(digest)
                documents.append(chunk.content)
                metadatas.append(
                    {
                        "source": relative,
                        "domain": domain,
                        "kind": "knowledge_document",
                        "chunk_index": index,
                        "token_start": chunk.token_start,
                        "token_end": chunk.token_end,
                    }
                )
        vectors = self.embedding.embed_documents(documents) if documents else []
        existing_ids = {
            item["id"]
            for item in self.store.list_items()
            if item["metadata"].get("kind") == "knowledge_document"
            or (
                self.store.collection.name == self.KNOWLEDGE_COLLECTION
                and item["metadata"].get("source")
                and not item["metadata"].get("kind")
            )
        }
        current_ids = set(ids)

        # Write the complete new snapshot first. If Embedding or upsert fails, the
        # previous searchable snapshot remains intact. Content-addressed ids make
        # unchanged chunks idempotent and changed chunks distinct.
        self.store.upsert(
            ids=ids,
            documents=documents,
            embeddings=vectors,
            metadatas=metadatas,
        )
        stale_ids = sorted(existing_ids - current_ids)
        if stale_ids:
            self.store.delete(ids=stale_ids)
        return {
            "files": len(files),
            "chunks": len(documents),
            "deleted_chunks": len(stale_ids),
            "total": self.store.count,
        }
