"""Property-based fuzz tests for QueueBackend (MemoryQueueBackend).

Uses Hypothesis to generate edge-case inputs and verifies that queue
operations never crash with valid-typed but unusual inputs, maintain FIFO
ordering, and handle concurrent access without corruption.
"""

from __future__ import annotations

import asyncio

from hypothesis import given, settings
from hypothesis import strategies as st

from loom_ai.backends.memory import MemoryQueueBackend
from loom_ai.models import QueueItem


def _run(coro):
    return asyncio.run(coro)


FUZZ_TEXT = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "M", "N", "P", "S", "Z")),
    min_size=0,
    max_size=5000,
)

FUZZ_ID = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=200,
)

FUZZ_QUEUE_NAME = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "N", "P")),
    min_size=1,
    max_size=100,
)


class TestQueueFuzz:
    @given(queue_name=FUZZ_QUEUE_NAME, item_id=FUZZ_ID)
    @settings(max_examples=100, deadline=None)
    def test_enqueue_and_fetch_never_crashes(self, queue_name, item_id):
        backend = MemoryQueueBackend()
        item = QueueItem(id=item_id, payload={"data": "test"})
        count = _run(backend.enqueue(queue_name, [item]))
        assert count == 1

        fetched = _run(backend.fetch(queue_name, 1, "worker-fuzz"))
        assert len(fetched) == 1
        assert fetched[0].id == item_id

    @given(queue_name=FUZZ_QUEUE_NAME, n=st.integers(min_value=1, max_value=50))
    @settings(max_examples=50, deadline=None)
    def test_fifo_preserved_with_fuzz_names(self, queue_name, n):
        backend = MemoryQueueBackend()
        items = [QueueItem(id=f"fifo-{i}", payload={"i": i}) for i in range(n)]
        _run(backend.enqueue(queue_name, items))

        fetched = _run(backend.fetch(queue_name, n, "w"))
        assert [f.id for f in fetched] == [f"fifo-{i}" for i in range(n)]

    @given(queue_name=FUZZ_QUEUE_NAME, item_id=FUZZ_ID)
    @settings(max_examples=50, deadline=None)
    def test_complete_after_fetch(self, queue_name, item_id):
        backend = MemoryQueueBackend()
        _run(backend.enqueue(queue_name, [QueueItem(id=item_id, payload={})]))
        _run(backend.fetch(queue_name, 1, "w"))

        ok = _run(backend.complete(queue_name, item_id))
        assert ok is True

        status = _run(backend.status(queue_name))
        assert status["pending"] == 0
        assert status["processing"] == 0

    @given(queue_name=FUZZ_QUEUE_NAME, item_id=FUZZ_ID)
    @settings(max_examples=50, deadline=None)
    def test_complete_unfetched_returns_false(self, queue_name, item_id):
        backend = MemoryQueueBackend()
        ok = _run(backend.complete(queue_name, item_id))
        assert ok is False

    @given(queue_name=FUZZ_QUEUE_NAME)
    @settings(max_examples=50, deadline=None)
    def test_fetch_empty_queue_returns_empty(self, queue_name):
        backend = MemoryQueueBackend()
        fetched = _run(backend.fetch(queue_name, 10, "w"))
        assert fetched == []

    @given(queue_name=FUZZ_QUEUE_NAME, item_id=FUZZ_ID)
    @settings(max_examples=50, deadline=None)
    def test_requeue_returns_item_to_queue(self, queue_name, item_id):
        backend = MemoryQueueBackend()
        item = QueueItem(id=item_id, payload={"retry": True})
        _run(backend.enqueue(queue_name, [item]))

        fetched = _run(backend.fetch(queue_name, 1, "w1"))
        assert len(fetched) == 1

        requeued = _run(backend.requeue(queue_name, fetched))
        assert requeued == 1

        refetched = _run(backend.fetch(queue_name, 1, "w2"))
        assert len(refetched) == 1
        assert refetched[0].id == item_id

    @given(queue_name=FUZZ_QUEUE_NAME)
    @settings(max_examples=50, deadline=None)
    def test_status_on_fresh_queue(self, queue_name):
        backend = MemoryQueueBackend()
        status = _run(backend.status(queue_name))
        assert status["pending"] == 0
        assert status["processing"] == 0
        assert status["dead_letter"] == 0

    @given(queue_names=st.lists(FUZZ_QUEUE_NAME, min_size=1, max_size=10, unique=True))
    @settings(max_examples=50, deadline=None)
    def test_list_queues_after_enqueue(self, queue_names):
        backend = MemoryQueueBackend()
        for name in queue_names:
            _run(backend.enqueue(name, [QueueItem(id="x", payload={})]))

        listed = _run(backend.list_queues())
        for name in queue_names:
            assert name in listed

    @given(
        count=st.integers(min_value=0, max_value=100),
        request_count=st.integers(min_value=0, max_value=200),
    )
    @settings(max_examples=50, deadline=None)
    def test_fetch_count_capped_at_available(self, count, request_count):
        backend = MemoryQueueBackend()
        items = [QueueItem(id=f"cap-{i}", payload={}) for i in range(count)]
        if items:
            _run(backend.enqueue("capped", items))

        fetched = _run(backend.fetch("capped", request_count, "w"))
        assert len(fetched) <= count
        assert len(fetched) <= max(request_count, 0)


class TestQueueConcurrency:
    async def test_concurrent_enqueue_preserves_all_items(self):
        backend = MemoryQueueBackend()

        async def enqueue_batch(start):
            items = [
                QueueItem(id=f"par-{i}", payload={}) for i in range(start, start + 10)
            ]
            await backend.enqueue("parallel", items)

        await asyncio.gather(*(enqueue_batch(i * 10) for i in range(5)))

        status = await backend.status("parallel")
        assert status["pending"] == 50

    async def test_concurrent_fetch_no_duplicate_claims(self):
        backend = MemoryQueueBackend()
        items = [QueueItem(id=f"dup-{i}", payload={}) for i in range(20)]
        await backend.enqueue("dedup", items)

        results = await asyncio.gather(
            backend.fetch("dedup", 10, "w1"),
            backend.fetch("dedup", 10, "w2"),
        )

        all_fetched = results[0] + results[1]
        ids = [item.id for item in all_fetched]
        assert len(ids) == len(set(ids))
        assert len(ids) == 20
