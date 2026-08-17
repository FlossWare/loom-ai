"""Benchmarks for MemoryQueueBackend operations."""

from __future__ import annotations

import asyncio

import pytest

from loom_ai.backends.memory import MemoryQueueBackend
from loom_ai.models import QueueItem

SIZES = [10, 100, 1000]


def _make_items(n: int) -> list[QueueItem]:
    return [
        QueueItem(id=f"item-{i}", payload={"task": f"work-{i}"})
        for i in range(n)
    ]


@pytest.mark.parametrize("size", SIZES)
def test_enqueue(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryQueueBackend()
    items = _make_items(size)

    def run():
        loop.run_until_complete(backend.enqueue("bench-q", items))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_dequeue(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryQueueBackend()

    def run():
        loop.run_until_complete(backend.enqueue("bench-q", _make_items(size)))
        loop.run_until_complete(backend.fetch("bench-q", size, "worker-1"))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_peek_status(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryQueueBackend()
    loop.run_until_complete(backend.enqueue("bench-q", _make_items(size)))

    def run():
        loop.run_until_complete(backend.status("bench-q"))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_complete(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryQueueBackend()

    def run():
        items = _make_items(size)
        loop.run_until_complete(backend.enqueue("bench-q", items))
        loop.run_until_complete(backend.fetch("bench-q", size, "worker-1"))
        for item in items:
            loop.run_until_complete(backend.complete("bench-q", item.id))

    benchmark(run)
    loop.close()
