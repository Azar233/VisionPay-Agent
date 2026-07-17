"""Authenticated knowledge, fault-case and semantic-memory management APIs."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config.settings import settings
from app.embeddings import DashScopeEmbeddingClient
from app.database.session import get_db
from app.entity.db_models import ChatSession
from app.memory import LongTermMemoryStore, MemoryNotFoundError
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
    min_similarity: float | None = Field(None, ge=-1, le=1)
    session_uuid: str | None = Field(None, max_length=100)


class FaultCaseRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    symptom: str = Field(..., min_length=1, max_length=4000)
    resolution: str = Field(..., min_length=1, max_length=8000)
    domain: str = Field(default="general", min_length=1, max_length=50)


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=settings.LONG_TERM_MEMORY_TOP_K, ge=1, le=20)
    category: str | None = Field(None, max_length=50)
    min_similarity: float | None = Field(None, ge=-1, le=1)


class MemoryCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    category: str = Field(default="preference", min_length=1, max_length=50)
    session_uuid: str | None = Field(None, max_length=100)


class MemoryUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    category: str | None = Field(None, min_length=1, max_length=50)
    session_uuid: str | None = Field(None, max_length=100)


def _session_state(
    db: Session, *, user_id: int, session_uuid: str | None
) -> dict | None:
    if not session_uuid:
        return None
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.user_id == user_id,
            ChatSession.session_uuid == session_uuid,
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="对话不存在或无权访问")
    return session.context_state if isinstance(session.context_state, dict) else {}


def _memory_error(exc: ValueError) -> None:
    status = 404 if isinstance(exc, MemoryNotFoundError) else 400
    raise HTTPException(status_code=status, detail=str(exc)) from exc


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
        "min_similarity": settings.RAG_MIN_SIMILARITY,
        "dedup_similarity": settings.RAG_DEDUP_SIMILARITY,
        "adjacent_dedup_similarity": settings.RAG_ADJACENT_DEDUP_SIMILARITY,
        "max_chunks_per_source": settings.RAG_MAX_CHUNKS_PER_SOURCE,
        "memory_min_similarity": settings.LONG_TERM_MEMORY_MIN_SIMILARITY,
        "memory_dedupe_similarity": settings.LONG_TERM_MEMORY_DEDUPE_SIMILARITY,
        "memory_categories": sorted(LongTermMemoryStore.CATEGORIES),
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
    db: Session = Depends(get_db),
):
    try:
        return KnowledgeRetriever().retrieve(
            payload.query,
            context_state=_session_state(
                db,
                user_id=int(current_user.id),
                session_uuid=payload.session_uuid,
            ),
            top_k=payload.top_k,
            domain=payload.domain,
            min_similarity=payload.min_similarity,
        )
    except HTTPException:
        raise
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
            category=payload.category,
            min_similarity=payload.min_similarity,
        )
        return {
            "query": payload.query,
            "category": payload.category,
            "min_similarity": payload.min_similarity
            if payload.min_similarity is not None
            else settings.LONG_TERM_MEMORY_MIN_SIMILARITY,
            "items": items,
        }
    except ValueError as exc:
        _memory_error(exc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"长期记忆检索失败：{exc}") from exc


@router.post("/memory", summary="保存或覆盖当前经营者的长期记忆")
def create_memory(
    payload: MemoryCreateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        _session_state(
            db,
            user_id=int(current_user.id),
            session_uuid=payload.session_uuid,
        )
        return LongTermMemoryStore().remember(
            user_id=int(current_user.id),
            content=payload.content,
            category=payload.category,
            session_uuid=payload.session_uuid,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        _memory_error(exc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"长期记忆保存失败：{exc}") from exc


@router.get("/memory", summary="分页查看当前经营者的长期记忆")
def list_memories(
    category: str | None = Query(None, max_length=50),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
):
    try:
        return LongTermMemoryStore().list(
            user_id=int(current_user.id),
            category=category,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        _memory_error(exc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"长期记忆读取失败：{exc}") from exc


@router.get("/memory/{memory_id}", summary="查看单条长期记忆")
def get_memory(
    memory_id: str,
    current_user=Depends(get_current_user),
):
    try:
        return LongTermMemoryStore().get(
            user_id=int(current_user.id), memory_id=memory_id
        )
    except ValueError as exc:
        _memory_error(exc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"长期记忆读取失败：{exc}") from exc


@router.put("/memory/{memory_id}", summary="修改并合并重复长期记忆")
def update_memory(
    memory_id: str,
    payload: MemoryUpdateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        _session_state(
            db,
            user_id=int(current_user.id),
            session_uuid=payload.session_uuid,
        )
        return LongTermMemoryStore().update(
            user_id=int(current_user.id),
            memory_id=memory_id,
            content=payload.content,
            category=payload.category,
            session_uuid=payload.session_uuid,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        _memory_error(exc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"长期记忆修改失败：{exc}") from exc


@router.delete("/memory/{memory_id}", summary="删除当前经营者的长期记忆")
def delete_memory(
    memory_id: str,
    current_user=Depends(get_current_user),
):
    try:
        return LongTermMemoryStore().delete(
            user_id=int(current_user.id), memory_id=memory_id
        )
    except ValueError as exc:
        _memory_error(exc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"长期记忆删除失败：{exc}") from exc
