"""Phase 7 protocol definitions for loom-ai.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required.  All methods are
async.  Nothing outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.

Phase 7 covers four contract areas:

- **ProviderRegistry** -- model and provider discovery (#66)
- **ProviderCapabilityRegistry** -- provider capability, limits,
  and quota metadata (#67)
- **PolicyRegistry** -- provider policy, privacy, and eligibility metadata (#68)
- **CatalogSynchronizer** -- model catalog synchronization and staleness (#69)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.models_provider import (
        CatalogEntry,
        CatalogSource,
        DiscoveryResult,
        ModelDescriptor,
        ProviderCapabilities,
        ProviderDescriptor,
        ProviderPolicy,
        StalenessReport,
        SyncResult,
    )


# -- Provider Registry (#66) ------------------------------------------------


@runtime_checkable
class ProviderRegistry(Protocol):
    """Dynamic, provider-neutral registry for discovering AI model providers.

    Supports registration, lookup, and discovery of providers and their
    models with freshness, provenance, and confidence metadata.
    """

    async def register_provider(self, provider: ProviderDescriptor) -> None:
        """Register or update a provider in the registry."""
        ...

    async def get_provider(self, provider_id: str) -> ProviderDescriptor | None:
        """Return a provider by id, or ``None`` if not found."""
        ...

    async def list_providers(
        self,
        *,
        provider_type: str | None = None,
        protocol: str | None = None,
    ) -> list[ProviderDescriptor]:
        """Return registered providers, optionally filtered by type or protocol."""
        ...

    async def register_model(self, model: ModelDescriptor) -> None:
        """Register or update a model descriptor."""
        ...

    async def get_model(self, model_id: str) -> ModelDescriptor | None:
        """Return a model descriptor by id, or ``None`` if not found."""
        ...

    async def list_models(
        self,
        *,
        provider_id: str | None = None,
        modality: str | None = None,
    ) -> list[ModelDescriptor]:
        """Return model descriptors, optionally filtered by provider or modality."""
        ...

    async def discover(self) -> DiscoveryResult:
        """Run discovery across all configured sources and return the result."""
        ...

    async def remove_provider(self, provider_id: str) -> bool:
        """Remove a provider and its models from the registry."""
        ...


# -- Capability Registry (#67) ----------------------------------------------


@runtime_checkable
class ProviderCapabilityRegistry(Protocol):
    """Standardized metadata for operational constraints.

    Tracks rate limits, quotas, pricing, and context limits to feed
    routing decisions and observability.  Distinguishes provider-declared
    values from observed measurements.
    """

    async def set_capabilities(self, capabilities: ProviderCapabilities) -> None:
        """Store or update capability metadata for a provider/model pair."""
        ...

    async def get_capabilities(
        self, provider_id: str, model_id: str
    ) -> ProviderCapabilities | None:
        """Return capabilities for a provider/model pair, or ``None``."""
        ...

    async def list_capabilities(
        self,
        *,
        provider_id: str | None = None,
    ) -> list[ProviderCapabilities]:
        """Return capability records, optionally filtered by provider."""
        ...

    async def record_observed_limits(
        self,
        provider_id: str,
        model_id: str,
        *,
        requests_per_minute: int | None = None,
        tokens_per_minute: int | None = None,
    ) -> None:
        """Record empirically observed rate limits for a provider/model pair."""
        ...

    async def check_quota(self, provider_id: str, model_id: str) -> bool:
        """Return ``True`` if the provider/model has remaining quota."""
        ...


# -- Policy Registry (#68) --------------------------------------------------


@runtime_checkable
class PolicyRegistry(Protocol):
    """Provider policies that influence model selection independently of capability.

    Tracks data-retention, training-use, commercial restrictions,
    geographic eligibility, and compliance metadata.  Prevents routing
    from selecting a technically suitable provider that violates policy.
    """

    async def set_policy(self, policy: ProviderPolicy) -> None:
        """Store or update policy metadata for a provider."""
        ...

    async def get_policy(self, provider_id: str) -> ProviderPolicy | None:
        """Return the policy for a provider, or ``None`` if not set."""
        ...

    async def list_policies(self) -> list[ProviderPolicy]:
        """Return all stored provider policies."""
        ...

    async def check_eligible(
        self,
        provider_id: str,
        *,
        region: str | None = None,
        commercial: bool = False,
    ) -> bool:
        """Return ``True`` if the provider is eligible for the given constraints.

        Checks region allowlists/blocklists and commercial-use policy.
        """
        ...

    async def remove_policy(self, provider_id: str) -> bool:
        """Remove a provider policy.  Return ``True`` if it existed."""
        ...


# -- Catalog Synchronizer (#69) ---------------------------------------------


@runtime_checkable
class CatalogSynchronizer(Protocol):
    """Discover, validate, update, and retire model/provider metadata.

    Manages catalog sources, tracks metadata versions and freshness,
    and detects stale, retired, or renamed models.
    """

    async def add_source(self, source: CatalogSource) -> None:
        """Register a catalog discovery source."""
        ...

    async def list_sources(self) -> list[CatalogSource]:
        """Return all registered catalog sources."""
        ...

    async def sync(self, *, source_id: str | None = None) -> SyncResult:
        """Synchronize the catalog from one or all sources.

        When *source_id* is ``None``, all enabled sources are synced.
        """
        ...

    async def get_entry(self, entry_id: str) -> CatalogEntry | None:
        """Return a catalog entry by id, or ``None`` if not found."""
        ...

    async def staleness_report(self) -> StalenessReport:
        """Analyze catalog freshness and return a staleness report."""
        ...

    async def retire_entry(self, entry_id: str) -> bool:
        """Mark a catalog entry as retired.  Return ``True`` if it existed."""
        ...

    async def history(self, entry_id: str, *, limit: int = 10) -> list[CatalogEntry]:
        """Return historical versions of a catalog entry for reproducibility."""
        ...
