from __future__ import annotations

import pytest

from loom_ai.backends.http_llm import HttpLLMBackend

from .conftest import SIMPLE_PROMPT, requires_mistral

pytestmark = requires_mistral


async def test_chat_returns_content(mistral_backend: HttpLLMBackend):
    response = await mistral_backend.chat(SIMPLE_PROMPT, max_tokens=20)
    assert response.content
    assert len(response.content) > 0


async def test_response_fields_populated(mistral_backend: HttpLLMBackend):
    response = await mistral_backend.chat(SIMPLE_PROMPT, max_tokens=20)
    assert response.model
    assert response.provider == "mistral"


async def test_invalid_model_raises(mistral_backend: HttpLLMBackend):
    with pytest.raises(RuntimeError, match="LLM API error"):
        await mistral_backend.chat(
            SIMPLE_PROMPT, model="not-a-real-model-xyz", max_tokens=20
        )
