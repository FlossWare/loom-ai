"""Model router backend for loom-ai.

Maps model names to provider backends with priority-based routing and
automatic fallback.  All data is kept in-memory -- no external
dependencies required.

Classes
-------
SimpleModelRouter -- priority-aware model-to-provider routing with
                     fallback, health tracking, and cost estimation
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loom_ai.models_phase1 import ModelInfo, ProviderStatus


@dataclass
class _ProviderEntry:
    """Internal record for a registered provider."""

    name: str
    backend: object  # LLMBackend (duck-typed)
    models: list[str] = field(default_factory=list)
    priority: int = 0
    # Health tracking
    total_calls: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0


class SimpleModelRouter:
    """Priority-aware model router with fallback and health tracking.

    Satisfies :class:`~loom_ai.contracts_phase1.ModelRouter` via
    structural subtyping.  No ABC or inheritance required.

    Providers are registered with a priority (higher wins).  When
    ``route()`` is called, the highest-priority healthy provider for the
    requested model is returned.  If ``fallback=True`` and the primary
    provider has been marked unhealthy, the next-highest-priority
    provider is tried.

    Health tracking is passive -- callers should call
    :meth:`record_success` and :meth:`record_error` after using a
    backend to keep statistics current.
    """

    def __init__(self) -> None:
        # provider_name -> _ProviderEntry
        self._providers: dict[str, _ProviderEntry] = {}
        # model_name -> list of provider_names (sorted by priority desc on access)
        self._model_providers: dict[str, list[str]] = {}
        # model_name -> ModelInfo (optional enrichment)
        self._model_info: dict[str, ModelInfo] = {}

    # ── ModelRouter protocol methods ─────────────────────────────────────

    async def register_provider(
        self,
        name: str,
        backend: object,
        *,
        models: list[str],
        priority: int = 0,
    ) -> None:
        """Register a provider backend with its supported models."""
        entry = _ProviderEntry(
            name=name,
            backend=backend,
            models=list(models),
            priority=priority,
        )
        self._remove_stale_mappings(name, models)
        self._providers[name] = entry

        for model in models:
            providers = self._model_providers.setdefault(model, [])
            if name not in providers:
                providers.append(name)

            if model not in self._model_info:
                self._model_info[model] = ModelInfo(
                    model=model,
                    provider=name,
                )

    def _remove_stale_mappings(self, name: str, new_models: list[str]) -> None:
        """Remove model→provider mappings for models no longer served."""
        old_entry = self._providers.get(name)
        if old_entry is None:
            return
        for old_model in old_entry.models:
            if old_model not in new_models and old_model in self._model_providers:
                plist = self._model_providers[old_model]
                if name in plist:
                    plist.remove(name)

    async def route(self, model: str, *, fallback: bool = True) -> object:
        """Resolve *model* to an ``LLMBackend``.

        Returns the backend from the highest-priority healthy provider.
        When *fallback* is ``True`` and the primary provider is unhealthy,
        the next provider in priority order is tried.

        Raises ``LookupError`` when no provider can serve the model.
        """
        provider_names = self._model_providers.get(model)
        if not provider_names:
            raise LookupError(f"No provider registered for model {model!r}")

        # Sort by priority descending
        sorted_names = sorted(
            provider_names,
            key=lambda n: self._providers[n].priority,
            reverse=True,
        )

        for name in sorted_names:
            entry = self._providers[name]
            if self._is_healthy(entry):
                return entry.backend
            if not fallback:
                break

        if fallback:
            # All providers unhealthy -- return the highest-priority one anyway
            return self._providers[sorted_names[0]].backend

        raise LookupError(
            f"No healthy provider for model {model!r} (fallback disabled)"
        )

    async def list_available_models(self) -> list[ModelInfo]:
        """Return ``ModelInfo`` for every registered model."""
        return list(self._model_info.values())

    async def provider_health(self) -> dict[str, ProviderStatus]:
        """Return per-provider health information."""
        result: dict[str, ProviderStatus] = {}
        for name, entry in self._providers.items():
            error_rate = (
                entry.error_count / entry.total_calls if entry.total_calls > 0 else 0.0
            )
            avg_latency = (
                entry.total_latency_ms / entry.total_calls
                if entry.total_calls > 0
                else 0.0
            )
            result[name] = ProviderStatus(
                name=name,
                healthy=self._is_healthy(entry),
                error_rate=error_rate,
                avg_latency_ms=avg_latency,
                models=list(entry.models),
            )
        return result

    async def estimate_cost(self, model: str, tokens: int) -> float:
        """Return estimated cost in USD for *tokens* on *model*."""
        info = self._model_info.get(model)
        if info is None:
            raise LookupError(f"No model info for {model!r}")
        return info.cost_per_1k_tokens * (tokens / 1000.0)

    # ── Health tracking helpers ──────────────────────────────────────────

    def record_success(self, provider_name: str, *, latency_ms: float = 0.0) -> None:
        """Record a successful call to a provider."""
        entry = self._providers.get(provider_name)
        if entry is not None:
            entry.total_calls += 1
            entry.total_latency_ms += latency_ms

    def record_error(self, provider_name: str, *, latency_ms: float = 0.0) -> None:
        """Record a failed call to a provider."""
        entry = self._providers.get(provider_name)
        if entry is not None:
            entry.total_calls += 1
            entry.error_count += 1
            entry.total_latency_ms += latency_ms

    def set_model_info(self, model: str, info: ModelInfo) -> None:
        """Set or replace ``ModelInfo`` for a model.

        Useful for enriching the default entry created by
        ``register_provider`` with capabilities, context length, and
        cost data.
        """
        self._model_info[model] = info

    # ── Internal ─────────────────────────────────────────────────────────

    @staticmethod
    def _is_healthy(entry: _ProviderEntry, *, threshold: float = 0.5) -> bool:
        """A provider is unhealthy when its error rate exceeds *threshold*."""
        if entry.total_calls == 0:
            return True
        return (entry.error_count / entry.total_calls) < threshold
