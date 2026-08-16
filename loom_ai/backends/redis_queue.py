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

import json
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    ) -> int:
        """Add items to the named queue.

        Items are placed in a sorted set scored by priority 0
        (lower = higher priority).

        Returns the number of items enqueued.
        """
        pipe = self._redis.pipeline()
        count = 0
        for item in items:
            item_id = item.id or uuid.uuid4().hex
            meta = {
                "id": item_id,
                "payload": json.dumps(item.payload),
                "priority": 0,
                "enqueued_at": item.enqueued_at or time.time(),
                "retry_count": 0,
                "worker_id": item.worker_id or "",
                "status": "pending",
            }
            pipe.hset(self._item_key(queue_name, item_id), mapping=meta)
            pipe.zadd(self._pending_key(queue_name), {item_id: 0})
            pipe.sadd(self._queues_key(), queue_name)
            count += 1
        pipe.execute()
        return count

    async def fetch(
        self,
        queue_name: str,
        count: int,
        worker_id: str,
    ) -> list[QueueItem]:
        """Claim up to *count* items for *worker_id*.

        Reclaims any items whose leases have expired before attempting to
        fetch new ones.  Returns a list of QueueItem instances.
        """
        from loom_ai.models import QueueItem as _QueueItem

        await self._reclaim_expired(queue_name)

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
            self._redis.zadd(self._processing_key(queue_name), {item_id: lease_expiry})
            self._redis.hset(
                self._item_key(queue_name, item_id),
                mapping={"worker_id": worker_id, "status": "processing"},
            )
            raw = self._redis.hgetall(self._item_key(queue_name, item_id))
            meta = self._decode_hash(raw)
            payload = json.loads(meta.get("payload", "{}"))
            fetched.append(
                _QueueItem(
                    id=meta.get("id", item_id),
                    payload=payload,
                    enqueued_at=float(meta.get("enqueued_at", 0.0)),
                    worker_id=meta.get("worker_id"),
                )
            )
        return fetched

    async def complete(self, queue_name: str, item_id: str) -> bool:
        """Mark an item as done and remove it from the processing set."""
        key = self._item_key(queue_name, item_id)
        if not self._redis.exists(key):
            return False
        self._redis.hset(key, mapping={"status": "completed"})
        self._redis.zrem(self._processing_key(queue_name), item_id)
        return True

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
                await self._dead_letter(queue_name, item_id, meta)
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

    async def status(self, queue_name: str) -> dict:
        """Return queue state counts."""
        pending = self._redis.zcard(self._pending_key(queue_name))
        processing = self._redis.zcard(self._processing_key(queue_name))
        dlq_len = self._redis.llen(self._dlq_key(queue_name))
        return {
            "queue": queue_name,
            "pending": pending,
            "processing": processing,
            "dead_letter": dlq_len,
        }

    async def list_queues(self) -> list[str]:
        """Return known queue names."""
        raw = self._redis.smembers(self._queues_key())
        return [m.decode() if isinstance(m, bytes) else str(m) for m in raw]

    # -- DLQ access ------------------------------------------------------

    async def dead_letter_items(self, queue_name: str) -> list[dict]:
        """Return all items in the dead-letter queue."""
        raw_items = self._redis.lrange(self._dlq_key(queue_name), 0, -1)
        return [
            json.loads(r.decode() if isinstance(r, bytes) else r) for r in raw_items
        ]

    # -- Lease reclamation -----------------------------------------------

    async def _reclaim_expired(self, queue_name: str) -> int:
        """Move expired leases back to the pending set.

        Returns the count of reclaimed items.
        """
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
                await self._dead_letter(queue_name, item_id, meta)
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

    # -- Dead-letter handling --------------------------------------------

    async def _dead_letter(self, queue_name: str, item_id: str, meta: dict) -> None:
        """Move an item to the dead-letter queue."""
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
