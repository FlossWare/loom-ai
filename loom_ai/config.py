"""LoomConfig registry that wires all backends together.

Backends can be injected directly at construction time (for testing and
explicit wiring) or auto-detected from ``LOOM_*`` environment variables
via ``from_env()``.

The core package ships only stdlib-based backends.  Optional extras
(PostgreSQL, Redis, OrientDB, OpenAI, etc.) are loaded lazily so the
core carries zero third-party dependencies.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from loom_ai.backends.adaptive_router import AdaptiveModelRouter
from loom_ai.consensus import ConsensusEngine
from loom_ai.contracts_graph import KnowledgeGraph
from loom_ai.protocols import (
    EmbeddingBackend,
    LLMBackend,
    QueueBackend,
    ResourceProvider,
    SearchBackend,
    SecretsBackend,
    StorageBackend,
    ToolProvider,
)

GraphLike = KnowledgeGraph
logger = logging.getLogger(__name__)


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
    consensus: Optional multi-model consensus engine wrapping *llm*.
    tools:     Optional MCP tool provider (``None`` when unconfigured).
    resources: Optional MCP resource provider (``None`` when unconfigured).
    router:    Optional adaptive model router with Thompson Sampling
               (``None`` when unconfigured).
    """

    storage: StorageBackend
    queue: QueueBackend
    secrets: SecretsBackend
    embedding: EmbeddingBackend
    search: SearchBackend
    graph: GraphLike | None = None
    llm: LLMBackend | None = None
    consensus: ConsensusEngine | None = None
    tools: ToolProvider | None = None
    resources: ResourceProvider | None = None
    router: AdaptiveModelRouter | None = None

    async def close(self) -> None:
        """Shut down all resource-owning backends."""
        try:
            from loom_ai.backends.postgresql import (
                close_shared_pool,
            )

            await close_shared_pool()
        except ImportError:
            pass

        for name in self.__dataclass_fields__:
            backend = getattr(self, name, None)
            if backend is None:
                continue
            if not hasattr(backend, "close"):
                continue
            try:
                await backend.close()
            except Exception:
                logger.warning(
                    "Failed to close %s backend", name
                )

    @classmethod
    async def from_env(cls) -> LoomConfig:
        """Build a LoomConfig by reading ``LOOM_*`` environment variables.

        This method is ``async`` because some optional backends (e.g.
        PostgreSQL) require awaiting connection-pool creation during
        factory construction.

        Environment variables and their defaults::

            LOOM_STORAGE        memory | postgresql           (default: memory)
            LOOM_QUEUE          memory | redis                (default: memory)
            LOOM_SECRETS        env | dotenv | postgresql     (default: env)
            LOOM_EMBEDDING      noop | openai | litellm       (default: noop)
            LOOM_SEARCH         memory | postgresql           (default: memory)
            LOOM_GRAPH          disabled | memory | orientdb  (default: disabled)
            LOOM_LLM_PROVIDER   free | openai-compatible        (default: openai-compatible)
            LOOM_LLM_BASE_URL   Base URL (required when provider=openai-compatible)
            LOOM_LLM_API_KEY    Optional bearer token for the LLM endpoint
            LOOM_LLM_MODEL      Default model id for the LLM backend
            LOOM_SECRETS_FILE   Path to .env file (when LOOM_SECRETS=dotenv)
            LOOM_SECRETS_PREFIX Key prefix for env secret lookup
            LOOM_SECRETS_KEY    Fernet key for encrypting PG-backed secrets
            LOOM_CAPTURE_LLM    0 | 1                      (default: 0)
            LOOM_TOOLS          disabled | memory          (default: disabled)
            LOOM_RESOURCES      disabled | memory          (default: disabled)
        """
        storage_kind = os.environ.get("LOOM_STORAGE", "memory")
        secrets_kind = os.environ.get("LOOM_SECRETS", "env")
        search_kind = os.environ.get("LOOM_SEARCH", "memory")

        pg_pool: Any = None
        built: list[tuple[str, Any]] = []
        try:
            if "postgresql" in (
                storage_kind,
                secrets_kind,
                search_kind,
            ):
                from loom_ai.backends.postgresql import (
                    get_shared_pool,
                )

                pg_pool = await get_shared_pool()

            storage = await cls._build_storage(
                storage_kind, pool=pg_pool
            )
            built.append(("storage", storage))

            queue = await cls._build_queue(
                os.environ.get("LOOM_QUEUE", "memory"),
            )
            built.append(("queue", queue))

            secrets = await cls._build_secrets(
                secrets_kind, pool=pg_pool
            )
            built.append(("secrets", secrets))

            embedding = await cls._build_embedding(
                os.environ.get("LOOM_EMBEDDING", "noop"),
            )
            built.append(("embedding", embedding))

            search = await cls._build_search(
                search_kind, pool=pg_pool
            )
            built.append(("search", search))

            graph = await cls._build_graph(
                os.environ.get("LOOM_GRAPH", "disabled"),
            )
            built.append(("graph", graph))

            llm = await cls._build_llm()
            if llm is not None and (
                os.environ.get("LOOM_CAPTURE_LLM") == "1"
            ):
                from loom_ai.backends.capturing_llm import (
                    CapturingLLMBackend,
                )

                llm = CapturingLLMBackend(llm)
            built.append(("llm", llm))

            consensus = (
                ConsensusEngine(llm)
                if llm is not None
                else None
            )

            tools = cls._build_tools(
                os.environ.get("LOOM_TOOLS", "disabled"),
            )
            resources = cls._build_resources(
                os.environ.get("LOOM_RESOURCES", "disabled"),
            )
            router = cls._build_router(
                os.environ.get("LOOM_ROUTER", "disabled"),
            )

            return cls(
                storage=storage,
                queue=queue,
                secrets=secrets,
                embedding=embedding,
                search=search,
                graph=graph,
                llm=llm,
                consensus=consensus,
                tools=tools,
                resources=resources,
                router=router,
            )
        except Exception:
            for name, backend in reversed(built):
                if backend is None:
                    continue
                if not hasattr(backend, "close"):
                    continue
                try:
                    await backend.close()
                except Exception:
                    logger.warning(
                        "Cleanup: failed to close %s",
                        name,
                    )
            if pg_pool is not None:
                try:
                    from loom_ai.backends.postgresql import (
                        close_shared_pool,
                    )

                    await close_shared_pool()
                except Exception:
                    logger.warning(
                        "Cleanup: failed to close PG pool"
                    )
            raise

    @staticmethod
    async def _build_storage(kind: str, *, pool: Any = None) -> StorageBackend:
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
                    "Install with: pip install flossware-loom-ai[postgresql]"
                ) from exc
            return await PostgresqlStorageBackend.from_env(pool=pool)  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown storage backend: {kind!r}.  Valid options: memory, postgresql"
        )

    @staticmethod
    async def _build_queue(kind: str) -> QueueBackend:
        if kind == "memory":
            from loom_ai.backends.memory import MemoryQueueBackend

            return MemoryQueueBackend()
        if kind == "redis":
            try:
                from loom_ai.backends.redis_queue import (
                    RedisQueueBackend,  # type: ignore[import-not-found]
                )
            except ImportError as exc:
                raise ImportError(
                    "Redis queue requires the 'redis' package.  "
                    "Install with: pip install flossware-loom-ai[redis]"
                ) from exc
            return await RedisQueueBackend.from_env()  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown queue backend: {kind!r}.  Valid options: memory, redis"
        )

    @staticmethod
    async def _build_secrets(kind: str, *, pool: Any = None) -> SecretsBackend:
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
                    "Install with: pip install flossware-loom-ai[postgresql]"
                ) from exc
            return await PostgresqlSecretsBackend.from_env(pool=pool)  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown secrets backend: {kind!r}.  "
            f"Valid options: env, dotenv, postgresql"
        )

    @staticmethod
    async def _build_embedding(kind: str) -> EmbeddingBackend:
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
                    "Install with: pip install flossware-loom-ai[openai]"
                ) from exc
            return await OpenAIEmbeddingBackend.from_env()  # type: ignore[attr-defined]
        if kind == "litellm":
            try:
                from loom_ai.backends.litellm_embedding import (
                    LiteLLMEmbeddingBackend,  # type: ignore[import-not-found]
                )
            except ImportError as exc:
                raise ImportError(
                    "LiteLLM embeddings require the 'litellm' package.  "
                    "Install with: pip install flossware-loom-ai[litellm]"
                ) from exc
            return await LiteLLMEmbeddingBackend.from_env()  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown embedding backend: {kind!r}.  "
            f"Valid options: noop, openai, litellm"
        )

    @staticmethod
    async def _build_search(kind: str, *, pool: Any = None) -> SearchBackend:
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
                    "Install with: pip install flossware-loom-ai[postgresql]"
                ) from exc
            return await PostgresqlSearchBackend.from_env(pool=pool)  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown search backend: {kind!r}.  Valid options: memory, postgresql"
        )

    @staticmethod
    async def _build_graph(kind: str) -> KnowledgeGraph | None:
        if kind == "disabled":
            return None
        if kind == "memory":
            from loom_ai.backends.graph import InMemoryKnowledgeGraph

            return InMemoryKnowledgeGraph()
        if kind == "orientdb":
            try:
                from loom_ai.backends.orientdb import (
                    OrientDBGraphBackend,  # type: ignore[import-not-found]
                )
            except ImportError as exc:
                raise ImportError(
                    "OrientDB graph requires 'pyorient'.  "
                    "Install with: pip install flossware-loom-ai[orientdb]"
                ) from exc
            return await OrientDBGraphBackend.from_env()  # type: ignore[attr-defined]
        raise ValueError(
            f"Unknown graph backend: {kind!r}.  "
            f"Valid options: disabled, memory, orientdb"
        )

    @staticmethod
    async def _build_llm() -> LLMBackend | None:
        provider = os.environ.get("LOOM_LLM_PROVIDER", "openai-compatible")

        if provider == "free":
            from loom_ai.backends.free_model_router import FreeModelRouter

            router = FreeModelRouter(
                pg_dsn=os.environ.get("LOOM_PG_DSN", ""),
            )
            await router.initialize()
            return router

        base_url = os.environ.get("LOOM_LLM_BASE_URL")
        if not base_url:
            return None

        from loom_ai.backends.http_llm import HttpLLMBackend

        return HttpLLMBackend(
            base_url=base_url,
            api_key=os.environ.get("LOOM_LLM_API_KEY", ""),
            default_model=os.environ.get("LOOM_LLM_MODEL", "gpt-4o-mini"),
            provider_name=provider,
        )

    @staticmethod
    def _build_tools(kind: str) -> ToolProvider | None:
        if kind == "disabled":
            return None
        if kind == "memory":
            from loom_ai.backends.memory_mcp import MemoryToolProvider

            return MemoryToolProvider()
        raise ValueError(
            f"Unknown tools backend: {kind!r}.  Valid options: disabled, memory"
        )

    @staticmethod
    def _build_resources(kind: str) -> ResourceProvider | None:
        if kind == "disabled":
            return None
        if kind == "memory":
            from loom_ai.backends.memory_mcp import MemoryResourceProvider

            return MemoryResourceProvider()
        raise ValueError(
            f"Unknown resources backend: {kind!r}.  Valid options: disabled, memory"
        )

    @staticmethod
    def _build_router(kind: str) -> AdaptiveModelRouter | None:
        if kind == "disabled":
            return None
        if kind == "adaptive":
            return AdaptiveModelRouter()
        raise ValueError(
            f"Unknown router backend: {kind!r}.  Valid options: disabled, adaptive"
        )
