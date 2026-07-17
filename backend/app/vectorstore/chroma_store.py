"""Persistent Chroma collections with caller-provided DashScope embeddings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config.settings import settings


class VectorStoreConfigurationError(RuntimeError):
    """Raised when Chroma is not installed or configured correctly."""


def _metadata_value(value: Any) -> str | int | float | bool:
    if isinstance(value, (str, int, float, bool)):
        return value
    if value is None:
        return ""
    return str(value)


class ChromaStore:
    """Thin wrapper that keeps embedding calls outside Chroma."""

    def __init__(self, collection_name: str) -> None:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - depends on optional runtime package
            raise VectorStoreConfigurationError(
                "Chroma 未安装，请在 agentenv 中安装 requirements.txt"
            ) from exc

        root = Path(settings.CHROMA_PERSIST_DIR).expanduser()
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root
        self.client = chromadb.PersistentClient(path=str(root))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": settings.CHROMA_DISTANCE},
        )

    @property
    def count(self) -> int:
        return int(self.collection.count())

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not (len(ids) == len(documents) == len(embeddings) == len(metadatas)):
            raise ValueError("Chroma upsert 各字段数量必须一致")
        if not ids:
            return
        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=[
                {key: _metadata_value(value) for key, value in item.items()}
                for item in metadatas
            ],
        )

    def query(
        self,
        *,
        embedding: list[float],
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if self.count == 0:
            return []
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=max(1, min(int(top_k), self.count)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        items = []
        for item_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances
        ):
            distance_value = float(distance)
            items.append(
                {
                    "id": item_id,
                    "content": document,
                    "metadata": metadata or {},
                    "distance": distance_value,
                    "similarity": max(-1.0, min(1.0, 1.0 - distance_value)),
                }
            )
        return items

    def list_items(
        self,
        *,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return stored ids/documents/metadata without loading embeddings."""
        kwargs: dict[str, Any] = {"include": ["documents", "metadatas"]}
        if ids:
            kwargs["ids"] = ids
        if where:
            kwargs["where"] = where
        if limit is not None:
            kwargs["limit"] = max(1, int(limit))
        if offset is not None:
            kwargs["offset"] = max(0, int(offset))
        result = self.collection.get(**kwargs)
        return [
            {"id": item_id, "content": document or "", "metadata": metadata or {}}
            for item_id, document, metadata in zip(
                result.get("ids") or [],
                result.get("documents") or [],
                result.get("metadatas") or [],
            )
        ]

    def delete(self, *, ids: list[str] | None = None, where: dict | None = None) -> None:
        if ids or where:
            self.collection.delete(ids=ids, where=where)
