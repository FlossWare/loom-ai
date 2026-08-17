"""Conformance tests for LLMBackend implementations.

Any backend that satisfies the LLMBackend protocol should pass all
tests in this module.  Override the ``llm_backend`` fixture in a
downstream ``conftest.py`` to plug in a different implementation.
"""

from __future__ import annotations

from loom_ai.models import ChatMessage, ChatResponse

# -- chat() ---------------------------------------------------------------


async def test_chat_returns_chat_response(llm_backend):
    """chat() returns a ChatResponse instance."""
    messages = [ChatMessage(role="user", content="Hello")]
    result = await llm_backend.chat(messages)

    assert isinstance(result, ChatResponse)
    assert isinstance(result.content, str)
    assert len(result.content) > 0


async def test_chat_with_model_kwarg(llm_backend):
    """chat() accepts an explicit model keyword argument."""
    messages = [ChatMessage(role="user", content="ping")]
    result = await llm_backend.chat(messages, model="stub-model")

    assert isinstance(result, ChatResponse)


async def test_chat_with_temperature_and_max_tokens(llm_backend):
    """chat() accepts temperature and max_tokens keyword arguments."""
    messages = [ChatMessage(role="user", content="test")]
    result = await llm_backend.chat(messages, temperature=0.0, max_tokens=10)

    assert isinstance(result, ChatResponse)


# -- chat_stream() --------------------------------------------------------


async def test_chat_stream_yields_strings(llm_backend):
    """chat_stream() yields string deltas."""
    messages = [ChatMessage(role="user", content="stream this")]
    deltas: list[str] = []

    async for chunk in llm_backend.chat_stream(messages):
        assert isinstance(chunk, str)
        deltas.append(chunk)

    assert len(deltas) > 0


async def test_chat_stream_concatenation_is_nonempty(llm_backend):
    """Concatenating chat_stream() deltas produces non-empty content."""
    messages = [ChatMessage(role="user", content="stream")]
    content = ""

    async for chunk in llm_backend.chat_stream(messages):
        content += chunk

    assert len(content) > 0


# -- list_models() --------------------------------------------------------


async def test_list_models_returns_list(llm_backend):
    """list_models() returns a list of strings."""
    models = await llm_backend.list_models()

    assert isinstance(models, list)
    assert len(models) >= 1
    assert all(isinstance(m, str) for m in models)
