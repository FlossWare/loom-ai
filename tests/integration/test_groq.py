from __future__ import annotations

import pytest

from loom_ai.backends.http_llm import HttpLLMBackend

from .conftest import SIMPLE_PROMPT, requires_groq

pytestmark = requires_groq


async def test_chat_returns_content(groq_backend: HttpLLMBackend):
    response = await groq_backend.chat(SIMPLE_PROMPT, max_tokens=20)
    assert response.content
    assert len(response.content) > 0


async def test_response_fields_populated(groq_backend: HttpLLMBackend):
    response = await groq_backend.chat(SIMPLE_PROMPT, max_tokens=20)
    assert response.model
    assert response.provider == "groq"


async def test_invalid_model_raises(groq_backend: HttpLLMBackend):
    with pytest.raises(RuntimeError, match="LLM API error"):
        await groq_backend.chat(
            SIMPLE_PROMPT, model="not-a-real-model-xyz", max_tokens=20
        )
