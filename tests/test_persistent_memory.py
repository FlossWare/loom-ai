"""Tests for InMemoryPersistentMemory (issue #91)."""

import pytest

from loom_ai.backends.memory import InMemoryPersistentMemory
from loom_ai.contracts_core import PersistentMemoryBackend
from loom_ai.models_core import MemoryRecord


@pytest.fixture
def mem():
    return InMemoryPersistentMemory()


def test_satisfies_protocol():
    assert isinstance(InMemoryPersistentMemory(), PersistentMemoryBackend)


async def test_store_recall_roundtrip(mem):
    record_id = await mem.store(
        "greeting",
        "Hello, world!",
        memory_type="fact",
        metadata={"source": "test"},
    )
    assert isinstance(record_id, str)
    assert len(record_id) > 0

    recalled = await mem.recall("greeting")
    assert recalled is not None
    assert isinstance(recalled, MemoryRecord)
    assert recalled.id == record_id
    assert recalled.name == "greeting"
    assert recalled.content == "Hello, world!"
    assert recalled.memory_type == "fact"
    assert recalled.metadata == {"source": "test"}
    assert recalled.created_at != ""
    assert recalled.updated_at != ""


async def test_recall_missing_returns_none(mem):
    result = await mem.recall("nonexistent")
    assert result is None


async def test_search_by_content(mem):
    await mem.store("py-info", "Python is a programming language", memory_type="fact")
    await mem.store("js-info", "JavaScript runs in browsers", memory_type="fact")
    await mem.store("py-tip", "Use Python virtual environments", memory_type="tip")

    results = await mem.search("Python")
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"py-info", "py-tip"}


async def test_search_by_name(mem):
    await mem.store("python-setup", "Install Python 3.12", memory_type="guide")
    await mem.store("rust-setup", "Install Rust via rustup", memory_type="guide")

    results = await mem.search("python")
    assert len(results) == 1
    assert results[0].name == "python-setup"


async def test_search_with_type_filter(mem):
    await mem.store("py-info", "Python is great", memory_type="fact")
    await mem.store("py-tip", "Use type hints in Python", memory_type="tip")

    results = await mem.search("Python", memory_type="tip")
    assert len(results) == 1
    assert results[0].name == "py-tip"
    assert results[0].memory_type == "tip"


async def test_search_with_limit(mem):
    for i in range(20):
        await mem.store(f"item-{i}", f"content about topic {i}", memory_type="fact")

    results = await mem.search("topic", limit=5)
    assert len(results) == 5


async def test_search_no_results(mem):
    await mem.store("greeting", "Hello", memory_type="fact")
    results = await mem.search("nonexistent-query")
    assert results == []


async def test_update_changes_content_and_timestamp(mem):
    await mem.store("note", "original content", memory_type="note")
    original = await mem.recall("note")
    assert original is not None
    original_updated_at = original.updated_at

    await mem.update("note", "updated content")
    updated = await mem.recall("note")
    assert updated is not None
    assert updated.content == "updated content"
    assert updated.memory_type == "note"  # unchanged
    assert updated.updated_at >= original_updated_at


async def test_update_changes_type_and_metadata(mem):
    await mem.store("note", "some content", memory_type="note", metadata={"v": 1})

    await mem.update("note", "new content", memory_type="reference", metadata={"v": 2})
    updated = await mem.recall("note")
    assert updated is not None
    assert updated.content == "new content"
    assert updated.memory_type == "reference"
    assert updated.metadata == {"v": 2}


async def test_update_missing_raises(mem):
    with pytest.raises(KeyError):
        await mem.update("nonexistent", "content")


async def test_forget_existing_returns_true(mem):
    await mem.store("temp", "temporary data", memory_type="scratch")
    result = await mem.forget("temp")
    assert result is True

    recalled = await mem.recall("temp")
    assert recalled is None


async def test_forget_missing_returns_false(mem):
    result = await mem.forget("nonexistent")
    assert result is False


async def test_list_memories_all(mem):
    await mem.store("a", "content a", memory_type="fact")
    await mem.store("b", "content b", memory_type="tip")
    await mem.store("c", "content c", memory_type="fact")

    all_memories = await mem.list_memories()
    assert len(all_memories) == 3
    names = {r.name for r in all_memories}
    assert names == {"a", "b", "c"}


async def test_list_memories_filtered_by_type(mem):
    await mem.store("a", "content a", memory_type="fact")
    await mem.store("b", "content b", memory_type="tip")
    await mem.store("c", "content c", memory_type="fact")

    facts = await mem.list_memories(memory_type="fact")
    assert len(facts) == 2
    names = {r.name for r in facts}
    assert names == {"a", "c"}

    tips = await mem.list_memories(memory_type="tip")
    assert len(tips) == 1
    assert tips[0].name == "b"


async def test_list_memories_empty(mem):
    result = await mem.list_memories()
    assert result == []


async def test_store_overwrites_same_name(mem):
    id1 = await mem.store("key", "first", memory_type="fact")
    id2 = await mem.store("key", "second", memory_type="fact")
    assert id1 != id2

    recalled = await mem.recall("key")
    assert recalled is not None
    assert recalled.content == "second"
    assert recalled.id == id2

    all_memories = await mem.list_memories()
    assert len(all_memories) == 1
