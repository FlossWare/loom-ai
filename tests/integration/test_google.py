from __future__ import annotations

import pytest

from loom_ai.backends.http_llm import HttpLLMBackend

from .conftest import SIMPLE_PROMPT, requires_google

pytestmark = requires_google


async def test_chat_returns_content(google_backend: HttpLLMBackend):
    response = await google_backend.chat(SIMPLE_PROMPT, max_tokens=20)
    assert response.content
    assert len(response.content) > 0


async def test_response_fields_populated(google_backend: HttpLLMBackend):
    response = await google_backend.chat(SIMPLE_PROMPT, max_tokens=20)
    assert response.model
    assert response.provider == "google"


async def test_invalid_model_raises(google_backend: HttpLLMBackend):
    with pytest.raises(RuntimeError, match="LLM API error"):
        await google_backend.chat(
            SIMPLE_PROMPT, model="not-a-real-model-xyz", max_tokens=20
        )
