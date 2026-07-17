from types import SimpleNamespace
from uuid import uuid4

from app.config.settings import settings
from app.embeddings.dashscope import DashScopeEmbeddingClient
from app.rag.chunker import TokenChunker
from app.rag.retriever import KnowledgeRetriever
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
