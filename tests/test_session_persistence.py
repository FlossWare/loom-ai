"""Tests for session persistence (#683-#686).

Covers:
- #683: Persist session state across process termination
- #684: Extract, chunk, embed, and persist engineering knowledge
- #685: Retrieve prior knowledge in a fresh session
- #686: Use recovered knowledge for follow-up tasks
"""

from __future__ import annotations

import json

import pytest

from loom_ai.backends.memory import InMemoryPersistentMemory
from loom_ai.models_phase1 import RetrievalResult
from loom_ai.session_persistence import (
    RecoveredContext,
    SessionEvent,
    SessionManager,
    SessionState,
)


class FakeKnowledgePipeline:
    """Minimal in-memory KnowledgePipeline for testing."""

    def __init__(self) -> None:
        self._docs: dict[str, tuple[str, dict]] = {}
        self._counter = 0

    async def ingest(
        self,
        content: str,
        *,
        metadata: dict | None = None,
    ) -> str:
        self._counter += 1
        doc_id = f"doc-{self._counter}"
        self._docs[doc_id] = (content, metadata or {})
        return doc_id

    async def query(
        self,
        question: str,
        *,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        results = []
        q_lower = question.lower()
        for doc_id, (content, meta) in self._docs.items():
            if q_lower in content.lower():
                results.append(
                    RetrievalResult(
                        content=content,
                        score=1.0,
                        source=meta.get("source", doc_id),
                        chunk_id=doc_id,
                        metadata=meta,
                    )
                )
                if len(results) >= limit:
                    break
        return results


class TestSessionEvent:
    def test_defaults(self):
        e = SessionEvent(kind="observation", content="test")
        assert e.kind == "observation"
        assert e.content == "test"
        assert e.timestamp == ""
        assert e.metadata == {}


class TestSessionState:
    def test_defaults(self):
        s = SessionState(session_id="s1", project="p1")
        assert s.session_id == "s1"
        assert s.project == "p1"
        assert s.events == []
        assert s.metadata == {}


class TestRecoveredContext:
    def test_defaults(self):
        ctx = RecoveredContext()
        assert ctx.memories == []
        assert ctx.knowledge == []
        assert ctx.provenance == []


class TestSessionCreate:
    async def test_create_returns_uuid(self):
        mgr = SessionManager()
        sid = await mgr.create_session(project="loom-ai")
        assert sid
        assert len(sid) == 36

    async def test_create_with_metadata(self):
        mgr = SessionManager()
        sid = await mgr.create_session(
            project="test",
            metadata={"tag": "dev"},
        )
        state = await mgr.get_session(sid)
        assert state is not None
        assert state.project == "test"
        assert state.metadata == {"tag": "dev"}
        assert state.created_at != ""


class TestRecordEvent:
    async def test_records_events_in_order(self):
        mgr = SessionManager()
        sid = await mgr.create_session(project="test")
        await mgr.record_event(sid, "first")
        await mgr.record_event(sid, "second", kind="decision")

        state = await mgr.get_session(sid)
        assert state is not None
        assert len(state.events) == 2
        assert state.events[0].content == "first"
        assert state.events[0].kind == "observation"
        assert state.events[1].content == "second"
        assert state.events[1].kind == "decision"

    async def test_records_timestamp(self):
        mgr = SessionManager()
        sid = await mgr.create_session(project="test")
        await mgr.record_event(sid, "event")

        state = await mgr.get_session(sid)
        assert state is not None
        assert state.events[0].timestamp != ""

    async def test_unknown_session_raises(self):
        mgr = SessionManager()
        with pytest.raises(KeyError, match="Session not found"):
            await mgr.record_event("no-such-id", "event")


class TestPersistToMemory:
    async def test_persist_stores_to_memory(self):
        memory = InMemoryPersistentMemory()
        mgr = SessionManager(memory=memory)
        sid = await mgr.create_session(project="loom-ai")
        await mgr.record_event(sid, "found bug")
        await mgr.record_event(sid, "fixed it", kind="fix")

        result = await mgr.persist(sid)
        assert result["memory_stored"] is True
        assert result["session_id"] == sid

        record = await memory.recall(f"session/{sid}")
        assert record is not None
        data = json.loads(record.content)
        assert data["project"] == "loom-ai"
        assert len(data["events"]) == 2
        assert data["events"][1]["kind"] == "fix"

    async def test_persist_no_backend(self):
        mgr = SessionManager()
        sid = await mgr.create_session(project="test")
        result = await mgr.persist(sid)
        assert result["memory_stored"] is False
        assert result["knowledge_stored"] is False

    async def test_persist_unknown_session_raises(self):
        mgr = SessionManager()
        with pytest.raises(KeyError, match="Session not found"):
            await mgr.persist("no-such-id")


class TestKnowledgeExtraction:
    async def test_extracts_relevant_event_kinds(self):
        knowledge = FakeKnowledgePipeline()
        mgr = SessionManager(knowledge=knowledge)
        sid = await mgr.create_session(project="loom-ai")

        await mgr.record_event(sid, "parser has off-by-one", kind="observation")
        await mgr.record_event(sid, "chose recursive descent", kind="decision")
        await mgr.record_event(sid, "found edge case", kind="discovery")
        await mgr.record_event(sid, "patched boundary check", kind="fix")

        result = await mgr.persist(sid)
        assert result["knowledge_stored"] is True
        assert "knowledge_doc_id" in result

        assert len(knowledge._docs) == 1
        doc_content = list(knowledge._docs.values())[0][0]
        assert "[observation] parser has off-by-one" in doc_content
        assert "[decision] chose recursive descent" in doc_content
        assert "[discovery] found edge case" in doc_content
        assert "[fix] patched boundary check" in doc_content

    async def test_skips_non_knowledge_events(self):
        knowledge = FakeKnowledgePipeline()
        mgr = SessionManager(knowledge=knowledge)
        sid = await mgr.create_session(project="test")

        await mgr.record_event(sid, "just a log", kind="log")
        await mgr.record_event(sid, "user said hi", kind="chat")

        result = await mgr.persist(sid)
        assert result["knowledge_stored"] is False

    async def test_both_memory_and_knowledge(self):
        memory = InMemoryPersistentMemory()
        knowledge = FakeKnowledgePipeline()
        mgr = SessionManager(memory=memory, knowledge=knowledge)
        sid = await mgr.create_session(project="loom-ai")
        await mgr.record_event(sid, "important fix", kind="fix")

        result = await mgr.persist(sid)
        assert result["memory_stored"] is True
        assert result["knowledge_stored"] is True


class TestRecoverContext:
    async def test_recover_from_memory(self):
        memory = InMemoryPersistentMemory()
        mgr = SessionManager(memory=memory)
        sid = await mgr.create_session(project="loom-ai")
        await mgr.record_event(sid, "parser has bug")
        await mgr.persist(sid)

        ctx = await mgr.recover_context(
            project="loom-ai",
            query="parser",
        )
        assert len(ctx.memories) == 1
        assert "parser has bug" in ctx.memories[0]["content"]
        assert any("memory:" in p for p in ctx.provenance)

    async def test_recover_from_knowledge(self):
        knowledge = FakeKnowledgePipeline()
        mgr = SessionManager(knowledge=knowledge)
        sid = await mgr.create_session(project="loom-ai")
        await mgr.record_event(sid, "parser has bug", kind="observation")
        await mgr.persist(sid)

        ctx = await mgr.recover_context(
            project="loom-ai",
            query="parser",
        )
        assert len(ctx.knowledge) == 1
        assert "parser has bug" in ctx.knowledge[0]["content"]
        assert any("knowledge:" in p for p in ctx.provenance)

    async def test_recover_combined(self):
        memory = InMemoryPersistentMemory()
        knowledge = FakeKnowledgePipeline()
        mgr = SessionManager(memory=memory, knowledge=knowledge)
        sid = await mgr.create_session(project="loom-ai")
        await mgr.record_event(sid, "parser bug found", kind="discovery")
        await mgr.persist(sid)

        ctx = await mgr.recover_context(
            project="loom-ai",
            query="parser",
        )
        assert len(ctx.memories) >= 1
        assert len(ctx.knowledge) >= 1
        assert len(ctx.provenance) >= 2

    async def test_empty_query_returns_nothing(self):
        memory = InMemoryPersistentMemory()
        mgr = SessionManager(memory=memory)
        sid = await mgr.create_session(project="test")
        await mgr.record_event(sid, "data")
        await mgr.persist(sid)

        ctx = await mgr.recover_context(project="test", query="")
        assert ctx.memories == []

    async def test_no_backends_returns_empty(self):
        mgr = SessionManager()
        ctx = await mgr.recover_context(
            project="test",
            query="anything",
        )
        assert ctx.memories == []
        assert ctx.knowledge == []


class TestFollowUpWithRecoveredKnowledge:
    """#686: Use recovered knowledge to inform follow-up work."""

    async def test_recover_and_apply(self):
        memory = InMemoryPersistentMemory()
        knowledge = FakeKnowledgePipeline()

        mgr1 = SessionManager(memory=memory, knowledge=knowledge)
        sid1 = await mgr1.create_session(project="loom-ai")
        await mgr1.record_event(
            sid1,
            "parser fails on nested brackets: fix boundary check",
            kind="fix",
        )
        await mgr1.persist(sid1)

        mgr2 = SessionManager(memory=memory, knowledge=knowledge)
        ctx = await mgr2.recover_context(
            project="loom-ai",
            query="parser",
        )

        assert len(ctx.knowledge) >= 1
        assert "nested brackets" in ctx.knowledge[0]["content"]
        assert len(ctx.provenance) >= 1

        sid2 = await mgr2.create_session(project="loom-ai")
        await mgr2.record_event(
            sid2,
            f"recovered {len(ctx.knowledge)} prior findings about parser",
            kind="observation",
        )
        state = await mgr2.get_session(sid2)
        assert state is not None
        assert len(state.events) == 1
        assert "recovered" in state.events[0].content

    async def test_multi_session_accumulation(self):
        memory = InMemoryPersistentMemory()
        knowledge = FakeKnowledgePipeline()

        for i in range(3):
            mgr = SessionManager(memory=memory, knowledge=knowledge)
            sid = await mgr.create_session(project="loom-ai")
            await mgr.record_event(
                sid,
                f"session {i}: found issue in parser module",
                kind="observation",
            )
            await mgr.persist(sid)

        fresh = SessionManager(memory=memory, knowledge=knowledge)
        ctx = await fresh.recover_context(
            project="loom-ai",
            query="parser",
        )

        assert len(ctx.knowledge) == 3
        assert len(ctx.provenance) >= 3


class TestGetSession:
    async def test_returns_none_for_unknown(self):
        mgr = SessionManager()
        assert await mgr.get_session("nonexistent") is None

    async def test_returns_state(self):
        mgr = SessionManager()
        sid = await mgr.create_session(project="test")
        state = await mgr.get_session(sid)
        assert state is not None
        assert state.session_id == sid
