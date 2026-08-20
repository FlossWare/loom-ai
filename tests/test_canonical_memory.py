"""Tests for canonical memory model (#667) and graph unification (#668)."""

from __future__ import annotations

from loom_ai.backends.conversation import InMemoryConversationManager
from loom_ai.backends.scoped_memory import ScopedMemoryView
from loom_ai.config import GraphLike
from loom_ai.models import ChatMessage
from loom_ai.models_phase1 import MemoryRecord


class TestMemoryRecordCanonical:
    def test_has_scope_fields(self):
        r = MemoryRecord(
            id="1", name="test", content="c", memory_type="fact",
            scope="session", agent_id="a1", session_id="s1",
            ttl_seconds=3600, confidence=0.9,
        )
        assert r.scope == "session"
        assert r.agent_id == "a1"
        assert r.session_id == "s1"
        assert r.ttl_seconds == 3600
        assert r.confidence == 0.9
        assert r.superseded_by is None

    def test_defaults(self):
        r = MemoryRecord(
            id="2", name="x", content="y", memory_type="t",
        )
        assert r.scope == "global"
        assert r.agent_id == ""
        assert r.ttl_seconds is None
        assert r.confidence == 1.0


class TestScopedMemoryView:
    async def test_scoped_store_and_recall(self):
        from loom_ai.backends.memory import InMemoryPersistentMemory

        backend = InMemoryPersistentMemory()
        view = ScopedMemoryView(
            backend, scope="agent-1", agent_id="a1",
        )
        rid = await view.store(
            "finding", "bug in parser",
            memory_type="observation",
        )
        assert rid

        record = await view.recall("finding")
        assert record is not None
        assert "bug in parser" in record.content
        assert record.metadata["scope"] == "agent-1"
        assert record.metadata["agent_id"] == "a1"

    async def test_scoped_isolation(self):
        from loom_ai.backends.memory import InMemoryPersistentMemory

        backend = InMemoryPersistentMemory()
        view_a = ScopedMemoryView(backend, scope="agent-a")
        view_b = ScopedMemoryView(backend, scope="agent-b")

        await view_a.store("note", "from A", memory_type="t")
        await view_b.store("note", "from B", memory_type="t")

        rec_a = await view_a.recall("note")
        rec_b = await view_b.recall("note")
        assert rec_a is not None
        assert rec_b is not None
        assert "from A" in rec_a.content
        assert "from B" in rec_b.content

    async def test_forget(self):
        from loom_ai.backends.memory import InMemoryPersistentMemory

        backend = InMemoryPersistentMemory()
        view = ScopedMemoryView(backend, scope="test")
        await view.store("tmp", "data", memory_type="t")
        assert await view.forget("tmp") is True
        assert await view.recall("tmp") is None


class TestConversationArchive:
    async def test_archive_creates_frozen_copy(self):
        mgr = InMemoryConversationManager()
        sid = await mgr.create_session()
        await mgr.add_message(
            sid, ChatMessage(role="user", content="hello"),
        )

        archive_id = await mgr.archive(sid)
        assert archive_id.startswith("archived_")

        transcript = await mgr.export_transcript(archive_id)
        assert len(transcript) == 1
        assert transcript[0]["content"] == "hello"

        await mgr.add_message(
            sid, ChatMessage(role="assistant", content="hi"),
        )
        archived = await mgr.export_transcript(archive_id)
        assert len(archived) == 1


class TestGraphLikeAlias:
    def test_graph_like_is_graph_backend(self):
        from loom_ai.protocols import GraphBackend

        assert GraphLike is GraphBackend
