"""Authenticated knowledge, fault-case and semantic-memory management APIs."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.config.settings import settings
from app.embeddings import DashScopeEmbeddingClient
from app.memory import LongTermMemoryStore
from app.rag import KnowledgeRetriever
from app.vectorstore import ChromaStore

router = APIRouter(prefix="/api/knowledge", tags=["管理知识库"])
BACKEND_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = BACKEND_ROOT / "knowledge_base"
FAULT_CASE_ROOT = BACKEND_ROOT / "fault_case_base"


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    domain: str | None = Field(None, max_length=50)
    top_k: int = Field(default=settings.RAG_TOP_K, ge=1, le=20)


class FaultCaseRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    symptom: str = Field(..., min_length=1, max_length=4000)
    resolution: str = Field(..., min_length=1, max_length=8000)
    domain: str = Field(default="general", min_length=1, max_length=50)


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=settings.LONG_TERM_MEMORY_TOP_K, ge=1, le=20)


@router.get("/status", summary="查看 Embedding 与 Chroma 配置状态")
def knowledge_status(current_user=Depends(get_current_user)):
    del current_user
    counts = {}
    error = None
    try:
        for name in (
            KnowledgeRetriever.KNOWLEDGE_COLLECTION,
            KnowledgeRetriever.FAULT_COLLECTION,
            LongTermMemoryStore.COLLECTION,
            "visionpay_agent_routes",
        ):
            counts[name] = ChromaStore(name).count
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    return {
        "embedding_configured": bool(settings.DASHSCOPE_API_KEY),
        "model": settings.EMBEDDING_MODEL,
        "dimensions": settings.EMBEDDING_DIMENSIONS,
        "distance": settings.CHROMA_DISTANCE,
        "chunk_tokens": settings.RAG_CHUNK_TOKENS,
        "chunk_overlap_tokens": settings.RAG_CHUNK_OVERLAP_TOKENS,
        "top_k": settings.RAG_TOP_K,
        "collections": counts,
        "error": error,
    }


@router.post("/build", summary="构建或增量更新项目知识库")
def build_knowledge(current_user=Depends(get_current_user)):
    del current_user
    try:
        return {
            "knowledge": KnowledgeRetriever().index_directory(KNOWLEDGE_ROOT),
            "fault_cases": KnowledgeRetriever(
                KnowledgeRetriever.FAULT_COLLECTION
            ).index_directory(FAULT_CASE_ROOT),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"知识库构建失败：{exc}") from exc


@router.post("/search", summary="检索项目知识库")
def search_knowledge(
    payload: KnowledgeSearchRequest,
    current_user=Depends(get_current_user),
):
    del current_user
    try:
        results = KnowledgeRetriever().search(
            payload.query,
            top_k=payload.top_k,
            domain=payload.domain,
        )
        return {"query": payload.query, "items": results}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"知识检索失败：{exc}") from exc


@router.post("/fault-cases", summary="写入已确认的故障案例")
def add_fault_case(
    payload: FaultCaseRequest,
    current_user=Depends(get_current_user),
):
    content = (
        f"故障：{payload.title}\n\n现象：{payload.symptom}\n\n解决方案：{payload.resolution}"
    )
    try:
        embedding = DashScopeEmbeddingClient()
        store = ChromaStore(KnowledgeRetriever.FAULT_COLLECTION)
        import hashlib

        item_id = hashlib.sha256(content.encode("utf-8")).hexdigest()
        store.upsert(
            ids=[item_id],
            documents=[content],
            embeddings=[embedding.embed_query(content)],
            metadatas=[
                {
                    "title": payload.title,
                    "domain": payload.domain,
                    "created_by": int(current_user.id),
                    "source": "confirmed_fault_case",
                }
            ],
        )
        return {"id": item_id, "message": "故障案例已写入"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"故障案例写入失败：{exc}") from exc


@router.post("/memory/search", summary="检索当前经营者的长期记忆")
def search_memory(
    payload: MemorySearchRequest,
    current_user=Depends(get_current_user),
):
    try:
        items = LongTermMemoryStore().recall(
            user_id=current_user.id,
            query=payload.query,
            top_k=payload.top_k,
        )
        return {"query": payload.query, "items": items}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"长期记忆检索失败：{exc}") from exc
