"""Benchmark suite for QueueBackend implementations.

Compares MemoryQueueBackend throughput for enqueue, fetch, and complete.
"""

from __future__ import annotations

import pytest

from loom_ai.backends.memory import MemoryQueueBackend
from loom_ai.models import QueueItem


@pytest.fixture
def backend():
    return MemoryQueueBackend()


@pytest.mark.benchmark(group="queue-enqueue")
def test_bench_enqueue(benchmark, backend):
    items = [QueueItem(id=f"item-{i}", payload={"n": i}) for i in range(50)]

    async def _run():
        await backend.enqueue("bench", items)

    benchmark(lambda: __import__("asyncio").run(_run()))


@pytest.mark.benchmark(group="queue-fetch")
def test_bench_fetch(benchmark, backend):
    async def _setup():
        items = [QueueItem(id=f"item-{i}", payload={"n": i}) for i in range(50)]
        await backend.enqueue("bench", items)

    __import__("asyncio").run(_setup())

    async def _run():
        await backend.fetch("bench", 10, "worker-1")

    benchmark(lambda: __import__("asyncio").run(_run()))


@pytest.mark.benchmark(group="queue-status")
def test_bench_status(benchmark, backend):
    async def _run():
        await backend.status("bench")

    benchmark(lambda: __import__("asyncio").run(_run()))
