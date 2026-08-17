"""Pytest fixtures providing backend instances for conformance tests.

Default fixtures use the in-memory implementations shipped with the core
package.  Override any fixture in a downstream ``conftest.py`` to run the
same conformance suite against a PostgreSQL, Redis, or other backend.
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from loom_ai import LoomConfig
from loom_ai.backends.env_secrets import EnvSecretsBackend
from loom_ai.backends.memory import (
    MemoryGraphBackend,
    MemoryQueueBackend,
    MemorySearchBackend,
    MemoryStorageBackend,
    NoopEmbeddingBackend,
)
from loom_ai.backends.memory_mcp import MemoryResourceProvider, MemoryToolProvider
from loom_ai.execution import NoopTaskRunner
from loom_ai.models import (
    ChatMessage,
    ChatResponse,
    ResourceDefinition,
    ToolDefinition,
)

# ── Stub LLM backend (no network required) ──────────────────────────────


class StubLLMBackend:
    """Minimal in-memory LLM backend for conformance testing.

    Returns a fixed response for ``chat()``, yields a single delta for
    ``chat_stream()``, and exposes one pseudo-model via ``list_models()``.
    No network calls are made.
    """

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


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def storage_backend() -> MemoryStorageBackend:
    """Fresh in-memory storage backend for each test."""
    return MemoryStorageBackend()


@pytest.fixture
def queue_backend() -> MemoryQueueBackend:
    """Fresh in-memory queue backend for each test."""
    return MemoryQueueBackend()


@pytest.fixture
def secrets_backend() -> EnvSecretsBackend:
    """Fresh env-secrets backend with an isolated in-memory store."""
    return EnvSecretsBackend(overrides={"API_KEY": "test-key-123"})


@pytest.fixture
def embedding_backend() -> NoopEmbeddingBackend:
    """Fresh noop embedding backend for each test."""
    return NoopEmbeddingBackend()


@pytest.fixture
def search_backend() -> MemorySearchBackend:
    """Fresh in-memory search backend for each test."""
    return MemorySearchBackend()


@pytest.fixture
def graph_backend() -> MemoryGraphBackend:
    """Fresh in-memory graph backend for each test."""
    return MemoryGraphBackend()


@pytest.fixture
def llm_backend() -> StubLLMBackend:
    """Fresh stub LLM backend for each test."""
    return StubLLMBackend()


@pytest.fixture
def tool_provider() -> MemoryToolProvider:
    """Fresh in-memory tool provider with one registered tool."""
    provider = MemoryToolProvider()

    async def _echo(**kwargs: object) -> dict:
        return {"echo": kwargs}

    provider.register(
        ToolDefinition(
            name="echo",
            description="Echoes back the input arguments.",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        ),
        _echo,
    )
    return provider


@pytest.fixture
def resource_provider() -> MemoryResourceProvider:
    """Fresh in-memory resource provider with one registered resource."""
    provider = MemoryResourceProvider()
    provider.register(
        ResourceDefinition(
            uri="loom://test/greeting",
            name="greeting",
            description="A test greeting resource.",
            mime_type="text/plain",
        ),
        "Hello, Loom!",
    )
    return provider


@pytest.fixture
def task_runner() -> NoopTaskRunner:
    """Fresh noop task runner for each test."""
    return NoopTaskRunner()


@pytest.fixture
def loom_config() -> LoomConfig:
    """Full LoomConfig with all in-memory backends wired up."""
    return LoomConfig(
        storage=MemoryStorageBackend(),
        queue=MemoryQueueBackend(),
        secrets=EnvSecretsBackend(),
        embedding=NoopEmbeddingBackend(),
        search=MemorySearchBackend(),
        graph=MemoryGraphBackend(),
    )
