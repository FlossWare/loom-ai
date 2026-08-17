"""Property-based fuzz tests for LLMBackend (StubLLMBackend).

Uses Hypothesis to generate edge-case message content and verifies that
LLM operations never crash with valid-typed but unusual inputs.  Uses a
stub backend that returns fixed responses without network calls.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from hypothesis import given, settings
from hypothesis import strategies as st

from loom_ai.models import ChatMessage, ChatResponse


def _run(coro):
    return asyncio.run(coro)


class StubLLMBackend:
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        return ChatResponse(
            content="stub response",
            model=model or "stub-model",
            provider="stub",
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        yield "stub"
        yield " response"

    async def list_models(self) -> list[str]:
        return ["stub-model"]


FUZZ_TEXT = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "M", "N", "P", "S", "Z")),
    min_size=0,
    max_size=5000,
)

FUZZ_ROLE = st.sampled_from(["user", "assistant", "system"])

FUZZ_MESSAGE = st.builds(ChatMessage, role=FUZZ_ROLE, content=FUZZ_TEXT)


class TestLLMFuzz:
    @given(messages=st.lists(FUZZ_MESSAGE, min_size=1, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_chat_never_crashes(self, messages):
        backend = StubLLMBackend()
        result = _run(backend.chat(messages))
        assert isinstance(result, ChatResponse)
        assert isinstance(result.content, str)
        assert len(result.content) > 0

    @given(
        messages=st.lists(FUZZ_MESSAGE, min_size=1, max_size=10),
        model=st.one_of(st.none(), FUZZ_TEXT),
    )
    @settings(max_examples=50, deadline=None)
    def test_chat_with_model_kwarg(self, messages, model):
        backend = StubLLMBackend()
        result = _run(backend.chat(messages, model=model))
        assert isinstance(result, ChatResponse)

    @given(
        messages=st.lists(FUZZ_MESSAGE, min_size=1, max_size=10),
        temperature=st.floats(min_value=0.0, max_value=2.0),
        max_tokens=st.one_of(st.none(), st.integers(min_value=1, max_value=100000)),
    )
    @settings(max_examples=50, deadline=None)
    def test_chat_with_temperature_and_max_tokens(
        self, messages, temperature, max_tokens
    ):
        backend = StubLLMBackend()
        result = _run(backend.chat(messages, temperature=temperature, max_tokens=max_tokens))
        assert isinstance(result, ChatResponse)

    @given(messages=st.lists(FUZZ_MESSAGE, min_size=1, max_size=10))
    @settings(max_examples=50, deadline=None)
    def test_chat_stream_yields_strings(self, messages):
        backend = StubLLMBackend()

        async def collect():
            deltas = []
            async for chunk in backend.chat_stream(messages):
                assert isinstance(chunk, str)
                deltas.append(chunk)
            return deltas

        deltas = _run(collect())
        assert len(deltas) > 0

    @given(messages=st.lists(FUZZ_MESSAGE, min_size=1, max_size=10))
    @settings(max_examples=50, deadline=None)
    def test_chat_stream_concatenation_nonempty(self, messages):
        backend = StubLLMBackend()

        async def collect():
            content = ""
            async for chunk in backend.chat_stream(messages):
                content += chunk
            return content

        content = _run(collect())
        assert len(content) > 0

    @given(content=FUZZ_TEXT)
    @settings(max_examples=50, deadline=None)
    def test_single_message_with_fuzz_content(self, content):
        backend = StubLLMBackend()
        msg = ChatMessage(role="user", content=content)
        result = _run(backend.chat([msg]))
        assert isinstance(result, ChatResponse)

    def test_list_models_returns_list(self):
        backend = StubLLMBackend()
        models = _run(backend.list_models())
        assert isinstance(models, list)
        assert len(models) >= 1
        assert all(isinstance(m, str) for m in models)

    @given(
        content=st.text(
            alphabet=st.characters(
                codec="utf-8",
                categories=("L", "M", "N", "P", "S", "Z", "C"),
            ),
            min_size=1,
            max_size=10000,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_chat_with_very_long_and_special_content(self, content):
        backend = StubLLMBackend()
        msg = ChatMessage(role="user", content=content)
        result = _run(backend.chat([msg]))
        assert isinstance(result, ChatResponse)

    @given(
        role=st.text(min_size=1, max_size=50),
        content=FUZZ_TEXT,
    )
    @settings(max_examples=50, deadline=None)
    def test_chat_with_arbitrary_role(self, role, content):
        backend = StubLLMBackend()
        msg = ChatMessage(role=role, content=content)
        result = _run(backend.chat([msg]))
        assert isinstance(result, ChatResponse)


class TestLLMConcurrency:
    async def test_concurrent_chat_calls(self):
        backend = StubLLMBackend()

        async def call(i):
            msg = ChatMessage(role="user", content=f"message {i}")
            return await backend.chat([msg])

        results = await asyncio.gather(*(call(i) for i in range(50)))

        assert len(results) == 50
        assert all(isinstance(r, ChatResponse) for r in results)

    async def test_concurrent_stream_calls(self):
        backend = StubLLMBackend()

        async def stream(i):
            msg = ChatMessage(role="user", content=f"stream {i}")
            content = ""
            async for chunk in backend.chat_stream([msg]):
                content += chunk
            return content

        results = await asyncio.gather(*(stream(i) for i in range(20)))

        assert len(results) == 20
        assert all(len(r) > 0 for r in results)
