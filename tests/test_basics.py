"""Smoke tests for loom-ai core imports and in-memory backends."""

import re

import loom_ai
from loom_ai import (
    ChatMessage,
    ChatResponse,
    Chunk,
    Document,
    Embedding,
    GraphEdge,
    GraphNode,
    LoomConfig,
    QueueItem,
    SearchResult,
)
from loom_ai.protocols import (
    EmbeddingBackend,
    QueueBackend,
    SearchBackend,
    SecretsBackend,
    StorageBackend,
)


def test_version_xy_format():
    assert re.match(r"^\d+\.\d+$", loom_ai.__version__)


def test_from_env_defaults():
    cfg = LoomConfig.from_env()
    assert isinstance(cfg.storage, StorageBackend)
    assert isinstance(cfg.queue, QueueBackend)
    assert isinstance(cfg.secrets, SecretsBackend)
    assert isinstance(cfg.embedding, EmbeddingBackend)
    assert isinstance(cfg.search, SearchBackend)
    assert cfg.graph is None
    assert cfg.llm is None


async def test_memory_storage_roundtrip():
    cfg = LoomConfig.from_env()
    doc = Document(
        id="test-1",
        title="Test Doc",
        content="Hello world",
        url="",
        category="test",
    )
    doc_id = await cfg.storage.store_document(doc)
    assert doc_id == "test-1"

    retrieved = await cfg.storage.get_document("test-1")
    assert retrieved is not None
    assert retrieved.title == "Test Doc"

    count = await cfg.storage.count_documents()
    assert count == 1


async def test_memory_queue_roundtrip():
    cfg = LoomConfig.from_env()
    item = QueueItem(id="q-1", payload={"task": "embed"})
    await cfg.queue.enqueue("test-queue", [item])

    status = await cfg.queue.status("test-queue")
    assert status["queued"] == 1

    fetched = await cfg.queue.fetch("test-queue", 1, "worker-1")
    assert len(fetched) == 1
    assert fetched[0].id == "q-1"

    await cfg.queue.complete("test-queue", "q-1")
    status = await cfg.queue.status("test-queue")
    assert status["queued"] == 0


async def test_env_secrets():
    import os

    os.environ["LOOM_TEST_KEY"] = "secret-value"
    cfg = LoomConfig.from_env()
    val = await cfg.secrets.get("LOOM_TEST_KEY")
    assert val == "secret-value"
    del os.environ["LOOM_TEST_KEY"]


async def test_noop_embedding():
    cfg = LoomConfig.from_env()
    vectors = await cfg.embedding.embed(["hello", "world"])
    assert len(vectors) == 2
    assert all(len(v) > 0 for v in vectors)


async def test_memory_search():
    cfg = LoomConfig.from_env()
    await cfg.search.index(
        Chunk(
            id="c-1",
            document_id="d-1",
            content="Python programming language",
            chunk_index=0,
            content_hash="abc123",
        ),
        [0.1, 0.2, 0.3],
    )
    results = await cfg.search.text_search("Python", limit=5)
    assert len(results) >= 1
    assert "Python" in results[0].content


def test_dataclass_construction():
    doc = Document(id="d", title="T", content="C", url="", category="")
    assert doc.id == "d"

    chunk = Chunk(id="c", document_id="d", content="C", chunk_index=0, content_hash="h")
    assert chunk.document_id == "d"

    msg = ChatMessage(role="user", content="Hi")
    assert msg.role == "user"

    resp = ChatResponse(content="Hello", model="m", provider="p", usage={})
    assert resp.model == "m"

    node = GraphNode(id="n", label="L", properties={})
    edge = GraphEdge(id="e", source="a", target="b", label="L", properties={})
    assert node.label == "L"
    assert edge.source == "a"

    emb = Embedding(
        id="e",
        chunk_id="c",
        vector=[0.1],
        model="m",
        provider="p",
        dimensions=1,
    )
    assert emb.dimensions == 1

    sr = SearchResult(
        chunk_id="c",
        content="C",
        score=0.9,
        document_title="T",
        source="s",
    )
    assert sr.score == 0.9

    qi = QueueItem(id="q", payload={})
    assert qi.worker_id is None
