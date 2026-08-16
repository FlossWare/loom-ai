"""Tests for RAG pipeline backends: ingestion, embeddings, and hybrid search."""

from loom_ai.backends.rag import (
    DocumentIngester,
    EmbeddingStore,
    HybridSearcher,
    _content_hash,
    _cosine_similarity,
    _simple_embedding,
)
from loom_ai.models_phase1 import RetrievalResult

# ── _simple_embedding ────────────────────────────────────────────────────


def test_simple_embedding_deterministic():
    """Same text produces the same embedding."""
    a = _simple_embedding("hello world")
    b = _simple_embedding("hello world")
    assert a == b


def test_simple_embedding_is_unit_vector():
    """Embedding is approximately L2-normalised."""
    vec = _simple_embedding("some text here", dim=32)
    norm = sum(v * v for v in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_simple_embedding_dimension():
    """Embedding has the requested dimensionality."""
    vec = _simple_embedding("text", dim=16)
    assert len(vec) == 16


def test_simple_embedding_different_texts_differ():
    """Different texts produce different embeddings."""
    a = _simple_embedding("python programming")
    b = _simple_embedding("java development")
    assert a != b


# ── _cosine_similarity ───────────────────────────────────────────────────


def test_cosine_similarity_identical():
    """Identical vectors have similarity 1.0."""
    v = [1.0, 0.0, 0.0]
    assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    """Orthogonal vectors have similarity 0.0."""
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(_cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_opposite():
    """Opposite vectors have similarity -1.0."""
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert abs(_cosine_similarity(a, b) + 1.0) < 1e-6


# ── _content_hash ────────────────────────────────────────────────────────


def test_content_hash_deterministic():
    """Same content produces the same hash."""
    first = _content_hash("hello")
    assert first == _content_hash("hello")


def test_content_hash_different():
    """Different content produces different hashes."""
    assert _content_hash("hello") != _content_hash("world")


# ── DocumentIngester ─────────────────────────────────────────────────────


async def test_ingester_returns_doc_id():
    """Ingest returns a non-empty document id."""
    ingester = DocumentIngester()
    doc_id = await ingester.ingest("Some content.")
    assert isinstance(doc_id, str)
    assert len(doc_id) > 0


async def test_ingester_creates_chunks():
    """Ingested content is split into chunks."""
    ingester = DocumentIngester()
    doc_id = await ingester.ingest("Hello world. This is a test.")
    assert ingester.document_count == 1
    assert ingester.chunk_count >= 1
    chunks = await ingester.get_chunks_for_document(doc_id)
    assert len(chunks) >= 1


async def test_ingester_metadata_propagation():
    """Metadata is propagated to chunks."""
    ingester = DocumentIngester()
    doc_id = await ingester.ingest(
        "Content here.",
        metadata={"author": "test"},
    )
    chunks = await ingester.get_chunks_for_document(doc_id)
    assert chunks[0].metadata["author"] == "test"


async def test_ingester_provenance_tracking():
    """Provenance information is stored on the document record."""
    ingester = DocumentIngester()
    doc_id = await ingester.ingest(
        "Content here.",
        provenance={"source": "web", "url": "https://example.com"},
    )
    doc = await ingester.get_document(doc_id)
    assert doc is not None
    assert doc.provenance["source"] == "web"
    assert doc.provenance["url"] == "https://example.com"


async def test_ingester_deduplication():
    """Identical content is not stored twice."""
    ingester = DocumentIngester()
    id1 = await ingester.ingest("Duplicate content.")
    id2 = await ingester.ingest("Duplicate content.")
    assert id1 == id2
    assert ingester.document_count == 1


async def test_ingester_different_content_stored():
    """Different content gets different document ids."""
    ingester = DocumentIngester()
    id1 = await ingester.ingest("First document.")
    id2 = await ingester.ingest("Second document.")
    assert id1 != id2
    assert ingester.document_count == 2


async def test_ingester_content_hash():
    """Document records store a content hash."""
    ingester = DocumentIngester()
    doc_id = await ingester.ingest("Hash me.")
    doc = await ingester.get_document(doc_id)
    assert doc is not None
    assert doc.content_hash == _content_hash("Hash me.")


async def test_ingester_delete_document():
    """Deleting a document removes it and its chunks."""
    ingester = DocumentIngester()
    doc_id = await ingester.ingest("To be deleted.")
    assert ingester.document_count == 1
    deleted = await ingester.delete_document(doc_id)
    assert deleted is True
    assert ingester.document_count == 0
    assert ingester.chunk_count == 0


async def test_ingester_delete_nonexistent():
    """Deleting a non-existent document returns False."""
    ingester = DocumentIngester()
    assert await ingester.delete_document("fake-id") is False


async def test_ingester_get_chunk():
    """Individual chunks can be retrieved by id."""
    ingester = DocumentIngester()
    doc_id = await ingester.ingest("Chunk content.")
    chunks = await ingester.get_chunks_for_document(doc_id)
    chunk = await ingester.get_chunk(chunks[0].id)
    assert chunk is not None
    assert chunk.doc_id == doc_id


async def test_ingester_chunks_for_missing_doc():
    """Requesting chunks for a missing doc returns empty list."""
    ingester = DocumentIngester()
    assert await ingester.get_chunks_for_document("missing") == []


# ── EmbeddingStore ───────────────────────────────────────────────────────


async def test_embedding_store_returns_id():
    """Store returns an embedding id."""
    store = EmbeddingStore()
    emb_id = await store.store("chunk-1", "some text")
    assert isinstance(emb_id, str)
    assert len(emb_id) > 0


async def test_embedding_store_count():
    """Count tracks stored embeddings."""
    store = EmbeddingStore()
    assert store.count == 0
    await store.store("c1", "text one")
    assert store.count == 1
    await store.store("c2", "text two")
    assert store.count == 2


async def test_embedding_store_search():
    """Search returns results sorted by similarity."""
    store = EmbeddingStore()
    await store.store("c1", "python programming language")
    await store.store("c2", "java programming language")
    await store.store("c3", "the weather is sunny")

    results = await store.search("python programming")
    assert len(results) == 3
    # First result should be most similar to query.
    chunk_ids = [r[0] for r in results]
    assert chunk_ids[0] == "c1"


async def test_embedding_store_search_limit():
    """Search respects the limit parameter."""
    store = EmbeddingStore()
    for i in range(10):
        await store.store(f"c{i}", f"text number {i}")

    results = await store.search("text", limit=3)
    assert len(results) == 3


async def test_embedding_store_custom_vector():
    """Custom vectors can be supplied instead of auto-generated."""
    store = EmbeddingStore(dim=3)
    await store.store("c1", "unused", vector=[1.0, 0.0, 0.0])
    await store.store("c2", "unused", vector=[0.0, 1.0, 0.0])

    results = await store.search("unused", vector=[1.0, 0.0, 0.0], limit=2)
    assert results[0][0] == "c1"
    assert abs(results[0][1] - 1.0) < 1e-6


async def test_embedding_store_get():
    """Retrieve a stored embedding by chunk id."""
    store = EmbeddingStore()
    await store.store("c1", "hello")
    rec = await store.get_embedding("c1")
    assert rec is not None
    assert rec.chunk_id == "c1"
    assert len(rec.vector) == 64


async def test_embedding_store_get_missing():
    """Retrieving a missing embedding returns None."""
    store = EmbeddingStore()
    assert await store.get_embedding("missing") is None


async def test_embedding_store_delete():
    """Delete removes an embedding."""
    store = EmbeddingStore()
    await store.store("c1", "text")
    assert store.count == 1
    deleted = await store.delete("c1")
    assert deleted is True
    assert store.count == 0
    assert await store.get_embedding("c1") is None


async def test_embedding_store_delete_missing():
    """Deleting a missing embedding returns False."""
    store = EmbeddingStore()
    assert await store.delete("missing") is False


async def test_embedding_store_metadata():
    """Metadata is stored with embeddings."""
    store = EmbeddingStore()
    await store.store("c1", "text", metadata={"model": "test"})
    rec = await store.get_embedding("c1")
    assert rec is not None
    assert rec.metadata["model"] == "test"


# ── HybridSearcher ───────────────────────────────────────────────────────


async def _build_hybrid_searcher() -> HybridSearcher:
    """Helper to build a HybridSearcher with sample data."""
    ingester = DocumentIngester()
    store = EmbeddingStore()

    await ingester.ingest(
        "Python is a versatile programming language.",
        metadata={"topic": "python"},
    )
    await ingester.ingest(
        "Java is a popular enterprise language.",
        metadata={"topic": "java"},
    )
    await ingester.ingest(
        "The weather is sunny and warm today.",
        metadata={"topic": "weather"},
    )

    # Index all chunks in the embedding store.
    for chunk_id, chunk in ingester._chunks.items():
        await store.store(chunk_id, chunk.content)

    return HybridSearcher(ingester, store)


async def test_hybrid_search_returns_results():
    """Hybrid search returns relevant results."""
    searcher = await _build_hybrid_searcher()
    results = await searcher.search("Python programming")
    assert len(results) >= 1
    assert isinstance(results[0], RetrievalResult)


async def test_hybrid_search_keyword_mode():
    """Keyword-only search finds matching documents."""
    searcher = await _build_hybrid_searcher()
    results = await searcher.search("Python", mode="keyword")
    assert len(results) >= 1
    assert "Python" in results[0].content


async def test_hybrid_search_vector_mode():
    """Vector-only search finds similar documents."""
    searcher = await _build_hybrid_searcher()
    results = await searcher.search("Python programming", mode="vector")
    assert len(results) >= 1


async def test_hybrid_search_limit():
    """Search respects the limit parameter."""
    searcher = await _build_hybrid_searcher()
    results = await searcher.search("language", limit=1)
    assert len(results) == 1


async def test_hybrid_search_no_results():
    """Search for non-matching query returns empty."""
    searcher = await _build_hybrid_searcher()
    results = await searcher.search("xyzzy-nonexistent", mode="keyword")
    assert results == []


async def test_hybrid_search_result_fields():
    """Results have expected fields populated."""
    searcher = await _build_hybrid_searcher()
    results = await searcher.search("Python", mode="keyword")
    assert len(results) >= 1
    r = results[0]
    assert r.content
    assert r.score > 0
    assert r.source  # doc_id
    assert r.chunk_id
    assert "topic" in r.metadata


async def test_hybrid_search_fuses_rankings():
    """Hybrid mode returns results from both keyword and vector rankings."""
    searcher = await _build_hybrid_searcher()
    results = await searcher.search("programming language")
    # Should have results covering multiple documents.
    assert len(results) >= 2
