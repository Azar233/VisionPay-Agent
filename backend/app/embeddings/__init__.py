"""Embedding providers used by routing, RAG, fault search and memory."""

from app.embeddings.dashscope import DashScopeEmbeddingClient, EmbeddingConfigurationError

__all__ = ["DashScopeEmbeddingClient", "EmbeddingConfigurationError"]
