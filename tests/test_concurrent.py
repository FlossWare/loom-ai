"""Concurrency tests for in-memory backends.

Verifies that storage, queue, search, and graph backends produce
correct results under concurrent access via asyncio.gather.  All
tests run against in-memory backends -- no external services needed.
"""

from __future__ import annotations

import asyncio

from loom_ai import Chunk, Document, GraphEdge, GraphNode, LoomConfig, QueueItem
from loom_ai.backends.memory import (
    MemoryGraphBackend,
    MemoryQueueBackend,
    MemorySearchBackend,
    MemoryStorageBackend,
)

# ── Storage concurrency ────────────────────────────────────────────────


async def test_concurrent_document_stores():
    storage = MemoryStorageBackend()
    docs = [
        Document(
            id=f"doc-{i}", title=f"Doc {i}", content=f"body {i}",
            url="", category="test",
        )
        for i in range(50)
    ]
    await asyncio.gather(*(storage.store_document(d) for d in docs))

    count = await storage.count_documents()
    assert count == 50

    for i in range(50):
        retrieved = await storage.get_document(f"doc-{i}")
        assert retrieved is not None
        assert retrieved.title == f"Doc {i}"


async def test_concurrent_chunk_stores():
    storage = MemoryStorageBackend()
    doc = Document(id="d-1", title="T", content="C", url="", category="test")
    await storage.store_document(doc)

    chunks = [
        Chunk(
            id=f"c-{i}",
            document_id="d-1",
            content=f"chunk {i}",
            chunk_index=i,
            content_hash=f"h{i}",
        )
        for i in range(30)
    ]

    await asyncio.gather(
        *(storage.store_chunks("d-1", [c]) for c in chunks)
    )

    count = await storage.count_chunks()
    assert count == 30

    stored = await storage.get_chunks("d-1")
    assert len(stored) == 30
    stored_ids = {c.id for c in stored}
    assert stored_ids == {f"c-{i}" for i in range(30)}


async def test_concurrent_document_store_and_read():
    storage = MemoryStorageBackend()

    async def store_and_read(i: int) -> Document | None:
        doc = Document(
            id=f"sr-{i}", title=f"SR {i}", content=f"content {i}", url="", category=""
        )
        await storage.store_document(doc)
        return await storage.get_document(f"sr-{i}")

    results = await asyncio.gather(*(store_and_read(i) for i in range(40)))
    for i, doc in enumerate(results):
        assert doc is not None
        assert doc.id == f"sr-{i}"


# ── Queue concurrency ──────────────────────────────────────────────────


async def test_concurrent_enqueue():
    queue = MemoryQueueBackend()
    batches = [
        [QueueItem(id=f"q-{batch}-{i}", payload={"b": batch, "i": i}) for i in range(5)]
        for batch in range(10)
    ]
    counts = await asyncio.gather(
        *(queue.enqueue("work", batch) for batch in batches)
    )
    assert sum(counts) == 50

    status = await queue.status("work")
    assert status["pending"] == 50


async def test_concurrent_enqueue_and_fetch():
    queue = MemoryQueueBackend()
    items = [QueueItem(id=f"ef-{i}", payload={"i": i}) for i in range(20)]
    await queue.enqueue("q", items)

    fetched = await asyncio.gather(
        queue.fetch("q", 5, "w-1"),
        queue.fetch("q", 5, "w-2"),
        queue.fetch("q", 5, "w-3"),
        queue.fetch("q", 5, "w-4"),
    )

    all_items = [item for batch in fetched for item in batch]
    assert len(all_items) == 20

    all_ids = [item.id for item in all_items]
    assert len(set(all_ids)) == 20


async def test_concurrent_complete():
    queue = MemoryQueueBackend()
    items = [QueueItem(id=f"cc-{i}", payload={}) for i in range(10)]
    await queue.enqueue("cq", items)
    await queue.fetch("cq", 10, "w-1")

    results = await asyncio.gather(
        *(queue.complete("cq", f"cc-{i}") for i in range(10))
    )
    assert all(results)

    status = await queue.status("cq")
    assert status["pending"] == 0
    assert status["processing"] == 0


# ── Search concurrency ─────────────────────────────────────────────────


async def test_concurrent_index_and_search():
    search = MemorySearchBackend()

    chunks = [
        Chunk(
            id=f"sc-{i}",
            document_id="d-1",
            content=f"Python programming example {i}",
            chunk_index=i,
            content_hash=f"h{i}",
        )
        for i in range(20)
    ]

    await asyncio.gather(
        *(search.index(c, [float(i) / 20, 0.5, 0.5]) for i, c in enumerate(chunks))
    )

    results = await search.text_search("Python", limit=20)
    assert len(results) == 20

    result_ids = {r.chunk_id for r in results}
    assert result_ids == {f"sc-{i}" for i in range(20)}


async def test_concurrent_text_searches():
    search = MemorySearchBackend()

    for i in range(10):
        chunk = Chunk(
            id=f"ts-{i}",
            document_id="d-1",
            content=f"topic-{i} content about algorithms",
            chunk_index=i,
            content_hash=f"h{i}",
        )
        await search.index(chunk, [float(i), 0.0])

    queries = [f"topic-{i}" for i in range(10)]
    results = await asyncio.gather(
        *(search.text_search(q, limit=5) for q in queries)
    )

    for i, result_list in enumerate(results):
        assert len(result_list) >= 1
        assert any(f"topic-{i}" in r.content for r in result_list)


async def test_concurrent_semantic_searches():
    search = MemorySearchBackend()

    for i in range(10):
        vec = [0.0] * 10
        vec[i] = 1.0
        chunk = Chunk(
            id=f"ss-{i}",
            document_id="d-1",
            content=f"semantic {i}",
            chunk_index=i,
            content_hash=f"h{i}",
        )
        await search.index(chunk, vec)

    queries = []
    for i in range(10):
        vec = [0.0] * 10
        vec[i] = 1.0
        queries.append(vec)

    results = await asyncio.gather(
        *(search.semantic_search(q, limit=3) for q in queries)
    )

    for i, result_list in enumerate(results):
        assert len(result_list) >= 1
        assert result_list[0].chunk_id == f"ss-{i}"


# ── Graph concurrency ──────────────────────────────────────────────────


async def test_concurrent_add_nodes():
    graph = MemoryGraphBackend()
    nodes = [
        GraphNode(id=f"n-{i}", label=f"Node {i}", properties={"idx": i})
        for i in range(30)
    ]
    ids = await asyncio.gather(*(graph.add_node(n) for n in nodes))
    assert len(ids) == 30
    assert set(ids) == {f"n-{i}" for i in range(30)}

    for i in range(30):
        node = await graph.get_node(f"n-{i}")
        assert node is not None
        assert node.label == f"Node {i}"


async def test_concurrent_add_edges():
    graph = MemoryGraphBackend()

    for i in range(20):
        await graph.add_node(GraphNode(id=f"en-{i}", label=f"N{i}", properties={}))

    edges = [
        GraphEdge(
            id=f"e-{i}",
            source=f"en-{i}",
            target=f"en-{(i + 1) % 20}",
            label="LINKS",
            properties={},
        )
        for i in range(20)
    ]

    ids = await asyncio.gather(*(graph.add_edge(e) for e in edges))
    assert len(ids) == 20


async def test_concurrent_neighbor_reads():
    graph = MemoryGraphBackend()

    await graph.add_node(GraphNode(id="hub", label="Hub", properties={}))
    for i in range(10):
        await graph.add_node(GraphNode(id=f"spoke-{i}", label=f"S{i}", properties={}))
        await graph.add_edge(
            GraphEdge(
                id=f"he-{i}",
                source="hub",
                target=f"spoke-{i}",
                label="HAS",
                properties={},
            )
        )

    results = await asyncio.gather(
        *(graph.get_neighbors("hub") for _ in range(20))
    )

    for neighbors in results:
        assert len(neighbors) == 10
        neighbor_ids = {n.id for n in neighbors}
        assert neighbor_ids == {f"spoke-{i}" for i in range(10)}


# ── Cross-backend concurrency ──────────────────────────────────────────


async def test_concurrent_multi_backend_operations():
    cfg = await LoomConfig.from_env()

    async def store_doc(i: int):
        doc = Document(
            id=f"mb-{i}", title=f"MB {i}", content=f"multi {i}", url="", category=""
        )
        return await cfg.storage.store_document(doc)

    async def enqueue_item(i: int):
        item = QueueItem(id=f"mq-{i}", payload={"i": i})
        return await cfg.queue.enqueue("multi", [item])

    async def index_chunk(i: int):
        chunk = Chunk(
            id=f"mc-{i}",
            document_id="mb-0",
            content=f"multi backend content {i}",
            chunk_index=i,
            content_hash=f"mh{i}",
        )
        return await cfg.search.index(chunk, [float(i)])

    await asyncio.gather(
        *(store_doc(i) for i in range(10)),
        *(enqueue_item(i) for i in range(10)),
        *(index_chunk(i) for i in range(10)),
    )

    doc_count = await cfg.storage.count_documents()
    assert doc_count == 10

    queue_status = await cfg.queue.status("multi")
    assert queue_status["pending"] == 10

    search_results = await cfg.search.text_search("multi backend", limit=20)
    assert len(search_results) == 10


async def test_no_data_corruption_under_interleaved_writes():
    storage = MemoryStorageBackend()
    queue = MemoryQueueBackend()

    async def write_cycle(i: int):
        doc = Document(
            id=f"ic-{i}", title=f"IC {i}",
            content=f"interleaved {i}", url="", category="",
        )
        await storage.store_document(doc)

        chunk = Chunk(
            id=f"ich-{i}",
            document_id=f"ic-{i}",
            content=f"chunk for ic-{i}",
            chunk_index=0,
            content_hash=f"ich{i}",
        )
        await storage.store_chunks(f"ic-{i}", [chunk])

        item = QueueItem(id=f"iq-{i}", payload={"doc": f"ic-{i}"})
        await queue.enqueue("interleaved", [item])

    await asyncio.gather(*(write_cycle(i) for i in range(25)))

    assert await storage.count_documents() == 25
    assert await storage.count_chunks() == 25

    status = await queue.status("interleaved")
    assert status["pending"] == 25

    for i in range(25):
        doc = await storage.get_document(f"ic-{i}")
        assert doc is not None
        assert doc.content == f"interleaved {i}"

        chunks = await storage.get_chunks(f"ic-{i}")
        assert len(chunks) == 1
        assert chunks[0].content == f"chunk for ic-{i}"
