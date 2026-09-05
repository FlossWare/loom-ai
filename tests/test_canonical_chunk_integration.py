"""Integration tests proving the producer/consumer canonical chunk boundary.

Validates the canonical chunk contract between FlossWare/chunking and
FlossWare/loom-ai across model, storage, REST API, and retrieval boundaries.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from loom_ai.backends.memory import MemoryStorageBackend
from loom_ai.config import LoomConfig
from loom_ai.models import Chunk
from loom_ai.server import create_app


def _make_canonical_chunk_fixture(
    chunk_id: str = "canonical-chunk-001",
    document_id: str = "doc-canonical-100",
    sequence: int = 42,
    content: str = "Hello 🚀 world! 🌟 Canonical chunking test content.",
    token_count: int = 128,
    start_offset: int = 6,
    end_offset: int = 45,
    metadata: dict | None = None,
    provenance: dict | None = None,
) -> dict:
    """Return a dictionary representing a canonical chunk from FlossWare/chunking."""
    return {
        "id": chunk_id,
        "document_id": document_id,
        "sequence": sequence,
        "content": content,
        "token_count": token_count,
        "start_offset": start_offset,
        "end_offset": end_offset,
        "content_hash": "a1b2c3d4e5f60718",
        "metadata": metadata
        or {
            "section": "intro",
            "author": "alice",
            "importance": 0.95,
        },
        "provenance": provenance
        or {
            "source_uri": "https://example.com/doc1",
            "ingested_at": "2025-01-01T00:00:00Z",
            "pipeline_version": "v2.1.0",
        },
    }


@pytest.mark.asyncio
async def test_canonical_chunk_identity_preservation():
    """Verify that chunk ID is strictly preserved without re-indexing."""
    storage = MemoryStorageBackend()
    fixture = _make_canonical_chunk_fixture(chunk_id="canonical-chunk-001")

    chunk = Chunk(
        id=fixture["id"],
        document_id=fixture["document_id"],
        content=fixture["content"],
        chunk_index=fixture["sequence"],
        token_count=fixture["token_count"],
        start_offset=fixture["start_offset"],
        end_offset=fixture["end_offset"],
        metadata=fixture["metadata"],
        provenance=fixture["provenance"],
        content_hash=fixture["content_hash"],
    )

    await storage.store_chunks(fixture["document_id"], [chunk])
    stored = await storage.get_chunks(fixture["document_id"])

    assert len(stored) == 1
    assert stored[0].id == "canonical-chunk-001"


@pytest.mark.asyncio
async def test_canonical_chunk_sequence_preservation():
    """Verify that a non-zero, non-trivial sequence is preserved and not replaced with 0."""
    storage = MemoryStorageBackend()
    fixture = _make_canonical_chunk_fixture(sequence=42)

    chunk = Chunk(
        id=fixture["id"],
        document_id=fixture["document_id"],
        content=fixture["content"],
        chunk_index=fixture["sequence"],
        token_count=fixture["token_count"],
        start_offset=fixture["start_offset"],
        end_offset=fixture["end_offset"],
        metadata=fixture["metadata"],
        provenance=fixture["provenance"],
    )

    await storage.store_chunks(fixture["document_id"], [chunk])
    stored = await storage.get_chunks(fixture["document_id"])

    assert len(stored) == 1
    assert stored[0].chunk_index == 42
    assert stored[0].sequence == 42


@pytest.mark.asyncio
async def test_canonical_chunk_metadata_preservation():
    """Verify that multiple metadata fields survive storage and retrieval."""
    storage = MemoryStorageBackend()
    custom_metadata = {
        "heading": "Section 3.1",
        "tags": ["core", "pipeline"],
        "depth": 3,
    }
    fixture = _make_canonical_chunk_fixture(metadata=custom_metadata)

    chunk = Chunk(
        id=fixture["id"],
        document_id=fixture["document_id"],
        content=fixture["content"],
        chunk_index=fixture["sequence"],
        metadata=fixture["metadata"],
    )

    await storage.store_chunks(fixture["document_id"], [chunk])
    stored = await storage.get_chunks(fixture["document_id"])

    assert stored[0].metadata == custom_metadata


@pytest.mark.asyncio
async def test_canonical_chunk_provenance_preservation():
    """Verify that provenance tracking info survives storage intact."""
    storage = MemoryStorageBackend()
    custom_provenance = {
        "source_uri": "s3://bucket/docs/spec.pdf",
        "extractor": "pdfminer.six",
        "hash": "sha256:abc123xyz",
    }
    fixture = _make_canonical_chunk_fixture(provenance=custom_provenance)

    chunk = Chunk(
        id=fixture["id"],
        document_id=fixture["document_id"],
        content=fixture["content"],
        chunk_index=fixture["sequence"],
        provenance=fixture["provenance"],
    )

    await storage.store_chunks(fixture["document_id"], [chunk])
    stored = await storage.get_chunks(fixture["document_id"])

    assert stored[0].provenance == custom_provenance


@pytest.mark.asyncio
async def test_canonical_chunk_token_count_preservation():
    """Verify explicit token_count is preserved without recalculation."""
    storage = MemoryStorageBackend()
    fixture = _make_canonical_chunk_fixture(token_count=256)

    chunk = Chunk(
        id=fixture["id"],
        document_id=fixture["document_id"],
        content=fixture["content"],
        chunk_index=fixture["sequence"],
        token_count=256,
    )

    await storage.store_chunks(fixture["document_id"], [chunk])
    stored = await storage.get_chunks(fixture["document_id"])

    assert stored[0].token_count == 256


@pytest.mark.asyncio
async def test_canonical_chunk_offset_preservation():
    """Verify explicit start/end offsets are preserved intact."""
    storage = MemoryStorageBackend()
    fixture = _make_canonical_chunk_fixture(start_offset=1024, end_offset=2048)

    chunk = Chunk(
        id=fixture["id"],
        document_id=fixture["document_id"],
        content=fixture["content"],
        chunk_index=fixture["sequence"],
        start_offset=1024,
        end_offset=2048,
    )

    await storage.store_chunks(fixture["document_id"], [chunk])
    stored = await storage.get_chunks(fixture["document_id"])

    assert stored[0].start_offset == 1024
    assert stored[0].end_offset == 2048


def test_canonical_chunk_unicode_offset_semantics():
    """Verify Unicode content offset semantics against Python character offsets.

    In Python str and FlossWare/chunking contracts, offsets specify character code
    point indices into the document content string.
    """
    doc_content = (
        "Intro: Hello 🚀 world! 🌟 Canonical chunking test with multi-byte unicode."
    )
    # Slice character offsets:
    start_offset = 7
    end_offset = 21
    chunk_text = doc_content[start_offset:end_offset]

    assert chunk_text == "Hello 🚀 world!"

    chunk = Chunk(
        id="chunk-unicode-001",
        document_id="doc-unicode-1",
        content=chunk_text,
        chunk_index=1,
        start_offset=start_offset,
        end_offset=end_offset,
    )

    assert doc_content[chunk.start_offset : chunk.end_offset] == chunk.content


@pytest.mark.asyncio
async def test_multiple_chunks_no_renumbering():
    """Verify multiple chunks with non-trivial sequence numbers are not renumbered."""
    storage = MemoryStorageBackend()
    doc_id = "doc-multi-123"

    c1 = Chunk(
        id="canonical-chunk-010",
        document_id=doc_id,
        content="Chunk 10 content",
        chunk_index=10,
        token_count=15,
        start_offset=0,
        end_offset=16,
    )
    c2 = Chunk(
        id="canonical-chunk-025",
        document_id=doc_id,
        content="Chunk 25 content",
        chunk_index=25,
        token_count=15,
        start_offset=20,
        end_offset=36,
    )
    c3 = Chunk(
        id="canonical-chunk-005",
        document_id=doc_id,
        content="Chunk 5 content",
        chunk_index=5,
        token_count=15,
        start_offset=40,
        end_offset=55,
    )

    await storage.store_chunks(doc_id, [c1, c2, c3])
    stored = await storage.get_chunks(doc_id)

    # Sorted by chunk_index
    assert [c.id for c in stored] == [
        "canonical-chunk-005",
        "canonical-chunk-010",
        "canonical-chunk-025",
    ]
    assert [c.chunk_index for c in stored] == [5, 10, 25]


@pytest.mark.asyncio
async def test_rest_api_canonical_chunk_round_trip():
    """End-to-End REST round-trip test submitting canonical chunks via POST and retrieving via GET."""
    storage = MemoryStorageBackend()
    cfg = LoomConfig(
        storage=storage,
        queue=None,  # type: ignore[arg-type]
        secrets=None,  # type: ignore[arg-type]
        embedding=None,  # type: ignore[arg-type]
        search=None,  # type: ignore[arg-type]
    )

    app = create_app(cfg)
    client = TestClient(app)

    fixture1 = _make_canonical_chunk_fixture(
        chunk_id="chunk-rest-001",
        document_id="doc-rest-777",
        sequence=10,
        content="First canonical chunk in REST test.",
        token_count=50,
        start_offset=0,
        end_offset=35,
        metadata={"author": "alice"},
        provenance={"source": "api"},
    )
    fixture2 = _make_canonical_chunk_fixture(
        chunk_id="chunk-rest-002",
        document_id="doc-rest-777",
        sequence=20,
        content="Second canonical chunk in REST test.",
        token_count=60,
        start_offset=36,
        end_offset=72,
        metadata={"author": "bob"},
        provenance={"source": "scraper"},
    )

    store_resp = client.post(
        "/knowledge/chunks/store",
        json={"document_id": "doc-rest-777", "chunks": [fixture1, fixture2]},
    )

    assert store_resp.status_code == 200
    assert store_resp.json() == {"stored": 2, "total": 2}

    get_resp = client.get("/knowledge/documents/doc-rest-777/chunks")
    assert get_resp.status_code == 200

    data = get_resp.json()
    assert data["count"] == 2
    chunks = data["chunks"]

    c1 = chunks[0]
    assert c1["id"] == "chunk-rest-001"
    assert c1["document_id"] == "doc-rest-777"
    assert c1["chunk_index"] == 10
    assert c1["sequence"] == 10
    assert c1["content"] == "First canonical chunk in REST test."
    assert c1["token_count"] == 50
    assert c1["start_offset"] == 0
    assert c1["end_offset"] == 35
    assert c1["metadata"] == {"author": "alice"}
    assert c1["provenance"] == {"source": "api"}

    c2 = chunks[1]
    assert c2["id"] == "chunk-rest-002"
    assert c2["document_id"] == "doc-rest-777"
    assert c2["chunk_index"] == 20
    assert c2["sequence"] == 20
    assert c2["content"] == "Second canonical chunk in REST test."
    assert c2["token_count"] == 60
    assert c2["start_offset"] == 36
    assert c2["end_offset"] == 72
    assert c2["metadata"] == {"author": "bob"}
    assert c2["provenance"] == {"source": "scraper"}
