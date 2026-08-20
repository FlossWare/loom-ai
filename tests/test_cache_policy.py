"""Tests for PromptCachePolicy backend.

Covers provider-specific hint application, unknown-provider passthrough,
cache-hit/miss statistics, content hashing, and protocol conformance.
No external dependencies required.
"""

from __future__ import annotations

from loom_ai.backends.cache import PromptCachePolicy, _content_hash
from loom_ai.contracts_session import CachePolicy
from loom_ai.models_session import CacheStats

# ── Protocol conformance ──────────────────────────────────────────────────


def test_protocol_conformance():
    """PromptCachePolicy satisfies the CachePolicy protocol."""
    policy = PromptCachePolicy()
    assert isinstance(policy, CachePolicy)


# ── Anthropic hints ───────────────────────────────────────────────────────


def test_anthropic_adds_cache_control_to_system_messages():
    policy = PromptCachePolicy()
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
    ]
    result = policy.apply_cache_hints(messages, provider="anthropic")

    assert len(result) == 2
    assert result[0]["cache_control"] == {"type": "ephemeral"}
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "You are a helpful assistant."
    assert "cache_control" not in result[1]


def test_anthropic_multiple_system_messages():
    policy = PromptCachePolicy()
    messages = [
        {"role": "system", "content": "System prompt 1"},
        {"role": "system", "content": "System prompt 2"},
        {"role": "user", "content": "Hi"},
    ]
    result = policy.apply_cache_hints(messages, provider="anthropic")

    assert result[0]["cache_control"] == {"type": "ephemeral"}
    assert result[1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in result[2]


def test_anthropic_no_system_messages():
    policy = PromptCachePolicy()
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    result = policy.apply_cache_hints(messages, provider="anthropic")

    assert len(result) == 2
    for msg in result:
        assert "cache_control" not in msg


def test_anthropic_does_not_mutate_original():
    policy = PromptCachePolicy()
    original = [{"role": "system", "content": "Be helpful."}]
    result = policy.apply_cache_hints(original, provider="anthropic")

    assert "cache_control" in result[0]
    assert "cache_control" not in original[0]


# ── OpenAI hints ──────────────────────────────────────────────────────────


def test_openai_returns_unchanged():
    policy = PromptCachePolicy()
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]
    result = policy.apply_cache_hints(messages, provider="openai")

    assert len(result) == 2
    assert result[0] == messages[0]
    assert result[1] == messages[1]
    for msg in result:
        assert "cache_control" not in msg


# ── Unknown provider passthrough ──────────────────────────────────────────


def test_unknown_provider_passthrough():
    policy = PromptCachePolicy()
    messages = [
        {"role": "system", "content": "Hello"},
        {"role": "user", "content": "World"},
    ]
    result = policy.apply_cache_hints(messages, provider="some-unknown-provider")

    assert len(result) == 2
    assert result[0] == messages[0]
    assert result[1] == messages[1]
    for msg in result:
        assert "cache_control" not in msg


def test_empty_provider_passthrough():
    policy = PromptCachePolicy()
    messages = [{"role": "user", "content": "Hi"}]
    result = policy.apply_cache_hints(messages, provider="")

    assert result == messages


# ── Stats tracking ────────────────────────────────────────────────────────


async def test_initial_stats_are_zero():
    policy = PromptCachePolicy()
    stats = await policy.cache_stats()

    assert isinstance(stats, CacheStats)
    assert stats.hits == 0
    assert stats.misses == 0
    assert stats.hit_rate == 0.0
    assert stats.tokens_saved == 0
    assert stats.cost_saved == 0.0


async def test_first_call_is_miss():
    policy = PromptCachePolicy()
    messages = [{"role": "user", "content": "Hello"}]
    policy.apply_cache_hints(messages, provider="anthropic")

    stats = await policy.cache_stats()
    assert stats.misses == 1
    assert stats.hits == 0
    assert stats.hit_rate == 0.0


async def test_repeated_call_is_hit():
    policy = PromptCachePolicy()
    messages = [{"role": "user", "content": "Hello"}]
    policy.apply_cache_hints(messages, provider="anthropic")
    policy.apply_cache_hints(messages, provider="anthropic")

    stats = await policy.cache_stats()
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.hit_rate == 0.5


async def test_different_messages_are_separate_misses():
    policy = PromptCachePolicy()
    policy.apply_cache_hints(
        [{"role": "user", "content": "Hello"}], provider="anthropic"
    )
    policy.apply_cache_hints(
        [{"role": "user", "content": "Goodbye"}], provider="anthropic"
    )

    stats = await policy.cache_stats()
    assert stats.misses == 2
    assert stats.hits == 0


async def test_stats_accumulate_correctly():
    policy = PromptCachePolicy()
    msg_a = [{"role": "user", "content": "A"}]
    msg_b = [{"role": "user", "content": "B"}]

    # 2 misses
    policy.apply_cache_hints(msg_a, provider="openai")
    policy.apply_cache_hints(msg_b, provider="openai")
    # 3 hits
    policy.apply_cache_hints(msg_a, provider="openai")
    policy.apply_cache_hints(msg_b, provider="openai")
    policy.apply_cache_hints(msg_a, provider="openai")

    stats = await policy.cache_stats()
    assert stats.hits == 3
    assert stats.misses == 2
    assert stats.hit_rate == 3 / 5


# ── Content hashing ──────────────────────────────────────────────────────


def test_content_hash_deterministic():
    messages = [{"role": "user", "content": "Hello"}]
    h1 = _content_hash(messages)
    h2 = _content_hash(messages)
    assert h1 == h2


def test_content_hash_differs_for_different_content():
    h1 = _content_hash([{"role": "user", "content": "Hello"}])
    h2 = _content_hash([{"role": "user", "content": "Goodbye"}])
    assert h1 != h2


def test_content_hash_order_independent_dict_keys():
    """Dict key insertion order should not affect the hash."""
    h1 = _content_hash([{"role": "user", "content": "Hi"}])
    h2 = _content_hash([{"content": "Hi", "role": "user"}])
    assert h1 == h2


# ── Edge cases ────────────────────────────────────────────────────────────


def test_empty_messages_list():
    policy = PromptCachePolicy()
    result = policy.apply_cache_hints([], provider="anthropic")
    assert result == []


def test_empty_messages_list_openai():
    policy = PromptCachePolicy()
    result = policy.apply_cache_hints([], provider="openai")
    assert result == []
