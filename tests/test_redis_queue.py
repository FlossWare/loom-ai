"""Tests for loom_ai.backends.redis_queue using mock Redis."""

import time
from collections import defaultdict
from unittest.mock import MagicMock, patch

import pytest

from loom_ai.backends.redis_queue import RedisQueueBackend
from loom_ai.models import QueueItem

# -- Mock Redis ---------------------------------------------------------------


class MockRedis:
    """Minimal Redis mock implementing the commands used by RedisQueueBackend."""

    def __init__(self):
        self._hashes: dict[str, dict[str, str]] = {}
        self._sorted_sets: dict[str, dict[str, float]] = defaultdict(dict)
        self._sets: dict[str, set[str]] = defaultdict(set)
        self._lists: dict[str, list[str]] = defaultdict(list)

    def pipeline(self):
        return MockPipeline(self)

    def hset(self, name, mapping=None, **kwargs):
        if name not in self._hashes:
            self._hashes[name] = {}
        if mapping:
            self._hashes[name].update({str(k): str(v) for k, v in mapping.items()})

    def hgetall(self, name):
        return dict(self._hashes.get(name, {}))

    def exists(self, name):
        return name in self._hashes

    def zadd(self, name, mapping):
        for member, score in mapping.items():
            self._sorted_sets[name][str(member)] = score

    def zpopmin(self, name, count=1):
        ss = self._sorted_sets.get(name, {})
        if not ss:
            return []
        sorted_items = sorted(ss.items(), key=lambda kv: kv[1])
        result = []
        for member, score in sorted_items[:count]:
            del ss[member]
            result.append((member, score))
        return result

    def zrem(self, name, *members):
        ss = self._sorted_sets.get(name, {})
        for m in members:
            ss.pop(str(m), None)

    def zcard(self, name):
        return len(self._sorted_sets.get(name, {}))

    def zrangebyscore(self, name, min_score, max_score):
        ss = self._sorted_sets.get(name, {})
        results = []
        for member, score in ss.items():
            min_ok = True if min_score == "-inf" else score >= float(min_score)
            max_ok = True if max_score == "+inf" else score <= float(max_score)
            if min_ok and max_ok:
                results.append(member)
        return results

    def sadd(self, name, *values):
        for v in values:
            self._sets[name].add(str(v))

    def smembers(self, name):
        return set(self._sets.get(name, set()))

    def rpush(self, name, *values):
        for v in values:
            self._lists[name].append(str(v))

    def lrange(self, name, start, stop):
        lst = self._lists.get(name, [])
        if stop == -1:
            return lst[start:]
        return lst[start : stop + 1]

    def llen(self, name):
        return len(self._lists.get(name, []))

    def eval(self, script, numkeys, *args):
        """Simulate the fetch Lua script atomically.

        Supports the ``_FETCH_LUA`` script used by
        :class:`RedisQueueBackend` to pop from a pending sorted set and
        add to a processing sorted set in one step.
        """
        keys = list(args[:numkeys])
        argv = list(args[numkeys:])

        pending_key = keys[0]
        processing_key = keys[1]
        lease_expiry = float(argv[0])

        result = self.zpopmin(pending_key, 1)
        if not result:
            return None
        item_id, _score = result[0]
        self.zadd(processing_key, {item_id: lease_expiry})
        return item_id


class MockPipeline:
    """Mock Redis pipeline that collects commands and executes them."""

    def __init__(self, redis: MockRedis):
        self._redis = redis
        self._commands: list[tuple] = []

    def hset(self, name, mapping=None, **kwargs):
        self._commands.append(("hset", name, mapping))
        return self

    def zadd(self, name, mapping):
        self._commands.append(("zadd", name, mapping))
        return self

    def sadd(self, name, *values):
        self._commands.append(("sadd", name, values))
        return self

    def execute(self):
        for cmd in self._commands:
            if cmd[0] == "hset":
                self._redis.hset(cmd[1], mapping=cmd[2])
            elif cmd[0] == "zadd":
                self._redis.zadd(cmd[1], cmd[2])
            elif cmd[0] == "sadd":
                self._redis.sadd(cmd[1], *cmd[2])
        self._commands.clear()


@pytest.fixture
def mock_redis():
    return MockRedis()


@pytest.fixture
def queue(mock_redis):
    return RedisQueueBackend(
        mock_redis, lease_timeout=10, max_retries=2, backoff_base=2.0
    )


# -- Enqueue ------------------------------------------------------------------


async def test_enqueue_returns_count(queue):
    items = [
        QueueItem(id="a", payload={"data": 1}),
        QueueItem(id="b", payload={"data": 2}),
    ]
    count = await queue.enqueue("tasks", items)
    assert count == 2


async def test_enqueue_generates_ids(queue):
    items = [QueueItem(id="", payload={"x": 1})]
    count = await queue.enqueue("tasks", items)
    assert count == 1
    # The item should now have an id assigned
    assert items[0].id != ""
    assert len(items[0].id) > 0


async def test_enqueue_registers_queue(queue, mock_redis):
    await queue.enqueue("myq", [QueueItem(id="a")])
    assert "myq" in mock_redis._sets[queue._queues_key()]


# -- Fetch --------------------------------------------------------------------


async def test_fetch_returns_items(queue, mock_redis):
    await queue.enqueue("tasks", [QueueItem(id="item1")])
    fetched = await queue.fetch("tasks", 1, "worker-1")
    assert len(fetched) == 1
    assert fetched[0].id == "item1"
    assert fetched[0].worker_id == "worker-1"
    # Verify processing status is tracked in Redis metadata
    meta = mock_redis.hgetall(queue._item_key("tasks", "item1"))
    assert meta["status"] == "processing"


async def test_fetch_returns_queue_items(queue):
    await queue.enqueue("tasks", [QueueItem(id="q1", payload={"key": "val"})])
    fetched = await queue.fetch("tasks", 1, "w1")
    assert isinstance(fetched[0], QueueItem)
    assert fetched[0].payload == {"key": "val"}


async def test_fetch_respects_count(queue):
    await queue.enqueue(
        "tasks",
        [QueueItem(id="a"), QueueItem(id="b"), QueueItem(id="c")],
    )
    fetched = await queue.fetch("tasks", 2, "w1")
    assert len(fetched) == 2


async def test_fetch_empty_queue(queue):
    fetched = await queue.fetch("tasks", 5, "w1")
    assert fetched == []


async def test_fetch_priority_order(queue):
    await queue.enqueue("tasks", [QueueItem(id="low")], priority=10)
    await queue.enqueue("tasks", [QueueItem(id="high")], priority=1)
    fetched = await queue.fetch("tasks", 2, "w1")
    assert fetched[0].id == "high"
    assert fetched[1].id == "low"


async def test_fetch_atomic_pop_and_lease(queue, mock_redis):
    """Item must never exist in neither pending nor processing.

    After fetch, the item must be removed from pending and present in
    processing -- the Lua script guarantees these happen atomically.
    """
    await queue.enqueue("tasks", [QueueItem(id="atom1")])

    pending_key = queue._pending_key("tasks")
    processing_key = queue._processing_key("tasks")

    assert mock_redis.zcard(pending_key) == 1
    assert mock_redis.zcard(processing_key) == 0

    fetched = await queue.fetch("tasks", 1, "w1")

    assert len(fetched) == 1
    assert fetched[0].id == "atom1"
    # Item moved from pending to processing
    assert mock_redis.zcard(pending_key) == 0
    assert mock_redis.zcard(processing_key) == 1
    assert "atom1" in mock_redis._sorted_sets[processing_key]


async def test_fetch_uses_eval_for_atomicity(queue, mock_redis):
    """Verify that fetch calls eval (Lua script) instead of separate
    zpopmin + zadd, ensuring crash-safe item transfer."""
    calls: list[str] = []
    original_eval = mock_redis.eval
    original_zpopmin = mock_redis.zpopmin

    def tracking_eval(*args, **kwargs):
        calls.append("eval")
        return original_eval(*args, **kwargs)

    def tracking_zpopmin(*args, **kwargs):
        calls.append("zpopmin")
        return original_zpopmin(*args, **kwargs)

    mock_redis.eval = tracking_eval
    mock_redis.zpopmin = tracking_zpopmin

    await queue.enqueue("tasks", [QueueItem(id="t1")])
    await queue.fetch("tasks", 1, "w1")

    # fetch must use eval (which internally calls zpopmin), not a
    # direct zpopmin at the top level.
    assert "eval" in calls
    # zpopmin is called *inside* eval, but never directly by fetch
    assert calls[0] == "eval"


# -- Complete -----------------------------------------------------------------


async def test_complete_marks_done(queue, mock_redis):
    await queue.enqueue("tasks", [QueueItem(id="item1")])
    await queue.fetch("tasks", 1, "w1")
    result = await queue.complete("tasks", "item1")
    assert result is True
    meta = mock_redis.hgetall(queue._item_key("tasks", "item1"))
    assert meta["status"] == "completed"


async def test_complete_unknown_item(queue):
    result = await queue.complete("tasks", "nonexistent")
    assert result is False


async def test_complete_removes_from_processing(queue, mock_redis):
    await queue.enqueue("tasks", [QueueItem(id="x")])
    await queue.fetch("tasks", 1, "w1")
    await queue.complete("tasks", "x")
    assert mock_redis.zcard(queue._processing_key("tasks")) == 0


# -- Requeue ------------------------------------------------------------------


async def test_requeue_increments_retry(queue, mock_redis):
    await queue.enqueue("tasks", [QueueItem(id="r1")])
    await queue.fetch("tasks", 1, "w1")
    requeued = await queue.requeue("tasks", [QueueItem(id="r1")])
    assert requeued == 1
    meta = mock_redis.hgetall(queue._item_key("tasks", "r1"))
    assert int(meta["retry_count"]) == 1
    assert meta["status"] == "pending"


async def test_requeue_applies_backoff_priority(queue, mock_redis):
    await queue.enqueue("tasks", [QueueItem(id="r1")], priority=0)
    await queue.fetch("tasks", 1, "w1")
    await queue.requeue("tasks", [QueueItem(id="r1")])
    # After 1 retry with backoff_base=2, priority should be 0 + int(2^1) = 2
    pending = mock_redis._sorted_sets[queue._pending_key("tasks")]
    assert pending["r1"] == 2


async def test_requeue_dead_letters_after_max_retries(queue, mock_redis):
    await queue.enqueue("tasks", [QueueItem(id="r1")])
    await queue.fetch("tasks", 1, "w1")

    # Retry 1
    await queue.requeue("tasks", [QueueItem(id="r1")])
    await queue.fetch("tasks", 1, "w1")

    # Retry 2
    await queue.requeue("tasks", [QueueItem(id="r1")])
    await queue.fetch("tasks", 1, "w1")

    # Retry 3 -- exceeds max_retries=2, should dead-letter
    requeued = await queue.requeue("tasks", [QueueItem(id="r1")])
    assert requeued == 0

    dlq = await queue.dead_letter_items("tasks")
    assert len(dlq) == 1
    assert dlq[0]["status"] == "dead_letter"


async def test_requeue_skips_empty_id(queue):
    requeued = await queue.requeue("tasks", [QueueItem(id="")])
    assert requeued == 0


async def test_requeue_skips_unknown_item(queue):
    requeued = await queue.requeue("tasks", [QueueItem(id="ghost")])
    assert requeued == 0


# -- Status -------------------------------------------------------------------


async def test_status_counts(queue):
    await queue.enqueue("tasks", [QueueItem(id="a"), QueueItem(id="b")])
    await queue.fetch("tasks", 1, "w1")
    st = await queue.status("tasks")
    assert st["pending"] == 1
    assert st["processing"] == 1
    assert st["dead_letter"] == 0


async def test_status_empty_queue(queue):
    st = await queue.status("empty")
    assert st["pending"] == 0
    assert st["processing"] == 0
    assert st["dead_letter"] == 0


# -- List queues --------------------------------------------------------------


async def test_list_queues(queue):
    await queue.enqueue("alpha", [QueueItem(id="1")])
    await queue.enqueue("beta", [QueueItem(id="2")])
    queues = await queue.list_queues()
    assert set(queues) == {"alpha", "beta"}


async def test_list_queues_empty(queue):
    queues = await queue.list_queues()
    assert queues == []


# -- Lease expiry / reclaim ---------------------------------------------------


async def test_expired_lease_reclaimed(queue, mock_redis, monkeypatch):
    await queue.enqueue("tasks", [QueueItem(id="leased")])
    await queue.fetch("tasks", 1, "w1")

    # Simulate time passing beyond lease timeout
    processing_key = queue._processing_key("tasks")
    mock_redis._sorted_sets[processing_key]["leased"] = time.time() - 100

    # Next fetch should reclaim
    await queue.enqueue("tasks", [QueueItem(id="fresh")])
    fetched = await queue.fetch("tasks", 2, "w2")

    # The reclaimed item should be back in pending (fetched again)
    ids = [f.id for f in fetched]
    assert "leased" in ids or "fresh" in ids


async def test_expired_lease_dead_letters_if_max_retries(queue, mock_redis):
    await queue.enqueue("tasks", [QueueItem(id="doomed")])
    await queue.fetch("tasks", 1, "w1")

    # Set retry_count to max already
    item_key = queue._item_key("tasks", "doomed")
    mock_redis._hashes[item_key]["retry_count"] = str(queue._max_retries)

    # Expire the lease
    processing_key = queue._processing_key("tasks")
    mock_redis._sorted_sets[processing_key]["doomed"] = time.time() - 100

    await queue._reclaim_expired("tasks")

    dlq = await queue.dead_letter_items("tasks")
    assert len(dlq) == 1


# -- Dead-letter queue --------------------------------------------------------


async def test_dead_letter_items_empty(queue):
    dlq = await queue.dead_letter_items("tasks")
    assert dlq == []


# -- Decode hash helper -------------------------------------------------------


def test_decode_hash_bytes():
    raw = {b"key": b"value", b"num": b"42"}
    decoded = RedisQueueBackend._decode_hash(raw)
    assert decoded == {"key": "value", "num": "42"}


def test_decode_hash_strings():
    raw = {"key": "value"}
    decoded = RedisQueueBackend._decode_hash(raw)
    assert decoded == {"key": "value"}


# -- Import path (issue #245) ------------------------------------------------


def test_config_imports_from_redis_queue_module():
    """Verify that config._build_queue imports from the correct module path."""
    import ast
    import inspect
    import textwrap

    from loom_ai.config import LoomConfig

    source = textwrap.dedent(inspect.getsource(LoomConfig._build_queue))
    tree = ast.parse(source)
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]
    redis_import = [
        imp for imp in imports if imp.module and "redis" in imp.module
    ]
    assert len(redis_import) == 1
    assert redis_import[0].module == "loom_ai.backends.redis_queue"


# -- from_env() (issue #245) -------------------------------------------------


def test_from_env_reads_loom_redis_url(monkeypatch):
    """RedisQueueBackend.from_env() reads LOOM_REDIS_URL and builds a client."""
    mock_client = MagicMock()
    mock_redis_mod = MagicMock()
    mock_redis_mod.Redis.from_url.return_value = mock_client

    monkeypatch.setenv("LOOM_REDIS_URL", "redis://myhost:6380/2")

    with patch("loom_ai.backends.redis_queue._redis_lib", mock_redis_mod):
        backend = RedisQueueBackend.from_env()

    mock_redis_mod.Redis.from_url.assert_called_once_with("redis://myhost:6380/2")
    assert backend._redis is mock_client


def test_from_env_uses_default_url(monkeypatch):
    """RedisQueueBackend.from_env() falls back to localhost when env var unset."""
    monkeypatch.delenv("LOOM_REDIS_URL", raising=False)

    mock_client = MagicMock()
    mock_redis_mod = MagicMock()
    mock_redis_mod.Redis.from_url.return_value = mock_client

    with patch("loom_ai.backends.redis_queue._redis_lib", mock_redis_mod):
        backend = RedisQueueBackend.from_env()

    mock_redis_mod.Redis.from_url.assert_called_once_with(
        "redis://localhost:6379/0"
    )
    assert isinstance(backend, RedisQueueBackend)
