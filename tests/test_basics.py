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


async def test_from_env_defaults():
    cfg = await LoomConfig.from_env()
    assert isinstance(cfg.storage, StorageBackend)
    assert isinstance(cfg.queue, QueueBackend)
    assert isinstance(cfg.secrets, SecretsBackend)
    assert isinstance(cfg.embedding, EmbeddingBackend)
    assert isinstance(cfg.search, SearchBackend)
    assert cfg.graph is None
    assert cfg.llm is None


async def test_memory_storage_roundtrip():
    cfg = await LoomConfig.from_env()
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
    cfg = await LoomConfig.from_env()
    item = QueueItem(id="q-1", payload={"task": "embed"})
    await cfg.queue.enqueue("test-queue", [item])

    status = await cfg.queue.status("test-queue")
    assert status["pending"] == 1

    fetched = await cfg.queue.fetch("test-queue", 1, "worker-1")
    assert len(fetched) == 1
    assert fetched[0].id == "q-1"

    await cfg.queue.complete("test-queue", "q-1")
    status = await cfg.queue.status("test-queue")
    assert status["pending"] == 0


async def test_env_secrets():
    import os

    os.environ["LOOM_TEST_KEY"] = "secret-value"
    cfg = await LoomConfig.from_env()
    val = await cfg.secrets.get("LOOM_TEST_KEY")
    assert val == "secret-value"
    del os.environ["LOOM_TEST_KEY"]


async def test_noop_embedding():
    cfg = await LoomConfig.from_env()
    vectors = await cfg.embedding.embed(["hello", "world"])
    assert len(vectors) == 2
    assert all(len(v) > 0 for v in vectors)


async def test_memory_search():
    cfg = await LoomConfig.from_env()
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


async def test_store_chunks_no_duplicates_on_re_store():
    """Re-storing chunks must not duplicate secondary index entries (#41)."""
    cfg = await LoomConfig.from_env()
    doc = Document(id="dup-doc", title="Dup", content="body", url="", category="test")
    await cfg.storage.store_document(doc)

    chunk = Chunk(
        id="dup-c-1",
        document_id="dup-doc",
        content="hello",
        chunk_index=0,
        content_hash="h1",
    )

    # Store the same chunk twice (simulates HTTP retry)
    await cfg.storage.store_chunks("dup-doc", [chunk])
    await cfg.storage.store_chunks("dup-doc", [chunk])

    # get_chunks must return exactly one entry, not two
    chunks = await cfg.storage.get_chunks("dup-doc")
    assert len(chunks) == 1

    # count_chunks must agree with primary store size
    count = await cfg.storage.count_chunks()
    assert count == 1

    # get_pending_chunks must not return duplicates
    pending = await cfg.storage.get_pending_chunks(10)
    pending_ids = [c.id for c in pending]
    assert pending_ids.count("dup-c-1") == 1


async def test_store_chunks_updates_content_on_re_store():
    """Re-storing a chunk with updated content must replace the old entry."""
    cfg = await LoomConfig.from_env()
    doc = Document(id="upd-doc", title="Upd", content="body", url="", category="test")
    await cfg.storage.store_document(doc)

    chunk_v1 = Chunk(
        id="upd-c-1",
        document_id="upd-doc",
        content="version 1",
        chunk_index=0,
        content_hash="h1",
    )
    chunk_v2 = Chunk(
        id="upd-c-1",
        document_id="upd-doc",
        content="version 2",
        chunk_index=0,
        content_hash="h2",
    )

    await cfg.storage.store_chunks("upd-doc", [chunk_v1])
    await cfg.storage.store_chunks("upd-doc", [chunk_v2])

    chunks = await cfg.storage.get_chunks("upd-doc")
    assert len(chunks) == 1
    assert chunks[0].content == "version 2"


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


async def test_batch_enqueue_unique_ids():
    """Batch-enqueued items must have unique IDs so no data is lost on fetch."""
    cfg = await LoomConfig.from_env()
    items = [QueueItem(id=f"batch-{i}", payload={"index": i}) for i in range(5)]
    count = await cfg.queue.enqueue("batch-queue", items)
    assert count == 5

    fetched = await cfg.queue.fetch("batch-queue", 5, "worker-1")
    assert len(fetched) == 5
    fetched_ids = [item.id for item in fetched]
    assert len(set(fetched_ids)) == 5, f"Duplicate IDs found: {fetched_ids}"


async def test_batch_enqueue_no_overwrite_in_processing():
    """Unique IDs prevent items from overwriting each other in _processing."""
    cfg = await LoomConfig.from_env()
    items = [QueueItem(id=f"dup-test-{i}", payload={"value": i}) for i in range(3)]
    await cfg.queue.enqueue("overwrite-queue", items)

    fetched = await cfg.queue.fetch("overwrite-queue", 3, "worker-1")
    assert len(fetched) == 3

    # Complete each item individually -- all must succeed
    for item in fetched:
        ok = await cfg.queue.complete("overwrite-queue", item.id)
        assert ok, f"Failed to complete item {item.id}"
