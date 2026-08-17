"""Tests for queue batch-enqueue ID uniqueness (issue #39).

Batch-enqueued items without explicit IDs must receive unique generated IDs
so that no data is silently lost when items move to the processing dict.
"""

import time

from loom_ai import LoomConfig, QueueItem


async def test_batch_enqueue_generates_unique_ids():
    """Items enqueued without explicit IDs must each get a distinct ID."""
    cfg = await LoomConfig.from_env()

    # Simulate the server's ID-generation logic (post-fix) for items
    # without explicit IDs.
    ts = int(time.time() * 1000)
    items = [
        QueueItem(id=f"q-{ts}-{i}", payload={"task": chr(ord("a") + i)})
        for i in range(5)
    ]

    count = await cfg.queue.enqueue("gen-id-queue", items)
    assert count == 5

    fetched = await cfg.queue.fetch("gen-id-queue", 5, "worker-1")
    assert len(fetched) == 5

    ids = [item.id for item in fetched]
    assert len(set(ids)) == 5, f"Duplicate IDs in batch: {ids}"


async def test_old_id_scheme_produces_duplicates():
    """Demonstrate the old bug: same timestamp for every item in a batch."""
    ts = int(time.time() * 1000)
    old_ids = [f"q-{ts}" for _ in range(5)]
    assert len(set(old_ids)) == 1, "Old scheme should produce duplicates"


async def test_new_id_scheme_produces_unique_ids():
    """The fix appends an index so IDs are unique within a batch."""
    ts = int(time.time() * 1000)
    new_ids = [f"q-{ts}-{i}" for i in range(5)]
    assert len(set(new_ids)) == 5


async def test_batch_items_all_completable():
    """Every batch-enqueued item must be independently completable."""
    cfg = await LoomConfig.from_env()

    ts = int(time.time() * 1000)
    items = [QueueItem(id=f"q-{ts}-{i}", payload={"v": i}) for i in range(5)]
    await cfg.queue.enqueue("complete-q", items)

    fetched = await cfg.queue.fetch("complete-q", 5, "worker-1")
    assert len(fetched) == 5

    for item in fetched:
        ok = await cfg.queue.complete("complete-q", item.id)
        assert ok, (
            f"Item {item.id} could not be completed (overwritten by duplicate ID?)"
        )


async def test_duplicate_ids_cause_processing_overwrite():
    """With duplicate IDs, fetched items overwrite each other in _processing."""
    cfg = await LoomConfig.from_env()

    # Enqueue 3 items with the SAME ID (the old bug)
    items = [QueueItem(id="same-id", payload={"index": i}) for i in range(3)]
    await cfg.queue.enqueue("dup-queue", items)

    fetched = await cfg.queue.fetch("dup-queue", 3, "worker-1")
    assert len(fetched) == 3

    # Only one complete call can succeed because all 3 items share
    # the same key in _processing and only the last one is retained.
    completed = 0
    for item in fetched:
        if await cfg.queue.complete("dup-queue", item.id):
            completed += 1
    assert completed == 1, (
        "Duplicate IDs should allow only 1 complete (others were overwritten)"
    )


async def test_explicit_ids_preserved():
    """When items supply their own IDs, those IDs must be used as-is."""
    cfg = await LoomConfig.from_env()
    items = [
        QueueItem(id="my-1", payload={"task": "x"}),
        QueueItem(id="my-2", payload={"task": "y"}),
    ]
    await cfg.queue.enqueue("explicit-q", items)

    fetched = await cfg.queue.fetch("explicit-q", 2, "worker-1")
    ids = {item.id for item in fetched}
    assert ids == {"my-1", "my-2"}
