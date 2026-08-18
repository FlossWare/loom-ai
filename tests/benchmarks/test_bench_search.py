"""Benchmarks for MemorySearchBackend operations."""

from __future__ import annotations

import asyncio
import math

import pytest

from loom_ai.backends.memory import MemorySearchBackend
from loom_ai.models import Chunk

SIZES = [10, 100, 1000]


def _make_chunk(i: int) -> Chunk:
    return Chunk(
        id=f"chunk-{i}",
        document_id=f"doc-{i % 10}",
        content=f"The quick brown fox jumps over item number {i}",
        chunk_index=i,
    )


def _make_vector(i: int, dims: int = 128) -> list[float]:
    return [math.sin(i + d) for d in range(dims)]


@pytest.mark.parametrize("size", SIZES)
def test_index(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemorySearchBackend()
    chunks = [_make_chunk(i) for i in range(size)]
    vectors = [_make_vector(i) for i in range(size)]

    def run():
        for chunk, vec in zip(chunks, vectors):
            loop.run_until_complete(
                backend.index(chunk, vec, document_title=f"Doc {chunk.chunk_index}")
            )

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_text_search(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemorySearchBackend()
    for i in range(size):
        loop.run_until_complete(backend.index(_make_chunk(i), _make_vector(i)))

    def run():
        loop.run_until_complete(backend.text_search("fox", limit=10))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_semantic_search(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemorySearchBackend()
    for i in range(size):
        loop.run_until_complete(backend.index(_make_chunk(i), _make_vector(i)))
    query_vector = _make_vector(size // 2)

    def run():
        loop.run_until_complete(backend.semantic_search(query_vector, limit=10))

    benchmark(run)
    loop.close()
