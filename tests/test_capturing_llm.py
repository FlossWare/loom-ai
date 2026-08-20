"""Tests for CapturingLLMBackend (#698)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from loom_ai.backends.capturing_llm import CapturingLLMBackend
from loom_ai.models import ChatMessage, ChatResponse


def _make_inner(response_content: str = "Hello!") -> MagicMock:
    inner = MagicMock()
    inner.chat = AsyncMock(return_value=ChatResponse(content=response_content))
    inner.list_models = AsyncMock(return_value=["model-a", "model-b"])

    async def _stream(*args, **kwargs):
        for chunk in ["Hel", "lo", "!"]:
            yield chunk

    inner.chat_stream = _stream
    return inner


class TestCapturingLLMChat:
    async def test_delegates_to_inner(self):
        inner = _make_inner("world")
        backend = CapturingLLMBackend(inner)
        msgs = [ChatMessage(role="user", content="hi")]
        resp = await backend.chat(msgs, model="test-model")
        assert resp.content == "world"
        inner.chat.assert_awaited_once()

    async def test_captures_to_knowledge(self):
        inner = _make_inner("response")
        knowledge = MagicMock()
        knowledge.ingest = AsyncMock(return_value="doc-1")
        backend = CapturingLLMBackend(inner, knowledge=knowledge)

        msgs = [ChatMessage(role="user", content="question")]
        await backend.chat(msgs, model="m1")

        knowledge.ingest.assert_awaited_once()
        call_args = knowledge.ingest.call_args
        content = call_args[0][0]
        assert "question" in content
        assert "response" in content
        meta = call_args[1]["metadata"]
        assert meta["model"] == "m1"
        assert meta["type"] == "llm_interaction"

    async def test_captures_to_memory(self):
        inner = _make_inner("answer")
        memory = MagicMock()
        memory.store = AsyncMock(return_value="mem-1")
        backend = CapturingLLMBackend(inner, memory=memory)

        msgs = [ChatMessage(role="user", content="ask")]
        await backend.chat(msgs)

        memory.store.assert_awaited_once()
        call_args = memory.store.call_args
        assert "ask" in call_args[0][1]
        assert "answer" in call_args[0][1]
        assert call_args[1]["memory_type"] == "interaction"

    async def test_no_capture_when_no_backends(self):
        inner = _make_inner()
        backend = CapturingLLMBackend(inner)
        msgs = [ChatMessage(role="user", content="hi")]
        resp = await backend.chat(msgs)
        assert resp.content == "Hello!"

    async def test_capture_error_does_not_break_chat(self):
        inner = _make_inner("ok")
        knowledge = MagicMock()
        knowledge.ingest = AsyncMock(side_effect=RuntimeError("db down"))
        backend = CapturingLLMBackend(inner, knowledge=knowledge)

        msgs = [ChatMessage(role="user", content="hi")]
        resp = await backend.chat(msgs)
        assert resp.content == "ok"


class TestCapturingLLMStream:
    async def test_stream_collects_and_captures(self):
        inner = _make_inner()
        knowledge = MagicMock()
        knowledge.ingest = AsyncMock(return_value="doc-2")
        backend = CapturingLLMBackend(inner, knowledge=knowledge)

        msgs = [ChatMessage(role="user", content="stream test")]
        chunks = []
        async for chunk in backend.chat_stream(msgs, model="s1"):
            chunks.append(chunk)

        assert "".join(chunks) == "Hello!"
        knowledge.ingest.assert_awaited_once()
        content = knowledge.ingest.call_args[0][0]
        assert "Hello!" in content


class TestCapturingLLMListModels:
    async def test_delegates_list_models(self):
        inner = _make_inner()
        backend = CapturingLLMBackend(inner)
        models = await backend.list_models()
        assert models == ["model-a", "model-b"]
