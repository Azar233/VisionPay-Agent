"""Shared retrieval for knowledge documents and operational fault cases."""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.embeddings import DashScopeEmbeddingClient
from app.rag.chunker import TokenChunker
from app.vectorstore import ChromaStore
from app.rag.query_rewriter import retrieval_query_rewriter


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
        min_similarity: float | None = None,
    ) -> list[dict[str, Any]]:
        if self.store.count == 0:
            return []
        limit = max(1, int(top_k or settings.RAG_TOP_K))
        candidate_limit = limit * max(1, int(settings.RAG_CANDIDATE_MULTIPLIER))
        where = {"domain": domain} if domain else None
        candidates = self.store.query(
            embedding=self.embedding.embed_query(query),
            top_k=candidate_limit,
            where=where,
        )
        threshold = max(
            float(settings.RAG_MIN_SIMILARITY),
            float(settings.RAG_MIN_SIMILARITY if min_similarity is None else min_similarity),
        )
        filtered = [
            item for item in candidates if float(item.get("similarity", -1.0)) >= threshold
        ]
        return self._deduplicate(filtered, limit=limit)

    @staticmethod
    def _normalized_content(value: str) -> str:
        return re.sub(r"\s+", "", str(value or "")).lower()

    @staticmethod
    def _source_key(item: dict[str, Any]) -> str:
        metadata = item.get("metadata") or {}
        source = str(metadata.get("source") or "")
        if source in {"confirmed_fault_case", ""}:
            return f"{source}:{metadata.get('title') or item.get('id')}"
        return source

    def _deduplicate(
        self, candidates: list[dict[str, Any]], *, limit: int
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        source_counts: dict[str, int] = {}
        content_threshold = float(settings.RAG_DEDUP_SIMILARITY)
        adjacent_threshold = float(settings.RAG_ADJACENT_DEDUP_SIMILARITY)
        source_limit = max(1, int(settings.RAG_MAX_CHUNKS_PER_SOURCE))

        for candidate in candidates:
            source = self._source_key(candidate)
            if source and source_counts.get(source, 0) >= source_limit:
                continue
            metadata = candidate.get("metadata") or {}
            chunk_index = metadata.get("chunk_index")
            normalized = self._normalized_content(candidate.get("content", ""))
            duplicate = False
            for existing in selected:
                existing_metadata = existing.get("metadata") or {}
                existing_source = self._source_key(existing)
                existing_index = existing_metadata.get("chunk_index")
                if (
                    source
                    and source == existing_source
                    and isinstance(chunk_index, int)
                    and isinstance(existing_index, int)
                    and abs(chunk_index - existing_index) <= 1
                ):
                    existing_content = self._normalized_content(existing.get("content", ""))
                    if normalized and existing_content and SequenceMatcher(
                        None, normalized, existing_content
                    ).ratio() >= adjacent_threshold:
                        duplicate = True
                        break
                existing_content = self._normalized_content(existing.get("content", ""))
                if normalized and existing_content and SequenceMatcher(
                    None, normalized, existing_content
                ).ratio() >= content_threshold:
                    duplicate = True
                    break
            if duplicate:
                continue
            candidate = dict(candidate)
            candidate["rank"] = len(selected) + 1
            selected.append(candidate)
            if source:
                source_counts[source] = source_counts.get(source, 0) + 1
            if len(selected) >= limit:
                break
        return selected

    def retrieve(
        self,
        query: str,
        *,
        context_state: dict[str, Any] | None = None,
        top_k: int | None = None,
        domain: str | None = None,
        min_similarity: float | None = None,
    ) -> dict[str, Any]:
        rewritten = retrieval_query_rewriter.rewrite(
            query,
            context_state=context_state,
            domain=domain,
        )
        items = self.search(
            rewritten.rewritten_query,
            top_k=top_k,
            domain=rewritten.domain,
            min_similarity=min_similarity,
        )
        return {**rewritten.as_dict(), "items": items}

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
