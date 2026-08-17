"""Tests proving idempotency semantics for storage and search backends (#33).

Every store / upsert operation tested here is called twice with identical
arguments.  The tests assert that the observable state after the second
call is the same as after the first (no duplicates, correct counts, data
replaced rather than appended).
"""

from loom_ai import Chunk, Document, Embedding
from loom_ai.backends.memory import (
    InMemoryPersistentMemory,
    MemoryGraphBackend,
    MemorySearchBackend,
    MemoryStorageBackend,
)
from loom_ai.models import GraphEdge, GraphNode

# ── StorageBackend.store_document ────────────────────────────────────


async def test_store_document_idempotent():
    """Storing the same document twice yields exactly one document."""
    storage = MemoryStorageBackend()
    doc = Document(id="doc-1", title="Title", content="Body", url="", category="test")

    id1 = await storage.store_document(doc)
    id2 = await storage.store_document(doc)

    assert id1 == id2
    assert await storage.count_documents() == 1

    retrieved = await storage.get_document("doc-1")
    assert retrieved is not None
    assert retrieved.title == "Title"


async def test_store_document_upsert_replaces_content():
    """Re-storing with changed content replaces the old document."""
    storage = MemoryStorageBackend()
    v1 = Document(id="doc-1", title="V1", content="Old", url="", category="test")
    v2 = Document(id="doc-1", title="V2", content="New", url="", category="test")

    await storage.store_document(v1)
    await storage.store_document(v2)

    assert await storage.count_documents() == 1
    retrieved = await storage.get_document("doc-1")
    assert retrieved is not None
    assert retrieved.title == "V2"
    assert retrieved.content == "New"


# ── StorageBackend.store_chunks ──────────────────────────────────────


async def test_store_chunks_idempotent():
    """Storing the same chunks twice yields exactly one copy of each."""
    storage = MemoryStorageBackend()
    doc = Document(id="d", title="D", content="", url="", category="")
    await storage.store_document(doc)

    chunks = [
        Chunk(id="c-1", document_id="d", content="A", chunk_index=0, content_hash="a"),
        Chunk(id="c-2", document_id="d", content="B", chunk_index=1, content_hash="b"),
    ]

    n1 = await storage.store_chunks("d", chunks)
    n2 = await storage.store_chunks("d", chunks)

    assert n1 == 2
    assert n2 == 2
    assert await storage.count_chunks() == 2

    retrieved = await storage.get_chunks("d")
    assert len(retrieved) == 2


async def test_store_chunks_upsert_replaces_content():
    """Re-storing a chunk with the same id but different content replaces it."""
    storage = MemoryStorageBackend()
    doc = Document(id="d", title="D", content="", url="", category="")
    await storage.store_document(doc)

    v1 = Chunk(
        id="c-1",
        document_id="d",
        content="old",
        chunk_index=0,
        content_hash="h1",
    )
    v2 = Chunk(
        id="c-1",
        document_id="d",
        content="new",
        chunk_index=0,
        content_hash="h2",
    )

    await storage.store_chunks("d", [v1])
    await storage.store_chunks("d", [v2])

    assert await storage.count_chunks() == 1
    retrieved = await storage.get_chunks("d")
    assert retrieved[0].content == "new"


# ── StorageBackend.store_embeddings ──────────────────────────────────


async def test_store_embeddings_idempotent():
    """Storing the same embeddings twice yields one copy of each."""
    storage = MemoryStorageBackend()
    embs = [
        Embedding(
            id="e-1",
            chunk_id="c-1",
            vector=[0.1, 0.2],
            model="m",
            provider="p",
            dimensions=2,
        ),
        Embedding(
            id="e-2",
            chunk_id="c-2",
            vector=[0.3, 0.4],
            model="m",
            provider="p",
            dimensions=2,
        ),
    ]

    n1 = await storage.store_embeddings(embs)
    n2 = await storage.store_embeddings(embs)

    assert n1 == 2
    assert n2 == 2
    assert await storage.count_embeddings() == 2


async def test_store_embeddings_upsert_replaces_vector():
    """Re-storing an embedding with a new vector replaces the old one."""
    storage = MemoryStorageBackend()
    v1 = Embedding(
        id="e-1",
        chunk_id="c-1",
        vector=[0.0, 0.0],
        model="m",
        provider="p",
        dimensions=2,
    )
    v2 = Embedding(
        id="e-1",
        chunk_id="c-1",
        vector=[1.0, 1.0],
        model="m",
        provider="p",
        dimensions=2,
    )

    await storage.store_embeddings([v1])
    await storage.store_embeddings([v2])

    assert await storage.count_embeddings() == 1


async def test_store_embeddings_reuse_id_clears_stale_chunk_marker():
    """Reusing an embedding ID for a different chunk clears the old marker.

    Regression test for #250: when an embedding ID is reassigned to a new
    chunk_id, the old chunk_id must be removed from ``_embedded_chunk_ids``
    so that ``get_pending_chunks()`` correctly returns the now-unembedded
    old chunk.
    """
    storage = MemoryStorageBackend()

    # Set up two chunks under a document.
    doc = Document(id="d-1", title="T", content="C", url="", category="test")
    chunk_a = Chunk(id="c-a", document_id="d-1", content="alpha", chunk_index=0)
    chunk_b = Chunk(id="c-b", document_id="d-1", content="beta", chunk_index=1)
    await storage.store_document(doc)
    await storage.store_chunks("d-1", [chunk_a, chunk_b])

    # Embed both chunks.
    emb_a = Embedding(
        id="e-1", chunk_id="c-a", vector=[0.1], model="m", provider="p", dimensions=1
    )
    emb_b = Embedding(
        id="e-2", chunk_id="c-b", vector=[0.2], model="m", provider="p", dimensions=1
    )
    await storage.store_embeddings([emb_a, emb_b])

    # Both chunks are embedded -- no pending chunks.
    assert await storage.get_pending_chunks(10) == []

    # Reassign embedding "e-1" from chunk "c-a" to chunk "c-b".
    emb_reassigned = Embedding(
        id="e-1", chunk_id="c-b", vector=[0.3], model="m", provider="p", dimensions=1
    )
    await storage.store_embeddings([emb_reassigned])

    # chunk "c-a" is no longer covered by any embedding, so it must
    # reappear as pending.
    pending = await storage.get_pending_chunks(10)
    pending_ids = [c.id for c in pending]
    assert "c-a" in pending_ids, (
        "Old chunk should be pending after its embedding was reassigned"
    )


# ── SearchBackend.index ──────────────────────────────────────────────


async def test_search_index_idempotent():
    """Indexing the same chunk twice does not create duplicates."""
    search = MemorySearchBackend()
    chunk = Chunk(
        id="c-1",
        document_id="d-1",
        content="Python programming",
        chunk_index=0,
        content_hash="h",
    )
    vector = [0.1, 0.2, 0.3]

    r1 = await search.index(chunk, vector, document_title="Doc", source="src")
    r2 = await search.index(chunk, vector, document_title="Doc", source="src")

    assert r1 is True  # first call writes new data
    assert r2 is False  # second call sees identical data, no change

    results = await search.text_search("Python", limit=10)
    assert len(results) == 1
    assert results[0].content == "Python programming"


async def test_search_index_upsert_on_content_change():
    """Re-indexing a chunk with changed content replaces the old entry."""
    search = MemorySearchBackend()
    v1 = Chunk(
        id="c-1",
        document_id="d-1",
        content="old content",
        chunk_index=0,
        content_hash="h1",
    )
    v2 = Chunk(
        id="c-1",
        document_id="d-1",
        content="new content",
        chunk_index=0,
        content_hash="h2",
    )

    await search.index(v1, [0.1])
    result = await search.index(v2, [0.2])

    assert result is True  # content changed

    results = await search.text_search("new", limit=10)
    assert len(results) == 1
    assert results[0].content == "new content"

    # Old content must be gone
    old_results = await search.text_search("old", limit=10)
    assert len(old_results) == 0


async def test_search_index_upsert_updates_vector():
    """Re-indexing with a different vector replaces the old one."""
    search = MemorySearchBackend()
    chunk = Chunk(
        id="c-1",
        document_id="d-1",
        content="hello",
        chunk_index=0,
        content_hash="h",
    )

    await search.index(chunk, [1.0, 0.0])
    result = await search.index(chunk, [0.0, 1.0])

    assert result is True  # vector changed

    # Semantic search with the new vector should score higher
    results = await search.semantic_search([0.0, 1.0], limit=1)
    assert len(results) == 1
    assert results[0].score > 0.9


# ── PersistentMemoryBackend.store ────────────────────────────────────


async def test_persistent_memory_store_idempotent():
    """Storing under the same name twice yields exactly one record."""
    mem = InMemoryPersistentMemory()

    await mem.store("key", "value", memory_type="fact")
    await mem.store("key", "value", memory_type="fact")

    all_memories = await mem.list_memories()
    assert len(all_memories) == 1
    assert all_memories[0].content == "value"


async def test_persistent_memory_store_upsert():
    """Re-storing under the same name replaces the content."""
    mem = InMemoryPersistentMemory()

    await mem.store("key", "first", memory_type="fact")
    await mem.store("key", "second", memory_type="fact")

    all_memories = await mem.list_memories()
    assert len(all_memories) == 1

    recalled = await mem.recall("key")
    assert recalled is not None
    assert recalled.content == "second"


# ── GraphBackend.add_node ────────────────────────────────────────────


async def test_graph_add_node_idempotent():
    """Adding the same node twice yields exactly one node."""
    graph = MemoryGraphBackend()
    node = GraphNode(id="n-1", label="Person", properties={"name": "Alice"})

    id1 = await graph.add_node(node)
    id2 = await graph.add_node(node)

    assert id1 == id2

    retrieved = await graph.get_node("n-1")
    assert retrieved is not None
    assert retrieved.label == "Person"


async def test_graph_add_node_upsert():
    """Re-adding a node with changed properties replaces the old one."""
    graph = MemoryGraphBackend()
    v1 = GraphNode(id="n-1", label="Person", properties={"name": "Alice"})
    v2 = GraphNode(id="n-1", label="Person", properties={"name": "Bob"})

    await graph.add_node(v1)
    await graph.add_node(v2)

    retrieved = await graph.get_node("n-1")
    assert retrieved is not None
    assert retrieved.properties["name"] == "Bob"


async def test_graph_add_edge_idempotent():
    """Adding the same edge twice yields exactly one edge."""
    graph = MemoryGraphBackend()
    await graph.add_node(GraphNode(id="a", label="A", properties={}))
    await graph.add_node(GraphNode(id="b", label="B", properties={}))

    edge = GraphEdge(id="e-1", source="a", target="b", label="knows", properties={})

    id1 = await graph.add_edge(edge)
    id2 = await graph.add_edge(edge)

    assert id1 == id2

    # Only one neighbor, not two
    neighbors = await graph.get_neighbors("a")
    assert len(neighbors) == 1
    assert neighbors[0].id == "b"
