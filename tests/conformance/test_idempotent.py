"""Conformance tests for IdempotentStore implementations.

Any backend that satisfies the IdempotentStore protocol should pass all
tests in this module.  The tests verify the idempotent contract using
the in-memory storage backend by default.  Override the
``storage_backend`` fixture to test other implementations.
"""

from __future__ import annotations

from loom_ai.models import Document
from loom_ai.protocols import IdempotentStore

# -- is_idempotent property ------------------------------------------------


async def test_is_idempotent_returns_true(storage_backend):
    """Backends satisfying IdempotentStore report is_idempotent as True."""
    assert isinstance(storage_backend, IdempotentStore)
    assert storage_backend.is_idempotent is True


# -- repeated writes produce same state ------------------------------------


async def test_repeated_store_document_no_duplicates(storage_backend):
    """Storing the same document twice does not create a duplicate."""
    doc = Document(id="idem-doc-1", title="First", content="body")

    await storage_backend.store_document(doc)
    await storage_backend.store_document(doc)

    count = await storage_backend.count_documents()
    assert count == 1


async def test_repeated_store_document_returns_same_id(storage_backend):
    """Storing the same document twice returns the same id both times."""
    doc = Document(id="idem-doc-2", title="Test", content="content")

    id_first = await storage_backend.store_document(doc)
    id_second = await storage_backend.store_document(doc)

    assert id_first == id_second


async def test_repeated_store_document_preserves_latest(storage_backend):
    """Re-storing a document with updated content uses the latest values."""
    doc_v1 = Document(id="idem-doc-3", title="V1", content="old")
    doc_v2 = Document(id="idem-doc-3", title="V2", content="new")

    await storage_backend.store_document(doc_v1)
    await storage_backend.store_document(doc_v2)

    retrieved = await storage_backend.get_document("idem-doc-3")
    assert retrieved is not None
    assert retrieved.title == "V2"
    assert retrieved.content == "new"

    count = await storage_backend.count_documents()
    assert count == 1


async def test_idempotent_store_safe_retry(storage_backend):
    """Multiple identical writes are safe to retry without side effects."""
    doc = Document(id="retry-doc", title="Retry", content="safe")

    for _ in range(5):
        await storage_backend.store_document(doc)

    count = await storage_backend.count_documents()
    assert count == 1

    retrieved = await storage_backend.get_document("retry-doc")
    assert retrieved is not None
    assert retrieved.title == "Retry"
