from types import SimpleNamespace
from uuid import uuid4

from app.config.settings import settings
from app.embeddings.dashscope import DashScopeEmbeddingClient
from app.rag.chunker import TokenChunker
from app.rag.retriever import KnowledgeRetriever
from app.rag.query_rewriter import retrieval_query_rewriter
from app.vectorstore import ChromaStore


def test_token_chunker_uses_400_with_60_overlap():
    chunker = TokenChunker(chunk_size=400, overlap=60)
    chunks = chunker.split("abc def " * 1000)

    assert len(chunks) > 1
    assert max(item.token_end - item.token_start for item in chunks) == 400
    assert chunks[0].token_end - chunks[1].token_start == 60


def test_chroma_store_uses_cosine_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", str(tmp_path))
    name = f"test_{uuid4().hex}"
    store = ChromaStore(name)
    store.upsert(
        ids=["dataset", "training"],
        documents=["数据集版本管理", "模型训练监控"],
        embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        metadatas=[{"domain": "dataset"}, {"domain": "training"}],
    )

    result = store.query(embedding=[0.9, 0.1, 0.0], top_k=1)

    assert store.count == 2
    assert result[0]["id"] == "dataset"
    assert result[0]["metadata"]["domain"] == "dataset"
    assert result[0]["similarity"] > 0.9


def test_dashscope_embedding_uses_configured_model_and_dimensions(monkeypatch):
    calls = []

    class FakeEmbeddings:
        def create(self, **kwargs):
            calls.append(kwargs)
            data = [
                SimpleNamespace(index=index, embedding=[float(index), 0.5, 1.0])
                for index, _ in enumerate(kwargs["input"])
            ]
            return SimpleNamespace(data=data)

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = FakeEmbeddings()

    import openai

    monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSIONS", 3)
    monkeypatch.setattr(settings, "EMBEDDING_BATCH_SIZE", 2)
    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)

    vectors = DashScopeEmbeddingClient().embed_documents(["a", "b", "c"])

    assert len(vectors) == 3
    assert [len(call["input"]) for call in calls] == [2, 1]
    assert all(call["model"] == "text-embedding-v4" for call in calls)
    assert all(call["dimensions"] == 3 for call in calls)


def test_knowledge_reindex_removes_changed_and_deleted_source_chunks(tmp_path, monkeypatch):
    class FakeEmbedding:
        @staticmethod
        def embed_documents(documents):
            return [[float(index + 1), 0.5, 1.0] for index, _ in enumerate(documents)]

    monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    source_root = tmp_path / "knowledge"
    (source_root / "dataset").mkdir(parents=True)
    (source_root / "training").mkdir(parents=True)
    dataset_file = source_root / "dataset" / "rules.md"
    training_file = source_root / "training" / "states.md"
    dataset_file.write_text("旧的数据集规则", encoding="utf-8")
    training_file.write_text("训练状态规则", encoding="utf-8")

    retriever = KnowledgeRetriever(f"test_sync_{uuid4().hex}")
    retriever.embedding = FakeEmbedding()
    first = retriever.index_directory(source_root)
    assert first == {"files": 2, "chunks": 2, "deleted_chunks": 0, "total": 2}

    retriever.store.upsert(
        ids=["confirmed-case"],
        documents=["人工确认的动态故障案例"],
        embeddings=[[9.0, 0.5, 1.0]],
        metadatas=[{"source": "confirmed_fault_case", "domain": "general"}],
    )

    dataset_file.write_text("新的数据集规则", encoding="utf-8")
    training_file.unlink()
    second = retriever.index_directory(source_root)
    items = retriever.store.list_items()

    assert second == {"files": 1, "chunks": 1, "deleted_chunks": 2, "total": 2}
    assert sorted(
        (item["metadata"]["source"], item["content"]) for item in items
    ) == [
        ("confirmed_fault_case", "人工确认的动态故障案例"),
        ("dataset/rules.md", "新的数据集规则"),
    ]


def test_rag_filters_low_similarity_and_deduplicates_adjacent_chunks(monkeypatch):
    candidates = [
        {
            "id": "a0",
            "content": "冻结数据集版本前必须完成校验",
            "similarity": 0.91,
            "metadata": {"source": "dataset/freeze.md", "chunk_index": 0},
        },
        {
            "id": "a1",
            "content": "冻结数据集版本后版本将变成只读",
            "similarity": 0.89,
            "metadata": {"source": "dataset/freeze.md", "chunk_index": 1},
        },
        {
            "id": "duplicate",
            "content": "冻结数据集版本前必须完成校验",
            "similarity": 0.88,
            "metadata": {"source": "general/copy.md", "chunk_index": 4},
        },
        {
            "id": "impact",
            "content": "冻结会阻止继续修改样品和标注",
            "similarity": 0.82,
            "metadata": {"source": "dataset/impact.md", "chunk_index": 0},
        },
        {
            "id": "low",
            "content": "无关内容",
            "similarity": 0.20,
            "metadata": {"source": "general/other.md", "chunk_index": 0},
        },
    ]

    class FakeStore:
        count = len(candidates)

        def query(self, **kwargs):
            assert kwargs["top_k"] == 8
            return candidates

    class FakeEmbedding:
        @staticmethod
        def embed_query(query):
            return [1.0, 0.0]

    retriever = object.__new__(KnowledgeRetriever)
    retriever.store = FakeStore()
    retriever.embedding = FakeEmbedding()
    monkeypatch.setattr(settings, "RAG_CANDIDATE_MULTIPLIER", 4)
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 0.45)
    monkeypatch.setattr(settings, "RAG_DEDUP_SIMILARITY", 0.88)
    monkeypatch.setattr(settings, "RAG_MAX_CHUNKS_PER_SOURCE", 2)

    results = retriever.search("如何冻结", top_k=2)

    assert [item["id"] for item in results] == ["a0", "impact"]
    assert [item["rank"] for item in results] == [1, 2]


def test_retrieval_query_rewriter_uses_structured_task_state():
    result = retrieval_query_rewriter.rewrite(
        "这个版本怎么冻结？",
        context_state={
            "active_agent": "dataset",
            "active_workflow": {
                "agent": "dataset",
                "purpose": "dataset.add_samples",
                "status": "active",
            },
            "entities": {"dataset_id": 21, "version": "draft-v21"},
        },
    )

    assert result.domain == "dataset"
    assert result.purpose == "dataset.freeze"
    assert result.context_used is True
    assert "冻结条件、影响范围和操作流程" in result.rewritten_query
    assert "数据集 ID 21" in result.rewritten_query
    assert "draft-v21" in result.rewritten_query

    new_topic = retrieval_query_rewriter.rewrite(
        "如何训练模型？",
        context_state={
            "active_agent": "dataset",
            "active_workflow": {"purpose": "dataset.add_samples"},
            "entities": {"dataset_id": 21},
        },
    )
    assert new_topic.domain == "training"
    assert new_topic.purpose is None
    assert new_topic.rewritten_query == "如何训练模型？"


def test_knowledge_search_api_passes_owned_session_state(client, db_session, monkeypatch):
    from app.api import knowledge as knowledge_api
    from app.entity.db_models import ChatSession

    client.post(
        "/api/auth/register",
        json={"username": "rag_owner", "email": "rag_owner@example.com", "password": "123456"},
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "rag_owner", "password": "123456"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    session_uuid = client.post(
        "/api/chat/sessions", headers=headers, json={"title": "rag context"}
    ).json()["session_uuid"]
    session = db_session.query(ChatSession).filter_by(session_uuid=session_uuid).one()
    session.context_state = {
        "active_agent": "dataset",
        "active_workflow": {"agent": "dataset", "purpose": "dataset.freeze", "status": "active"},
        "entities": {"dataset_id": 31},
    }
    db_session.commit()
    captured = {}

    class FakeRetriever:
        def retrieve(self, query, **kwargs):
            captured.update({"query": query, **kwargs})
            return {
                "original_query": query,
                "rewritten_query": "rewritten",
                "domain": "dataset",
                "purpose": "dataset.freeze",
                "context_used": True,
                "items": [],
            }

    monkeypatch.setattr(knowledge_api, "KnowledgeRetriever", FakeRetriever)
    response = client.post(
        "/api/knowledge/search",
        headers=headers,
        json={
            "query": "这个版本有什么影响？",
            "session_uuid": session_uuid,
            "top_k": 4,
            "min_similarity": 0.6,
        },
    )

    assert response.status_code == 200
    assert captured["context_state"]["entities"]["dataset_id"] == 31
    assert captured["top_k"] == 4
    assert captured["min_similarity"] == 0.6
