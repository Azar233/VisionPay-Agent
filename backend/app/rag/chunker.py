"""Token-aware document chunking using the configured 400/60 policy."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import settings


@dataclass(frozen=True)
class TextChunk:
    content: str
    token_start: int
    token_end: int


class TokenChunker:
    def __init__(self, chunk_size: int | None = None, overlap: int | None = None) -> None:
        import tiktoken

        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.chunk_size = int(chunk_size or settings.RAG_CHUNK_TOKENS)
        self.overlap = int(
            settings.RAG_CHUNK_OVERLAP_TOKENS if overlap is None else overlap
        )
        if self.chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if self.overlap < 0 or self.overlap >= self.chunk_size:
            raise ValueError("overlap 必须大于等于 0 且小于 chunk_size")

    def split(self, text: str) -> list[TextChunk]:
        content = str(text or "").strip()
        if not content:
            return []
        tokens = self.encoding.encode(content)
        step = self.chunk_size - self.overlap
        chunks: list[TextChunk] = []
        for start in range(0, len(tokens), step):
            end = min(start + self.chunk_size, len(tokens))
            decoded = self.encoding.decode(tokens[start:end]).strip()
            if decoded:
                chunks.append(TextChunk(decoded, start, end))
            if end >= len(tokens):
                break
        return chunks
