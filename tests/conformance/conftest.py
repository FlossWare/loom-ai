"""Pytest fixtures providing backend instances for conformance tests.

Default fixtures use the in-memory implementations shipped with the core
package.  Override any fixture in a downstream ``conftest.py`` to run the
same conformance suite against a PostgreSQL, Redis, or other backend.
"""

from __future__ import annotations

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
