"""Benchmarks for MemoryStorageBackend operations."""

from __future__ import annotations

import asyncio

import pytest

from loom_ai.backends.memory import MemoryStorageBackend
from loom_ai.models import Chunk, Document

SIZES = [10, 100, 1000]


def _make_doc(i: int) -> Document:
    return Document(
        id=f"doc-{i}",
        title=f"Document {i}",
        content=f"Content for document {i}",
        url=f"https://example.com/{i}",
        category="bench",
    )


def _make_chunks(doc_id: str, n: int) -> list[Chunk]:
    return [
        Chunk(
            id=f"{doc_id}-chunk-{j}",
            document_id=doc_id,
            content=f"Chunk {j} of {doc_id}",
            chunk_index=j,
        )
        for j in range(n)
    ]


@pytest.mark.parametrize("size", SIZES)
def test_store_documents(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryStorageBackend()
    docs = [_make_doc(i) for i in range(size)]

    def run():
        for doc in docs:
            loop.run_until_complete(backend.store_document(doc))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_get_document(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryStorageBackend()
    for i in range(size):
        loop.run_until_complete(backend.store_document(_make_doc(i)))

    def run():
        loop.run_until_complete(backend.get_document(f"doc-{size // 2}"))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_list_documents(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryStorageBackend()
    for i in range(size):
        loop.run_until_complete(backend.store_document(_make_doc(i)))

    def run():
        loop.run_until_complete(backend.list_documents(limit=50))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_delete_document(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryStorageBackend()

    def run():
        for i in range(size):
            loop.run_until_complete(backend.store_document(_make_doc(i)))
        for i in range(size):
            loop.run_until_complete(backend.delete_document(f"doc-{i}"))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_store_chunks(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryStorageBackend()
    loop.run_until_complete(backend.store_document(_make_doc(0)))
    chunks = _make_chunks("doc-0", size)

    def run():
        loop.run_until_complete(backend.store_chunks("doc-0", chunks))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_count_documents(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryStorageBackend()
    for i in range(size):
        loop.run_until_complete(backend.store_document(_make_doc(i)))

    def run():
        loop.run_until_complete(backend.count_documents())

    benchmark(run)
    loop.close()
