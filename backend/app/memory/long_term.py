"""User-scoped, deduplicated long-term memory stored in Chroma."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config.settings import settings
from app.embeddings import DashScopeEmbeddingClient
from app.vectorstore import ChromaStore


class MemoryNotFoundError(ValueError):
    pass


class SensitiveMemoryError(ValueError):
    pass


class InvalidMemoryCategoryError(ValueError):
    pass


class LongTermMemoryStore:
    COLLECTION = "visionpay_long_term_memory"
    CATEGORIES = {"preference", "stable_fact", "output_format", "workflow"}
    _SENSITIVE_PATTERNS = (
        re.compile(
            r"(?i)(?:password|passwd|pwd|secret|api[-_ ]?key|access[-_ ]?key|token|authorization)"
        ),
        re.compile(r"(?:密码|口令|密钥|令牌|访问凭证|授权码)"),
        re.compile(r"(?i)\bsk-[a-z0-9._-]{10,}\b"),
        re.compile(r"(?i)\bbearer\s+\S+"),
        re.compile(r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b"),
        re.compile(r"(?:价格|单价)\s*(?:是|为|=|:|：)?\s*[¥￥]?\d+(?:\.\d+)?"),
        re.compile(r"(?:当前|本次|临时).{0,12}(?:任务状态|训练进度|确认状态)"),
    )

    def __init__(self) -> None:
        self.embedding = None
        self.store = ChromaStore(self.COLLECTION)

    def _embed_query(self, text: str) -> list[float]:
        if self.embedding is None:
            self.embedding = DashScopeEmbeddingClient()
        return self.embedding.embed_query(text)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalized(content: str) -> str:
        return re.sub(r"[\s，。！？、,.!?;；:：]+", "", content).lower()

    @classmethod
    def _fingerprint(cls, content: str) -> str:
        return hashlib.sha256(cls._normalized(content).encode("utf-8")).hexdigest()

    @classmethod
    def _category(cls, category: str | None) -> str:
        value = str(category or "preference").strip().lower()
        if value not in cls.CATEGORIES:
            raise InvalidMemoryCategoryError(
                f"长期记忆类别必须是：{', '.join(sorted(cls.CATEGORIES))}"
            )
        return value

    @classmethod
    def _validate_content(cls, content: str) -> str:
        value = str(content or "").strip()
        if not value:
            raise ValueError("长期记忆内容不能为空")
        if len(value) > 4000:
            raise ValueError("长期记忆内容不能超过 4000 个字符")
        if any(pattern.search(value) for pattern in cls._SENSITIVE_PATTERNS):
            raise SensitiveMemoryError(
                "长期记忆拒绝保存密码、Token、密钥、实时价格或临时任务状态"
            )
        return value

    @staticmethod
    def _where(user_id: int, category: str | None = None) -> dict[str, Any]:
        if not category:
            return {"user_id": int(user_id)}
        return {
            "$and": [
                {"user_id": {"$eq": int(user_id)}},
                {"category": {"$eq": category}},
            ]
        }

    @staticmethod
    def _serialize(item: dict[str, Any], *, action: str | None = None) -> dict[str, Any]:
        result = {
            "id": item["id"],
            "content": item.get("content") or "",
            "metadata": item.get("metadata") or {},
        }
        if action:
            result["action"] = action
        if "similarity" in item:
            result["similarity"] = item["similarity"]
            result["distance"] = item.get("distance")
        return result

    def _similar(
        self,
        *,
        user_id: int,
        category: str,
        embedding: list[float],
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        if self.store.count == 0:
            return []
        return self.store.query(
            embedding=embedding,
            top_k=min(max(1, top_k), self.store.count),
            where=self._where(user_id, category),
        )

    def remember(
        self,
        *,
        user_id: int,
        content: str,
        category: str = "preference",
        session_uuid: str | None = None,
    ) -> dict[str, Any]:
        value = self._validate_content(content)
        normalized_category = self._category(category)
        vector = self._embed_query(value)
        similar = self._similar(
            user_id=user_id,
            category=normalized_category,
            embedding=vector,
        )
        fingerprint = self._fingerprint(value)
        exact = next(
            (
                item
                for item in similar
                if (item.get("metadata") or {}).get("content_fingerprint") == fingerprint
                or self._normalized(item.get("content") or "") == self._normalized(value)
            ),
            None,
        )
        if exact:
            return self._serialize(exact, action="deduplicated")

        threshold = float(settings.LONG_TERM_MEMORY_DEDUPE_SIMILARITY)
        replacement = next(
            (item for item in similar if float(item.get("similarity", -1.0)) >= threshold),
            None,
        )
        now = self._now()
        if replacement:
            memory_id = replacement["id"]
            previous = replacement.get("metadata") or {}
            metadata = {
                **previous,
                "user_id": int(user_id),
                "category": normalized_category,
                "session_uuid": session_uuid or previous.get("session_uuid") or "",
                "created_at": previous.get("created_at") or now,
                "updated_at": now,
                "revision": int(previous.get("revision") or 1) + 1,
                "content_fingerprint": fingerprint,
            }
            action = "updated"
        else:
            memory_id = uuid4().hex
            metadata = {
                "user_id": int(user_id),
                "category": normalized_category,
                "session_uuid": session_uuid or "",
                "created_at": now,
                "updated_at": now,
                "revision": 1,
                "content_fingerprint": fingerprint,
            }
            action = "created"
        self.store.upsert(
            ids=[memory_id],
            documents=[value],
            embeddings=[vector],
            metadatas=[metadata],
        )
        return {
            "id": memory_id,
            "content": value,
            "metadata": metadata,
            "action": action,
        }

    def list(
        self,
        *,
        user_id: int,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        normalized_category = self._category(category) if category else None
        items = self.store.list_items(where=self._where(user_id, normalized_category))
        items.sort(
            key=lambda item: str(
                (item.get("metadata") or {}).get("updated_at")
                or (item.get("metadata") or {}).get("created_at")
                or ""
            ),
            reverse=True,
        )
        start = max(0, int(offset))
        end = start + max(1, int(limit))
        return {
            "total": len(items),
            "items": [self._serialize(item) for item in items[start:end]],
        }

    def get(self, *, user_id: int, memory_id: str) -> dict[str, Any]:
        items = self.store.list_items(
            ids=[memory_id], where=self._where(user_id)
        )
        if not items:
            raise MemoryNotFoundError("长期记忆不存在或无权访问")
        return self._serialize(items[0])

    def update(
        self,
        *,
        user_id: int,
        memory_id: str,
        content: str,
        category: str | None = None,
        session_uuid: str | None = None,
    ) -> dict[str, Any]:
        current = self.get(user_id=user_id, memory_id=memory_id)
        value = self._validate_content(content)
        previous = current["metadata"]
        normalized_category = self._category(category or previous.get("category"))
        vector = self._embed_query(value)
        similar = self._similar(
            user_id=user_id,
            category=normalized_category,
            embedding=vector,
        )
        merged_ids = [
            item["id"]
            for item in similar
            if item["id"] != memory_id
            and float(item.get("similarity", -1.0))
            >= float(settings.LONG_TERM_MEMORY_DEDUPE_SIMILARITY)
        ]
        if merged_ids:
            self.store.delete(ids=merged_ids)
        now = self._now()
        metadata = {
            **previous,
            "user_id": int(user_id),
            "category": normalized_category,
            "session_uuid": session_uuid or previous.get("session_uuid") or "",
            "created_at": previous.get("created_at") or now,
            "updated_at": now,
            "revision": int(previous.get("revision") or 1) + 1,
            "content_fingerprint": self._fingerprint(value),
        }
        self.store.upsert(
            ids=[memory_id],
            documents=[value],
            embeddings=[vector],
            metadatas=[metadata],
        )
        return {
            "id": memory_id,
            "content": value,
            "metadata": metadata,
            "action": "updated",
            "merged_duplicate_ids": merged_ids,
        }

    def delete(self, *, user_id: int, memory_id: str) -> dict[str, Any]:
        current = self.get(user_id=user_id, memory_id=memory_id)
        self.store.delete(ids=[memory_id])
        return {"id": memory_id, "deleted": True, "content": current["content"]}

    def recall(
        self,
        *,
        user_id: int,
        query: str,
        top_k: int | None = None,
        category: str | None = None,
        min_similarity: float | None = None,
    ) -> list[dict[str, Any]]:
        if self.store.count == 0:
            return []
        normalized_category = self._category(category) if category else None
        limit = max(1, int(top_k or settings.LONG_TERM_MEMORY_TOP_K))
        candidates = self.store.query(
            embedding=self._embed_query(query),
            top_k=min(limit * 3, self.store.count),
            where=self._where(user_id, normalized_category),
        )
        threshold = max(
            float(settings.LONG_TERM_MEMORY_MIN_SIMILARITY),
            float(
                settings.LONG_TERM_MEMORY_MIN_SIMILARITY
                if min_similarity is None
                else min_similarity
            ),
        )
        selected = []
        fingerprints = set()
        for item in candidates:
            if float(item.get("similarity", -1.0)) < threshold:
                continue
            fingerprint = (item.get("metadata") or {}).get("content_fingerprint") or self._fingerprint(
                item.get("content") or ""
            )
            if fingerprint in fingerprints:
                continue
            fingerprints.add(fingerprint)
            selected.append(self._serialize(item))
            if len(selected) >= limit:
                break
        return selected
