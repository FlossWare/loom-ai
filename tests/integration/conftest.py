from __future__ import annotations

import os

import pytest

from loom_ai.backends.http_llm import HttpLLMBackend
from loom_ai.models import ChatMessage

_USER_AGENT = "loom-ai/1.0 (Python)"

requires_mistral = pytest.mark.skipif(
    not os.environ.get("MISTRAL_API_KEY"),
    reason="MISTRAL_API_KEY not set",
)

requires_google = pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"),
    reason="GOOGLE_API_KEY not set",
)

requires_groq = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set",
)


def _patch_user_agent(backend: HttpLLMBackend) -> HttpLLMBackend:
    original = backend._headers

    def _headers_with_ua() -> dict[str, str]:
        headers = original()
        headers["User-Agent"] = _USER_AGENT
        return headers

    backend._headers = _headers_with_ua  # type: ignore[assignment]
    return backend


SIMPLE_PROMPT = [ChatMessage(role="user", content="Say hello in one word.")]


@pytest.fixture()
def mistral_backend() -> HttpLLMBackend:
    return HttpLLMBackend(
        base_url="https://api.mistral.ai/v1",
        api_key=os.environ.get("MISTRAL_API_KEY", ""),
        default_model="mistral-small-latest",
        provider_name="mistral",
    )


@pytest.fixture()
def google_backend() -> HttpLLMBackend:
    return HttpLLMBackend(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key=os.environ.get("GOOGLE_API_KEY", ""),
        default_model="gemini-2.5-flash",
        provider_name="google",
    )


@pytest.fixture()
def groq_backend() -> HttpLLMBackend:
    backend = HttpLLMBackend(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ.get("GROQ_API_KEY", ""),
        default_model="qwen/qwen3.6-27b",
        provider_name="groq",
    )
    return _patch_user_agent(backend)
