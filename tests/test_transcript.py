"""Tests for InMemoryTranscriptStore."""

import asyncio

from loom_ai.backends.transcript import InMemoryTranscriptStore
from loom_ai.contracts_phase2 import TranscriptStore
from loom_ai.models import ChatMessage


def test_satisfies_protocol():
    """InMemoryTranscriptStore structurally satisfies TranscriptStore."""
    store = InMemoryTranscriptStore()
    assert isinstance(store, TranscriptStore)


async def test_store_and_load():
    store = InMemoryTranscriptStore()
    messages = [
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi there!"),
    ]
    await store.store("s1", messages)

    loaded = await store.load("s1")
    assert len(loaded) == 2
    assert loaded[0].role == "user"
    assert loaded[0].content == "Hello"
    assert loaded[1].role == "assistant"
    assert loaded[1].content == "Hi there!"


async def test_load_missing_session():
    store = InMemoryTranscriptStore()
    loaded = await store.load("nonexistent")
    assert loaded == []


async def test_store_overwrites():
    store = InMemoryTranscriptStore()
    await store.store("s1", [ChatMessage(role="user", content="First")])
    await store.store("s1", [ChatMessage(role="user", content="Second")])

    loaded = await store.load("s1")
    assert len(loaded) == 1
    assert loaded[0].content == "Second"


async def test_store_with_metadata():
    store = InMemoryTranscriptStore()
    meta = {"source": "web", "user_id": "u42"}
    await store.store(
        "s1",
        [ChatMessage(role="user", content="Hi")],
        metadata=meta,
    )

    sessions = await store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].metadata == meta


async def test_load_returns_copy():
    """Mutating the returned list should not affect the store."""
    store = InMemoryTranscriptStore()
    await store.store("s1", [ChatMessage(role="user", content="Hi")])

    loaded = await store.load("s1")
    loaded.clear()

    reloaded = await store.load("s1")
    assert len(reloaded) == 1


async def test_search_finds_matching_sessions():
    store = InMemoryTranscriptStore()
    await store.store(
        "s1",
        [
            ChatMessage(role="user", content="Tell me about Python"),
            ChatMessage(role="assistant", content="Python is a language"),
        ],
    )
    await store.store(
        "s2",
        [ChatMessage(role="user", content="What is Java?")],
    )

    results = await store.search("Python")
    assert len(results) == 1
    assert results[0].session_id == "s1"
    assert results[0].message_count == 2
    assert "Python" in results[0].preview


async def test_search_case_insensitive():
    store = InMemoryTranscriptStore()
    await store.store(
        "s1",
        [ChatMessage(role="user", content="HELLO WORLD")],
    )

    results = await store.search("hello")
    assert len(results) == 1
    assert results[0].session_id == "s1"


async def test_search_respects_limit():
    store = InMemoryTranscriptStore()
    for i in range(5):
        await store.store(
            f"s{i}",
            [ChatMessage(role="user", content="common keyword here")],
        )

    results = await store.search("common", limit=3)
    assert len(results) == 3


async def test_search_no_matches():
    store = InMemoryTranscriptStore()
    await store.store(
        "s1",
        [ChatMessage(role="user", content="Hello")],
    )

    results = await store.search("zzz_no_match")
    assert results == []


async def test_search_preview_truncated():
    store = InMemoryTranscriptStore()
    long_content = "x" * 200
    await store.store(
        "s1",
        [ChatMessage(role="user", content=long_content)],
    )

    results = await store.search("x")
    assert len(results) == 1
    assert len(results[0].preview) == 100


async def test_list_sessions_ordering():
    """Sessions should be returned most-recent first."""
    store = InMemoryTranscriptStore()

    await store.store("s1", [ChatMessage(role="user", content="First")])
    # Small delay to ensure distinct timestamps
    await asyncio.sleep(0.01)
    await store.store("s2", [ChatMessage(role="user", content="Second")])
    await asyncio.sleep(0.01)
    await store.store("s3", [ChatMessage(role="user", content="Third")])

    sessions = await store.list_sessions()
    assert len(sessions) == 3
    assert sessions[0].session_id == "s3"
    assert sessions[1].session_id == "s2"
    assert sessions[2].session_id == "s1"


async def test_list_sessions_limit():
    store = InMemoryTranscriptStore()
    for i in range(10):
        await store.store(
            f"s{i}",
            [ChatMessage(role="user", content=f"Session {i}")],
        )

    sessions = await store.list_sessions(limit=3)
    assert len(sessions) == 3


async def test_list_sessions_empty():
    store = InMemoryTranscriptStore()
    sessions = await store.list_sessions()
    assert sessions == []


async def test_list_sessions_preview():
    store = InMemoryTranscriptStore()
    await store.store(
        "s1",
        [ChatMessage(role="user", content="First message content")],
    )

    sessions = await store.list_sessions()
    assert sessions[0].preview == "First message content"


async def test_list_sessions_preview_empty_messages():
    store = InMemoryTranscriptStore()
    await store.store("s1", [])

    sessions = await store.list_sessions()
    assert sessions[0].preview == ""
    assert sessions[0].message_count == 0
