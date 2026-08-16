"""Tests for RAG chunking and knowledge pipeline backends."""

from loom_ai.backends.knowledge import InMemoryKnowledgePipeline, TokenChunker
from loom_ai.contracts_phase1 import ChunkingStrategy, KnowledgePipeline
from loom_ai.models_phase1 import RetrievalResult

# ── TokenChunker ─────────────────────────────────────────────────────────


def test_token_chunker_satisfies_protocol():
    assert isinstance(TokenChunker(), ChunkingStrategy)


def test_chunk_empty_string():
    chunker = TokenChunker()
    assert chunker.chunk("") == []


def test_chunk_single_short_sentence():
    chunker = TokenChunker()
    result = chunker.chunk("Hello world.")
    assert result == ["Hello world."]


def test_chunk_splits_on_sentence_boundary():
    chunker = TokenChunker()
    # Two sentences that together exceed max_tokens=5 (~20 chars).
    text = "First sentence. Second sentence."
    result = chunker.chunk(text, max_tokens=5, overlap=0)
    assert len(result) >= 2
    assert "First sentence. " in result[0]
    assert "Second sentence." in result[-1]


def test_chunk_splits_on_newline():
    chunker = TokenChunker()
    text = "Line one\nLine two\nLine three"
    result = chunker.chunk(text, max_tokens=4, overlap=0)
    assert len(result) >= 2


def test_chunk_overlap():
    chunker = TokenChunker()
    # Build text with several short sentences.
    text = "AAA. BBB. CCC. DDD. EEE."
    # Small max_tokens forces multiple chunks; overlap re-includes tail.
    result = chunker.chunk(text, max_tokens=4, overlap=2)
    assert len(result) >= 2
    # At least one pair of consecutive chunks should share content.
    shared = False
    for i in range(len(result) - 1):
        if any(word in result[i + 1] for word in result[i].split()):
            shared = True
            break
    assert shared, "Expected overlap between consecutive chunks"


def test_chunk_no_overlap():
    chunker = TokenChunker()
    text = "AAA. BBB. CCC."
    result = chunker.chunk(text, max_tokens=3, overlap=0)
    assert len(result) >= 2


def test_chunk_large_max_tokens():
    chunker = TokenChunker()
    text = "Short text."
    result = chunker.chunk(text, max_tokens=10000)
    assert result == ["Short text."]


# ── InMemoryKnowledgePipeline ────────────────────────────────────────────


def test_pipeline_satisfies_protocol():
    chunker = TokenChunker()
    pipeline = InMemoryKnowledgePipeline(chunker)
    assert isinstance(pipeline, KnowledgePipeline)


async def test_ingest_returns_doc_id():
    chunker = TokenChunker()
    pipeline = InMemoryKnowledgePipeline(chunker)
    doc_id = await pipeline.ingest("Some content to store.")
    assert isinstance(doc_id, str)
    assert len(doc_id) > 0


async def test_ingest_stores_chunks():
    chunker = TokenChunker()
    pipeline = InMemoryKnowledgePipeline(chunker)
    doc_id = await pipeline.ingest("Some content to store.")
    assert doc_id in pipeline._documents
    assert len(pipeline._documents[doc_id]) >= 1


async def test_ingest_with_metadata():
    chunker = TokenChunker()
    pipeline = InMemoryKnowledgePipeline(chunker)
    doc_id = await pipeline.ingest(
        "Content with metadata.",
        metadata={"author": "test", "topic": "demo"},
    )
    chunk_ids = pipeline._documents[doc_id]
    for cid in chunk_ids:
        assert pipeline._chunk_metadata[cid]["author"] == "test"


async def test_query_returns_relevant_chunks():
    chunker = TokenChunker()
    pipeline = InMemoryKnowledgePipeline(chunker)
    await pipeline.ingest("Python is a programming language.")
    await pipeline.ingest("Java is also a programming language.")
    await pipeline.ingest("The weather is sunny today.")

    results = await pipeline.query("Python programming")
    assert len(results) >= 1
    assert isinstance(results[0], RetrievalResult)
    # The Python chunk should rank first.
    assert "Python" in results[0].content


async def test_query_ranked_by_score():
    chunker = TokenChunker()
    pipeline = InMemoryKnowledgePipeline(chunker)
    await pipeline.ingest("apple apple apple banana")
    await pipeline.ingest("apple banana banana banana")

    results = await pipeline.query("apple")
    assert len(results) >= 2
    # The chunk with more "apple" occurrences should rank higher.
    assert results[0].score >= results[1].score


async def test_query_limit_parameter():
    chunker = TokenChunker()
    pipeline = InMemoryKnowledgePipeline(chunker)
    for i in range(20):
        await pipeline.ingest(f"Document number {i} about testing.")

    results = await pipeline.query("testing", limit=5)
    assert len(results) == 5


async def test_query_no_results():
    chunker = TokenChunker()
    pipeline = InMemoryKnowledgePipeline(chunker)
    await pipeline.ingest("Python is great.")

    results = await pipeline.query("nonexistent-xyz-keyword")
    assert results == []


async def test_query_result_fields():
    chunker = TokenChunker()
    pipeline = InMemoryKnowledgePipeline(chunker)
    doc_id = await pipeline.ingest(
        "Machine learning is fascinating.",
        metadata={"source_url": "https://example.com"},
    )

    results = await pipeline.query("machine learning")
    assert len(results) >= 1
    r = results[0]
    assert r.content
    assert r.score > 0
    assert r.source == doc_id
    assert r.chunk_id
    assert r.metadata["source_url"] == "https://example.com"


async def test_multiple_documents_queried():
    chunker = TokenChunker()
    pipeline = InMemoryKnowledgePipeline(chunker)
    id1 = await pipeline.ingest("Alpha bravo charlie.")
    await pipeline.ingest("Delta echo foxtrot.")
    id3 = await pipeline.ingest("Alpha delta golf.")

    results = await pipeline.query("alpha")
    assert len(results) >= 2
    sources = {r.source for r in results}
    assert id1 in sources
    assert id3 in sources
