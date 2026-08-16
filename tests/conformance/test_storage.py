"""Conformance tests for StorageBackend implementations.

Any backend that satisfies the StorageBackend protocol should pass all
tests in this module.  Override the ``storage_backend`` fixture in a
downstream ``conftest.py`` to plug in a different implementation.
"""

from __future__ import annotations

from loom_ai import Chunk, Document

# -- Document CRUD -----------------------------------------------------------


async def test_store_and_retrieve_document(storage_backend):
    """Storing a document and retrieving it by id returns the same data."""
    doc = Document(id="doc-1", title="Hello", content="World")
    doc_id = await storage_backend.store_document(doc)

    assert doc_id == "doc-1"

    retrieved = await storage_backend.get_document("doc-1")
    assert retrieved is not None
    assert retrieved.id == "doc-1"
    assert retrieved.title == "Hello"
    assert retrieved.content == "World"


async def test_get_missing_document_returns_none(storage_backend):
    """Requesting a non-existent document returns None."""
    result = await storage_backend.get_document("does-not-exist")
    assert result is None


async def test_idempotent_store_document(storage_backend):
    """Storing the same document twice yields exactly one record (upsert)."""
    doc = Document(id="idem-1", title="First", content="A")
    await storage_backend.store_document(doc)
    await storage_backend.store_document(doc)

    count = await storage_backend.count_documents()
    assert count == 1


async def test_idempotent_store_updates_content(storage_backend):
    """Re-storing a document with the same id replaces the content."""
    doc_v1 = Document(id="idem-2", title="V1", content="original")
    doc_v2 = Document(id="idem-2", title="V2", content="updated")

    await storage_backend.store_document(doc_v1)
    await storage_backend.store_document(doc_v2)

    retrieved = await storage_backend.get_document("idem-2")
    assert retrieved is not None
    assert retrieved.title == "V2"
    assert retrieved.content == "updated"


async def test_multiple_documents(storage_backend):
    """Storing several documents and listing them returns all of them."""
    for i in range(5):
        doc = Document(id=f"multi-{i}", title=f"Doc {i}", content=f"body {i}")
        await storage_backend.store_document(doc)

    count = await storage_backend.count_documents()
    assert count == 5

    docs = await storage_backend.list_documents(limit=10)
    assert len(docs) == 5


async def test_delete_document(storage_backend):
    """Deleting a document removes it from the store."""
    doc = Document(id="del-1", title="Bye", content="Gone")
    await storage_backend.store_document(doc)

    deleted = await storage_backend.delete_document("del-1")
    assert deleted is True

    assert await storage_backend.get_document("del-1") is None
    assert await storage_backend.count_documents() == 0


async def test_delete_missing_document_returns_false(storage_backend):
    """Deleting a non-existent document returns False."""
    result = await storage_backend.delete_document("no-such-doc")
    assert result is False


# -- Chunks ------------------------------------------------------------------


async def test_store_and_retrieve_chunks(storage_backend):
    """Storing chunks for a document and retrieving them round-trips."""
    doc = Document(id="cdoc-1", title="With Chunks", content="Full text")
    await storage_backend.store_document(doc)

    chunks = [
        Chunk(id="c-0", document_id="cdoc-1", content="part 0", chunk_index=0),
        Chunk(id="c-1", document_id="cdoc-1", content="part 1", chunk_index=1),
    ]
    stored = await storage_backend.store_chunks("cdoc-1", chunks)
    assert stored == 2

    retrieved = await storage_backend.get_chunks("cdoc-1")
    assert len(retrieved) == 2
    assert retrieved[0].chunk_index <= retrieved[1].chunk_index


async def test_store_chunks_idempotent(storage_backend):
    """Re-storing the same chunks does not create duplicates."""
    doc = Document(id="cdoc-idem", title="Idem", content="body")
    await storage_backend.store_document(doc)

    chunk = Chunk(id="ci-1", document_id="cdoc-idem", content="v1", chunk_index=0)
    await storage_backend.store_chunks("cdoc-idem", [chunk])
    await storage_backend.store_chunks("cdoc-idem", [chunk])

    retrieved = await storage_backend.get_chunks("cdoc-idem")
    assert len(retrieved) == 1


async def test_get_chunks_batch(storage_backend):
    """get_chunks_batch returns chunks for the given ids."""
    doc = Document(id="batch-doc", title="Batch", content="body")
    await storage_backend.store_document(doc)

    chunks = [
        Chunk(id=f"bc-{i}", document_id="batch-doc", content=f"p{i}", chunk_index=i)
        for i in range(3)
    ]
    await storage_backend.store_chunks("batch-doc", chunks)

    batch = await storage_backend.get_chunks_batch(["bc-0", "bc-2"])
    assert len(batch) == 2
    ids = {c.id for c in batch}
    assert ids == {"bc-0", "bc-2"}


async def test_count_chunks(storage_backend):
    """count_chunks returns the total across all documents."""
    doc = Document(id="cnt-doc", title="Count", content="body")
    await storage_backend.store_document(doc)

    chunks = [
        Chunk(id=f"cnt-{i}", document_id="cnt-doc", content=f"c{i}", chunk_index=i)
        for i in range(4)
    ]
    await storage_backend.store_chunks("cnt-doc", chunks)

    assert await storage_backend.count_chunks() == 4
