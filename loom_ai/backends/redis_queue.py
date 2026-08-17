"""Redis-backed durable queue backend for loom-ai.

Implements the :class:`~loom_ai.protocols.QueueBackend` protocol with:

* **Priorities** -- items carry an integer priority (lower = higher priority)
* **Lease-based processing** -- workers claim items with a timeout; unclaimed
  items are automatically reclaimed after the lease expires
* **Retry with exponential backoff** -- failed items are retried up to a
  configurable maximum
* **Dead-letter queue (DLQ)** -- items that exceed max retries move to a
  per-queue DLQ

The ``redis`` library import is guarded so the module can be imported
(and tested with mocks) without a running Redis server.

Classes
-------
RedisQueueBackend -- durable Redis queue with leases, priorities, and DLQ
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from loom_ai.models import QueueItem

try:
    import redis as _redis_lib  # noqa: F401

    _HAS_REDIS = True
except ImportError:
    _redis_lib = None  # type: ignore[assignment]
    _HAS_REDIS = False


class RedisQueueBackend:
    """Redis-backed durable task queue.

    Satisfies :class:`~loom_ai.protocols.QueueBackend` via structural
    subtyping.

    Parameters
    ----------
    redis_client:
        A ``redis.Redis`` (or compatible mock) instance.
    lease_timeout:
        Seconds before an in-flight item is reclaimed (default 300).
    max_retries:
        Maximum retry attempts before an item is dead-lettered (default 3).
    backoff_base:
        Base seconds for exponential backoff (default 2.0).
    key_prefix:
        Prefix for all Redis keys (default ``"loom:queue:"``).
    """

    def __init__(
        self,
        redis_client: object,
        *,
        lease_timeout: int = 300,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        key_prefix: str = "loom:queue:",
    ) -> None:
        self._redis = redis_client
        self._lease_timeout = lease_timeout
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._prefix = key_prefix

    # -- Key helpers -----------------------------------------------------

    def _pending_key(self, queue_name: str) -> str:
        """Sorted set of pending items (score = priority)."""
        return f"{self._prefix}{queue_name}:pending"

    def _processing_key(self, queue_name: str) -> str:
        """Sorted set of in-flight items (score = lease expiry timestamp)."""
        return f"{self._prefix}{queue_name}:processing"

    def _item_key(self, queue_name: str, item_id: str) -> str:
        """Hash key for item metadata."""
        return f"{self._prefix}{queue_name}:item:{item_id}"

    def _dlq_key(self, queue_name: str) -> str:
        """List key for dead-lettered items."""
        return f"{self._prefix}{queue_name}:dlq"

    def _queues_key(self) -> str:
        """Set tracking all known queue names."""
        return f"{self._prefix}queues"

    # -- QueueBackend protocol -------------------------------------------

    async def enqueue(
        self,
        queue_name: str,
        items: list[QueueItem],
        *,
        priority: int = 0,
    ) -> int:
        """Add items to the named queue.

        Each ``QueueItem`` should have a non-empty ``id``; one is generated
        if the id is empty.  Items are placed in a sorted set scored by
        *priority* (lower = higher priority).

        Returns the number of items enqueued.
        """

        def _sync() -> int:
            pipe = self._redis.pipeline()
            count = 0
            for item in items:
                item_id = item.id or uuid.uuid4().hex
                if not item.id:
                    item.id = item_id
                meta = {
                    "id": item_id,
                    "payload": json.dumps(item.payload),
                    "priority": priority,
                    "enqueued_at": item.enqueued_at or time.time(),
                    "retry_count": 0,
                    "worker_id": item.worker_id or "",
                    "status": "pending",
                }
                pipe.hset(self._item_key(queue_name, item_id), mapping=meta)
                pipe.zadd(self._pending_key(queue_name), {item_id: priority})
                pipe.sadd(self._queues_key(), queue_name)
                count += 1
            pipe.execute()
            return count

        return await asyncio.to_thread(_sync)

    async def fetch(
        self,
        queue_name: str,
        count: int,
        worker_id: str,
    ) -> list[QueueItem]:
        """Claim up to *count* items for *worker_id*.

        Reclaims any items whose leases have expired before attempting to
        fetch new ones.  Returns a list of ``QueueItem`` instances.
        """
        await self._reclaim_expired(queue_name)

        def _sync() -> list[QueueItem]:
            fetched: list[QueueItem] = []
            for _ in range(count):
                result = self._redis.zpopmin(self._pending_key(queue_name))
                if not result:
                    break
                item_id_raw, _score = result[0]
                item_id = (
                    item_id_raw.decode()
                    if isinstance(item_id_raw, bytes)
                    else str(item_id_raw)
                )

                lease_expiry = time.time() + self._lease_timeout
                self._redis.zadd(
                    self._processing_key(queue_name), {item_id: lease_expiry}
                )
                self._redis.hset(
                    self._item_key(queue_name, item_id),
                    mapping={"worker_id": worker_id, "status": "processing"},
                )
                raw = self._redis.hgetall(self._item_key(queue_name, item_id))
                meta = self._decode_hash(raw)
                qi = QueueItem(
                    id=meta.get("id", item_id),
                    payload=json.loads(meta.get("payload", "{}")),
                    enqueued_at=float(meta.get("enqueued_at", 0.0)),
                    worker_id=meta.get("worker_id"),
                )
                fetched.append(qi)
            return fetched

        return await asyncio.to_thread(_sync)

    async def complete(self, queue_name: str, item_id: str) -> bool:
        """Mark an item as done and remove it from the processing set."""

        def _sync() -> bool:
            key = self._item_key(queue_name, item_id)
            if not self._redis.exists(key):
                return False
            self._redis.hset(key, mapping={"status": "completed"})
            self._redis.zrem(self._processing_key(queue_name), item_id)
            return True

        return await asyncio.to_thread(_sync)

    async def requeue(
        self,
        queue_name: str,
        items: list[QueueItem],
    ) -> int:
        """Return items to the queue for retry.

        Increments each item's retry count.  Items exceeding
        ``max_retries`` are moved to the dead-letter queue instead.
        Returns the number of items requeued (excludes dead-lettered).
        """

        def _sync() -> int:
            requeued = 0
            for item in items:
                item_id = item.id
                if not item_id:
                    continue
                key = self._item_key(queue_name, item_id)
                raw = self._redis.hgetall(key)
                if not raw:
                    continue
                meta = self._decode_hash(raw)
                retry_count = int(meta.get("retry_count", 0)) + 1

                if retry_count > self._max_retries:
                    self._dead_letter_sync(queue_name, item_id, meta)
                else:
                    priority = int(meta.get("priority", 0))
                    backoff = self._backoff_base**retry_count
                    adjusted_priority = priority + int(backoff)
                    self._redis.hset(
                        key,
                        mapping={
                            "retry_count": retry_count,
                            "status": "pending",
                            "worker_id": "",
                        },
                    )
                    self._redis.zrem(self._processing_key(queue_name), item_id)
                    self._redis.zadd(
                        self._pending_key(queue_name),
                        {item_id: adjusted_priority},
                    )
                    requeued += 1
            return requeued

        return await asyncio.to_thread(_sync)

    async def status(self, queue_name: str) -> dict:
        """Return queue state counts."""

        def _sync() -> dict:
            pending = self._redis.zcard(self._pending_key(queue_name))
            processing = self._redis.zcard(self._processing_key(queue_name))
            dlq_len = self._redis.llen(self._dlq_key(queue_name))
            return {
                "queue": queue_name,
                "pending": pending,
                "processing": processing,
                "dead_letter": dlq_len,
            }

        return await asyncio.to_thread(_sync)

    async def list_queues(self) -> list[str]:
        """Return known queue names."""

        def _sync() -> list[str]:
            raw = self._redis.smembers(self._queues_key())
            return [m.decode() if isinstance(m, bytes) else str(m) for m in raw]

        return await asyncio.to_thread(_sync)

    # -- DLQ access ------------------------------------------------------

    async def dead_letter_items(self, queue_name: str) -> list[dict]:
        """Return all items in the dead-letter queue."""

        def _sync() -> list[dict]:
            raw_items = self._redis.lrange(self._dlq_key(queue_name), 0, -1)
            return [
                json.loads(r.decode() if isinstance(r, bytes) else r) for r in raw_items
            ]

        return await asyncio.to_thread(_sync)

    # -- Lease reclamation -----------------------------------------------

    async def _reclaim_expired(self, queue_name: str) -> int:
        """Move expired leases back to the pending set.

        Returns the count of reclaimed items.
        """

        def _sync() -> int:
            now = time.time()
            expired = self._redis.zrangebyscore(
                self._processing_key(queue_name), "-inf", now
            )
            reclaimed = 0
            for raw_id in expired:
                item_id = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
                key = self._item_key(queue_name, item_id)
                meta = self._decode_hash(self._redis.hgetall(key))
                retry_count = int(meta.get("retry_count", 0)) + 1

                if retry_count > self._max_retries:
                    self._dead_letter_sync(queue_name, item_id, meta)
                else:
                    priority = int(meta.get("priority", 0))
                    self._redis.hset(
                        key,
                        mapping={
                            "retry_count": retry_count,
                            "status": "pending",
                            "worker_id": "",
                        },
                    )
                    self._redis.zadd(self._pending_key(queue_name), {item_id: priority})
                self._redis.zrem(self._processing_key(queue_name), item_id)
                reclaimed += 1
            return reclaimed

        return await asyncio.to_thread(_sync)

    # -- Dead-letter handling --------------------------------------------

    def _dead_letter_sync(self, queue_name: str, item_id: str, meta: dict) -> None:
        """Move an item to the dead-letter queue (synchronous helper).

        Called from within ``asyncio.to_thread`` blocks so all Redis I/O
        stays off the event loop.
        """
        meta["status"] = "dead_letter"
        meta["dead_lettered_at"] = time.time()
        key = self._item_key(queue_name, item_id)
        self._redis.hset(key, mapping={"status": "dead_letter"})
        self._redis.zrem(self._processing_key(queue_name), item_id)
        self._redis.rpush(self._dlq_key(queue_name), json.dumps(meta))

    # -- Helpers ---------------------------------------------------------

    @staticmethod
    def _decode_hash(raw: dict) -> dict:
        """Decode bytes keys/values from hgetall to str."""
        return {
            (k.decode() if isinstance(k, bytes) else k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in raw.items()
        }
