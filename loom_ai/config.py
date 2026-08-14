"""LoomConfig registry that wires all backends together.

Backends can be injected directly at construction time (for testing and
explicit wiring) or auto-detected from ``LOOM_*`` environment variables
via ``from_env()``.

The core package ships only stdlib-based backends.  Optional extras
(PostgreSQL, Redis, OrientDB, OpenAI, etc.) are loaded lazily so the
core carries zero third-party dependencies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from loom_ai.protocols import (
    EmbeddingBackend,
    GraphBackend,
    LLMBackend,
    QueueBackend,
    SearchBackend,
    SecretsBackend,
    StorageBackend,
)


@dataclass
class LoomConfig:
    """Central registry providing typed access to every backend.

    Attributes
    ----------
    storage:   Document and chunk persistence.
    queue:     Named task queue with fetch/complete semantics.
    secrets:   Secret and API-key access.
    embedding: Text-to-vector embedding generation.
    search:    Full-text, semantic, and hybrid search.
    graph:     Optional knowledge graph (``None`` when disabled).
    llm:       Optional LLM chat completions (``None`` when unconfigured).
    """

    storage: StorageBackend
    queue: QueueBackend
    secrets: SecretsBackend
    embedding: EmbeddingBackend
    search: SearchBackend
    graph: GraphBackend | None = None
    llm: LLMBackend | None = None

    # ── Factory ──────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> LoomConfig:
        """Build a LoomConfig by reading ``LOOM_*`` environment variables.

        Environment variables and their defaults::

            LOOM_STORAGE        memory | postgresql           (default: memory)
            LOOM_QUEUE          memory | redis                (default: memory)
            LOOM_SECRETS        env | dotenv | postgresql     (default: env)
            LOOM_EMBEDDING      noop | openai | litellm       (default: noop)
            LOOM_SEARCH         memory | postgresql           (default: memory)
            LOOM_GRAPH          disabled | memory | orientdb  (default: disabled)
            LOOM_LLM_BASE_URL   Base URL for OpenAI-compatible endpoint
            LOOM_LLM_API_KEY    Optional bearer token for the LLM endpoint
            LOOM_LLM_MODEL      Default model id for the LLM backend
            LOOM_SECRETS_FILE   Path to .env file (when LOOM_SECRETS=dotenv)
            LOOM_SECRETS_PREFIX Key prefix for env secret lookup
        """
        return cls(
            storage=cls._build_storage(
                os.environ.get("LOOM_STORAGE", "memory"),
            ),
            queue=cls._build_queue(
                os.environ.get("LOOM_QUEUE", "memory"),
            ),
            secrets=cls._build_secrets(
                os.environ.get("LOOM_SECRETS", "env"),
            ),
            embedding=cls._build_embedding(
                os.environ.get("LOOM_EMBEDDING", "noop"),
            ),
            search=cls._build_search(
                os.environ.get("LOOM_SEARCH", "memory"),
            ),
            graph=cls._build_graph(
                os.environ.get("LOOM_GRAPH", "disabled"),
            ),
            llm=cls._build_llm(),
        )

    # ── Private builders (lazy imports keep core dependency-free) ─────

    @staticmethod
    def _build_storage(kind: str) -> StorageBackend:
        if kind == "memory":
            from loom_ai.backends.memory import MemoryStorageBackend

            return MemoryStorageBackend()
        if kind == "postgresql":
            try:
                from loom_ai.backends.postgresql import (
                    PostgresqlStorageBackend,  # type: ignore[import-not-found]
                )
            except ImportError as exc:
                raise ImportError(
                    "PostgreSQL storage requires 'asyncpg'.  "
                    "Install with: pip install loom-ai[postgresql]"
                ) from exc
            return PostgresqlStorageBackend.from_env()  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown storage backend: {kind!r}.  "
            f"Valid options: memory, postgresql"
        )

    @staticmethod
    def _build_queue(kind: str) -> QueueBackend:
        if kind == "memory":
            from loom_ai.backends.memory import MemoryQueueBackend

            return MemoryQueueBackend()
        if kind == "redis":
            try:
                from loom_ai.backends.redis import (
                    RedisQueueBackend,  # type: ignore[import-not-found]
                )
            except ImportError as exc:
                raise ImportError(
                    "Redis queue requires the 'redis' package.  "
                    "Install with: pip install loom-ai[redis]"
                ) from exc
            return RedisQueueBackend.from_env()  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown queue backend: {kind!r}.  "
            f"Valid options: memory, redis"
        )

    @staticmethod
    def _build_secrets(kind: str) -> SecretsBackend:
        if kind == "env":
            from loom_ai.backends.env_secrets import EnvSecretsBackend

            return EnvSecretsBackend(
                prefix=os.environ.get("LOOM_SECRETS_PREFIX", ""),
            )
        if kind == "dotenv":
            from loom_ai.backends.env_secrets import EnvSecretsBackend

            return EnvSecretsBackend(
                env_file=os.environ.get("LOOM_SECRETS_FILE", ".env"),
                prefix=os.environ.get("LOOM_SECRETS_PREFIX", ""),
            )
        if kind == "postgresql":
            try:
                from loom_ai.backends.postgresql import (
                    PostgresqlSecretsBackend,  # type: ignore[import-not-found]
                )
            except ImportError as exc:
                raise ImportError(
                    "PostgreSQL secrets requires 'asyncpg'.  "
                    "Install with: pip install loom-ai[postgresql]"
                ) from exc
            return PostgresqlSecretsBackend.from_env()  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown secrets backend: {kind!r}.  "
            f"Valid options: env, dotenv, postgresql"
        )

    @staticmethod
    def _build_embedding(kind: str) -> EmbeddingBackend:
        if kind == "noop":
            from loom_ai.backends.memory import NoopEmbeddingBackend

            return NoopEmbeddingBackend()
        if kind == "openai":
            try:
                from loom_ai.backends.openai_embedding import (
                    OpenAIEmbeddingBackend,  # type: ignore[import-not-found]
                )
            except ImportError as exc:
                raise ImportError(
                    "OpenAI embeddings require the 'openai' package.  "
                    "Install with: pip install loom-ai[openai]"
                ) from exc
            return OpenAIEmbeddingBackend.from_env()  # type: ignore[attr-defined]
        if kind == "litellm":
            try:
                from loom_ai.backends.litellm_embedding import (
                    LiteLLMEmbeddingBackend,  # type: ignore[import-not-found]
                )
            except ImportError as exc:
                raise ImportError(
                    "LiteLLM embeddings require the 'litellm' package.  "
                    "Install with: pip install loom-ai[litellm]"
                ) from exc
            return LiteLLMEmbeddingBackend.from_env()  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown embedding backend: {kind!r}.  "
            f"Valid options: noop, openai, litellm"
        )

    @staticmethod
    def _build_search(kind: str) -> SearchBackend:
        if kind == "memory":
            from loom_ai.backends.memory import MemorySearchBackend

            return MemorySearchBackend()
        if kind == "postgresql":
            try:
                from loom_ai.backends.postgresql import (
                    PostgresqlSearchBackend,  # type: ignore[import-not-found]
                )
            except ImportError as exc:
                raise ImportError(
                    "PostgreSQL search requires 'asyncpg' and 'pgvector'.  "
                    "Install with: pip install loom-ai[postgresql]"
                ) from exc
            return PostgresqlSearchBackend.from_env()  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown search backend: {kind!r}.  "
            f"Valid options: memory, postgresql"
        )

    @staticmethod
    def _build_graph(kind: str) -> GraphBackend | None:
        if kind == "disabled":
            return None
        if kind == "memory":
            from loom_ai.backends.memory import MemoryGraphBackend

            return MemoryGraphBackend()
        if kind == "orientdb":
            try:
                from loom_ai.backends.orientdb import (
                    OrientDBGraphBackend,  # type: ignore[import-not-found]
                )
            except ImportError as exc:
                raise ImportError(
                    "OrientDB graph requires 'pyorient'.  "
                    "Install with: pip install loom-ai[orientdb]"
                ) from exc
            return OrientDBGraphBackend.from_env()  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown graph backend: {kind!r}.  "
            f"Valid options: disabled, memory, orientdb"
        )

    @staticmethod
    def _build_llm() -> LLMBackend | None:
        base_url = os.environ.get("LOOM_LLM_BASE_URL")
        if not base_url:
            return None

        from loom_ai.backends.http_llm import HttpLLMBackend

        return HttpLLMBackend(
            base_url=base_url,
            api_key=os.environ.get("LOOM_LLM_API_KEY", ""),
            default_model=os.environ.get("LOOM_LLM_MODEL", "gpt-4o-mini"),
            provider_name=os.environ.get(
                "LOOM_LLM_PROVIDER", "openai-compatible"
            ),
        )
