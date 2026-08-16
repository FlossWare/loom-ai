"""Conformance tests for QueueBackend implementations.

Any backend that satisfies the QueueBackend protocol should pass all
tests in this module.  Override the ``queue_backend`` fixture in a
downstream ``conftest.py`` to plug in a different implementation.
"""

from __future__ import annotations

from loom_ai import QueueItem


async def test_enqueue_and_fetch(queue_backend):
    """Enqueued items can be fetched by a worker."""
    items = [QueueItem(id="q-1", payload={"task": "embed"})]
    count = await queue_backend.enqueue("work", items)
    assert count == 1

    fetched = await queue_backend.fetch("work", 1, "worker-A")
    assert len(fetched) == 1
    assert fetched[0].id == "q-1"
    assert fetched[0].worker_id == "worker-A"


async def test_fifo_ordering(queue_backend):
    """Items are fetched in FIFO order."""
    items = [QueueItem(id=f"fifo-{i}", payload={"order": i}) for i in range(5)]
    await queue_backend.enqueue("ordered", items)

    fetched = await queue_backend.fetch("ordered", 5, "w")
    ids = [item.id for item in fetched]
    assert ids == [f"fifo-{i}" for i in range(5)]


async def test_complete_marks_item_done(queue_backend):
    """Completing an item removes it from the processing set."""
    items = [QueueItem(id="done-1", payload={})]
    await queue_backend.enqueue("completion", items)

    fetched = await queue_backend.fetch("completion", 1, "w")
    assert len(fetched) == 1

    ok = await queue_backend.complete("completion", "done-1")
    assert ok is True

    status = await queue_backend.status("completion")
    assert status["processing"] == 0


async def test_complete_unknown_item_returns_false(queue_backend):
    """Completing an item that was never fetched returns False."""
    result = await queue_backend.complete("empty-q", "no-such-item")
    assert result is False


async def test_requeue_items(queue_backend):
    """Requeuing items returns them to the queue for retry."""
    items = [QueueItem(id="rq-1", payload={"attempt": 1})]
    await queue_backend.enqueue("retry", items)

    fetched = await queue_backend.fetch("retry", 1, "w")
    assert len(fetched) == 1

    requeued = await queue_backend.requeue("retry", fetched)
    assert requeued == 1

    # Should be fetchable again
    refetched = await queue_backend.fetch("retry", 1, "w2")
    assert len(refetched) == 1
    assert refetched[0].id == "rq-1"


async def test_empty_queue_returns_empty_list(queue_backend):
    """Fetching from an empty queue returns an empty list."""
    fetched = await queue_backend.fetch("empty", 10, "w")
    assert fetched == []


async def test_queue_status(queue_backend):
    """Status reports queued and processing counts."""
    items = [QueueItem(id=f"st-{i}", payload={}) for i in range(3)]
    await queue_backend.enqueue("status-q", items)

    status = await queue_backend.status("status-q")
    assert status["queued"] == 3
    assert status["processing"] == 0

    await queue_backend.fetch("status-q", 2, "w")
    status = await queue_backend.status("status-q")
    assert status["queued"] == 1
    assert status["processing"] == 2


async def test_list_queues(queue_backend):
    """list_queues returns names of all known queues."""
    await queue_backend.enqueue("alpha", [QueueItem(id="a1", payload={})])
    await queue_backend.enqueue("beta", [QueueItem(id="b1", payload={})])

    names = await queue_backend.list_queues()
    assert "alpha" in names
    assert "beta" in names
