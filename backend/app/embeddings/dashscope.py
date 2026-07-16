"""DashScope text-embedding-v4 through its OpenAI-compatible endpoint."""

from __future__ import annotations

from collections.abc import Iterable

from app.config.settings import settings


class EmbeddingConfigurationError(RuntimeError):
    """Raised when the configured embedding provider cannot be used."""


class DashScopeEmbeddingClient:
    """Small, dependency-light embedding client with deterministic batching."""

    def __init__(self) -> None:
        if not settings.DASHSCOPE_API_KEY:
            raise EmbeddingConfigurationError(
                "DASHSCOPE_API_KEY 未配置；setx 后请重新打开终端或重启后端"
            )
        from openai import OpenAI

        self.model = settings.EMBEDDING_MODEL
        self.dimensions = int(settings.EMBEDDING_DIMENSIONS)
        self.batch_size = max(1, int(settings.EMBEDDING_BATCH_SIZE))
        self.client = OpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.DASHSCOPE_BASE_URL,
        )

    @staticmethod
    def _normalize(texts: Iterable[str]) -> list[str]:
        normalized = [str(item or "").strip() for item in texts]
        if not normalized or any(not item for item in normalized):
            raise ValueError("Embedding 输入不能为空")
        return normalized

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        values = self._normalize(texts)
        vectors: list[list[float]] = []
        for offset in range(0, len(values), self.batch_size):
            response = self.client.embeddings.create(
                model=self.model,
                input=values[offset : offset + self.batch_size],
                dimensions=self.dimensions,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            for item in ordered:
                vector = list(item.embedding)
                if len(vector) != self.dimensions:
                    raise RuntimeError(
                        f"Embedding 维度异常：期望 {self.dimensions}，实际 {len(vector)}"
                    )
                vectors.append(vector)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
