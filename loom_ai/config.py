"""LoomConfig registry that wires all backends together.

Backends can be injected explicitly or auto-selected from environment
variables (``LOOM_STORAGE``, ``LOOM_QUEUE``, ``LOOM_LLM_*``, etc.).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from loom_ai.models import Document
from loom_ai.protocols import (
    EmbeddingBackend,
    GraphBackend,
    LLMBackend,
    QueueBackend,
    SearchBackend,
    SecretsBackend,
    StorageBackend,
    TaskRunnerBackend,
)

logger = logging.getLogger(__name__)


@dataclass
class LoomConfig:
    """Central configuration that holds all backend instances."""

    storage: StorageBackend
    queue: QueueBackend
    secrets: SecretsBackend
    llm: LLMBackend | None = None
    embedding: EmbeddingBackend | None = None
    search: SearchBackend | None = None
    graph: GraphBackend | None = None
    task_runner: TaskRunnerBackend | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    async def from_env(cls, **overrides: Any) -> LoomConfig:
        """Build a LoomConfig from environment variables and optional overrides."""
        storage = overrides.pop("storage", None) or await _build_storage()
        queue = overrides.pop("queue", None) or await _build_queue()
        secrets = overrides.pop("secrets", None) or await _build_secrets()
        llm = overrides.pop("llm", None)
        if llm is None and "llm" not in overrides:
            llm = await _build_llm()
        embedding = overrides.pop("embedding", None)
        if embedding is None and "embedding" not in overrides:
            embedding = await _build_embedding()
        search = overrides.pop("search", None)
        if search is None and "search" not in overrides:
            search = await _build_search()
        graph = overrides.pop("graph", None)
        if graph is None and "graph" not in overrides:
            graph = await _build_graph()
        task_runner = overrides.pop("task_runner", None)
        if task_runner is None and "task_runner" not in overrides:
            task_runner = await _build_task_runner()
        return cls(
            storage=storage,
            queue=queue,
            secrets=secrets,
            llm=llm,
            embedding=embedding,
            search=search,
            graph=graph,
            task_runner=task_runner,
            extra=overrides,
        )


async def _build_storage() -> StorageBackend:
    kind = os.environ.get("LOOM_STORAGE", "memory").lower()
    if kind == "postgresql":
        from loom_ai.backends.postgresql import PostgresqlStorageBackend

        return PostgresqlStorageBackend()
    if kind == "memory":
        from loom_ai.backends.memory import MemoryStorageBackend

        return MemoryStorageBackend()
    raise ValueError(f"Unknown storage backend: {kind!r}")


async def _build_queue() -> QueueBackend:
    kind = os.environ.get("LOOM_QUEUE", "memory").lower()
    if kind == "redis":
        from loom_ai.backends.redis_queue import RedisQueueBackend

        return RedisQueueBackend()
    if kind == "memory":
        from loom_ai.backends.memory import MemoryQueueBackend

        return MemoryQueueBackend()
    raise ValueError(f"Unknown queue backend: {kind!r}")


async def _build_secrets() -> SecretsBackend:
    kind = os.environ.get("LOOM_SECRETS", "env").lower()
    if kind == "env":
        from loom_ai.backends.env_secrets import EnvSecretsBackend

        return EnvSecretsBackend()
    if kind == "postgresql":
        from loom_ai.backends.postgresql_secrets import PostgresqlSecretsBackend

        return PostgresqlSecretsBackend()
    raise ValueError(f"Unknown secrets backend: {kind!r}")


async def _build_llm() -> LLMBackend | None:
    provider = os.environ.get("LOOM_LLM_PROVIDER", "").lower()
    if not provider or provider in {"none", "disabled"}:
        return None
    if provider == "free":
        from loom_ai.backends.free_model_router import FreeModelRouter

        return FreeModelRouter()
    if provider in {"openai", "openai-compatible", "http"}:
        from loom_ai.backends.http_llm import HttpLLMBackend

        return HttpLLMBackend()
    if provider == "litellm":
        from loom_ai.backends.litellm_backend import LiteLLMBackend

        return LiteLLMBackend()
    logger.warning("Unknown LLM provider %r; skipping LLM backend", provider)
    return None


async def _build_embedding() -> EmbeddingBackend | None:
    kind = os.environ.get("LOOM_EMBEDDING", "noop").lower()
    if kind in {"noop", "none", "disabled"}:
        return None
    if kind == "openai":
        from loom_ai.backends.openai_embedding import OpenAIEmbeddingBackend

        return OpenAIEmbeddingBackend()
    if kind == "litellm":
        from loom_ai.backends.litellm_embedding import LiteLLMEmbeddingBackend

        return LiteLLMEmbeddingBackend()
    logger.warning("Unknown embedding backend %r; skipping", kind)
    return None


async def _build_search() -> SearchBackend | None:
    kind = os.environ.get("LOOM_SEARCH", "").lower()
    if not kind or kind in {"none", "disabled"}:
        return None
    if kind == "memory":
        from loom_ai.backends.memory_search import MemorySearchBackend

        return MemorySearchBackend()
    logger.warning("Unknown search backend %r; skipping", kind)
    return None


async def _build_graph() -> GraphBackend | None:
    kind = os.environ.get("LOOM_GRAPH", "").lower()
    if not kind or kind in {"none", "disabled"}:
        return None
    if kind == "memory":
        from loom_ai.backends.memory_graph import MemoryGraphBackend

        return MemoryGraphBackend()
    if kind == "orientdb":
        from loom_ai.backends.orientdb_graph import OrientDBGraphBackend

        return OrientDBGraphBackend()
    logger.warning("Unknown graph backend %r; skipping", kind)
    return None


async def _build_task_runner() -> TaskRunnerBackend | None:
    kind = os.environ.get("LOOM_TASK_RUNNER", "").lower()
    if not kind or kind in {"none", "disabled"}:
        return None
    if kind == "local":
        from loom_ai.backends.local_task_runner import LocalTaskRunnerBackend

        return LocalTaskRunnerBackend()
    logger.warning("Unknown task runner %r; skipping", kind)
    return None
