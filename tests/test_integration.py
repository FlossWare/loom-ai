"""End-to-end integration tests exercising multiple backends together.

These tests verify that the core workflow -- store, embed, search, queue,
execute -- functions correctly when backends are wired through LoomConfig.
All tests use the in-memory backends shipped with the core package, so no
external services are required.
"""

from __future__ import annotations

import pytest

from loom_ai import (
    Chunk,
    Document,
    ExecutionPlan,
    QueueItem,
    Task,
)
from loom_ai.backends.env_secrets import EnvSecretsBackend
from loom_ai.backends.memory import (
    MemoryGraphBackend,
    MemoryQueueBackend,
    MemorySearchBackend,
    MemoryStorageBackend,
    NoopEmbeddingBackend,
)
from loom_ai.config import LoomConfig
from loom_ai.execution import ExecutionEngine, NoopTaskRunner


@pytest.fixture
def config() -> LoomConfig:
    """LoomConfig with all in-memory backends."""
    return LoomConfig(
        storage=MemoryStorageBackend(),
        queue=MemoryQueueBackend(),
        secrets=EnvSecretsBackend(),
        embedding=NoopEmbeddingBackend(),
        search=MemorySearchBackend(),
        graph=MemoryGraphBackend(),
    )


# -- End-to-end workflow ------------------------------------------------------


async def test_store_embed_search_workflow(config):
    """Store a document, embed its chunks, search for it."""
    # 1. Store a document
    doc = Document(
        id="e2e-doc",
        title="Integration Guide",
        content="How to integrate loom-ai backends",
    )
    doc_id = await config.storage.store_document(doc)
    assert doc_id == "e2e-doc"

    # 2. Create and store chunks
    chunk = Chunk(
        id="e2e-c-0",
        document_id="e2e-doc",
        content="How to integrate loom-ai backends",
        chunk_index=0,
    )
    stored = await config.storage.store_chunks("e2e-doc", [chunk])
    assert stored == 1

    # 3. Embed the chunk
    vector = await config.embedding.embed_single(chunk.content)
    assert len(vector) > 0

    # 4. Index in search backend
    await config.search.index(chunk, vector, document_title=doc.title, source=doc.url)

    # 5. Search by text
    text_results = await config.search.text_search("integrate", limit=5)
    assert len(text_results) >= 1
    assert "integrate" in text_results[0].content

    # 6. Search by vector
    sem_results = await config.search.semantic_search(vector, limit=5)
    assert len(sem_results) >= 1


async def test_queue_processing_workflow(config):
    """Enqueue a task, fetch it, and complete it."""
    # 1. Enqueue a processing task
    item = QueueItem(id="task-1", payload={"document_id": "e2e-doc"})
    count = await config.queue.enqueue("processing", [item])
    assert count == 1

    # 2. Worker fetches the task
    fetched = await config.queue.fetch("processing", 1, "worker-1")
    assert len(fetched) == 1
    assert fetched[0].payload["document_id"] == "e2e-doc"

    # 3. Worker completes the task
    ok = await config.queue.complete("processing", "task-1")
    assert ok is True

    # 4. Queue is now empty
    status = await config.queue.status("processing")
    assert status["pending"] == 0
    assert status["processing"] == 0


async def test_execution_engine_workflow(config):
    """Execute a plan with dependent tasks via the ExecutionEngine."""
    runner = NoopTaskRunner()
    engine = ExecutionEngine(config, runner=runner)

    plan = ExecutionPlan(
        id="plan-1",
        tasks=[
            Task(
                id="ingest",
                name="Ingest Document",
                description="Load document into storage",
                input_data={"path": "/docs/guide.md"},
            ),
            Task(
                id="embed",
                name="Embed Chunks",
                description="Generate embeddings for chunks",
                dependencies=["ingest"],
                input_data={"model": "noop"},
            ),
            Task(
                id="index",
                name="Index for Search",
                description="Index chunks in search backend",
                dependencies=["embed"],
                input_data={"backend": "memory"},
            ),
        ],
    )

    result = await engine.execute_plan(plan)

    for task in result.tasks:
        assert task.status.value == "completed", (
            f"Task {task.id} has status {task.status.value}"
        )


async def test_graph_with_storage_workflow(config):
    """Store a document and build a knowledge graph from it."""
    assert config.graph is not None

    # 1. Store a document
    doc = Document(
        id="graph-doc",
        title="Architecture",
        content="Describes system architecture",
    )
    await config.storage.store_document(doc)

    # 2. Build graph nodes from document metadata
    from loom_ai import GraphEdge, GraphNode

    doc_node = GraphNode(id="gn-doc", label="Document", properties={"title": doc.title})
    topic_node = GraphNode(
        id="gn-arch", label="Topic", properties={"name": "Architecture"}
    )
    await config.graph.add_node(doc_node)
    await config.graph.add_node(topic_node)

    edge = GraphEdge(id="ge-1", source="gn-doc", target="gn-arch", label="covers")
    await config.graph.add_edge(edge)

    # 3. Query the graph
    neighbors = await config.graph.get_neighbors("gn-doc")
    assert len(neighbors) == 1
    assert neighbors[0].id == "gn-arch"


async def test_multi_backend_roundtrip(config):
    """Verify data flows correctly across storage, embedding, and search."""
    # Store multiple documents with chunks
    for i in range(3):
        doc = Document(
            id=f"rt-doc-{i}",
            title=f"Roundtrip Doc {i}",
            content=f"Content for roundtrip document {i}",
        )
        await config.storage.store_document(doc)

        chunks = [
            Chunk(
                id=f"rt-c-{i}-{j}",
                document_id=f"rt-doc-{i}",
                content=f"Roundtrip chunk {j} of doc {i}",
                chunk_index=j,
            )
            for j in range(2)
        ]
        await config.storage.store_chunks(f"rt-doc-{i}", chunks)

        # Embed and index each chunk
        for chunk in chunks:
            vector = await config.embedding.embed_single(chunk.content)
            await config.search.index(chunk, vector, document_title=doc.title)

    # Verify storage counts
    assert await config.storage.count_documents() == 3
    assert await config.storage.count_chunks() == 6

    # Verify search finds content
    results = await config.search.text_search("Roundtrip", limit=10)
    assert len(results) == 6
