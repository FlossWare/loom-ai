"""In-memory backends for Phase 7 provider discovery protocols.

Classes
-------
InMemoryProviderRegistry           -- dict-backed provider and model discovery
InMemoryProviderCapabilityRegistry -- rate limits, quotas, and pricing metadata
InMemoryPolicyRegistry             -- provider policy, privacy, and eligibility
InMemoryCatalogSynchronizer        -- model catalog sync and staleness detection
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from loom_ai.models_provider import (
    CatalogEntry,
    CatalogSource,
    DiscoveryResult,
    ModelDescriptor,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderPolicy,
    RateLimits,
    StalenessReport,
    SyncResult,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════════
# ProviderRegistry (#66)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryProviderRegistry:
    """Dict-backed provider and model registry with filtering and discovery."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderDescriptor] = {}
        self._models: dict[str, ModelDescriptor] = {}

    async def register_provider(self, provider: ProviderDescriptor) -> None:
        self._providers[provider.id] = provider

    async def get_provider(self, provider_id: str) -> ProviderDescriptor | None:
        return self._providers.get(provider_id)

    async def list_providers(
        self,
        *,
        provider_type: str | None = None,
        protocol: str | None = None,
    ) -> list[ProviderDescriptor]:
        results = list(self._providers.values())
        if provider_type is not None:
            results = [p for p in results if p.provider_type == provider_type]
        if protocol is not None:
            results = [p for p in results if p.protocol == protocol]
        return results

    async def register_model(self, model: ModelDescriptor) -> None:
        self._models[model.id] = model

    async def get_model(self, model_id: str) -> ModelDescriptor | None:
        return self._models.get(model_id)

    async def list_models(
        self,
        *,
        provider_id: str | None = None,
        modality: str | None = None,
    ) -> list[ModelDescriptor]:
        results = list(self._models.values())
        if provider_id is not None:
            results = [m for m in results if m.provider_id == provider_id]
        if modality is not None:
            results = [m for m in results if modality in m.modalities]
        return results

    async def discover(self) -> DiscoveryResult:
        return DiscoveryResult(
            providers_found=len(self._providers),
            models_found=len(self._models),
            sources_queried=["memory"],
            discovered_at=_now(),
        )

    async def remove_provider(self, provider_id: str) -> bool:
        if provider_id not in self._providers:
            return False
        del self._providers[provider_id]
        stale = [mid for mid, m in self._models.items() if m.provider_id == provider_id]
        for mid in stale:
            del self._models[mid]
        return True


# ══════════════════════════════════════════════════════════════════════════
# ProviderCapabilityRegistry (#67)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryProviderCapabilityRegistry:
    """Dict-backed capability store keyed by (provider_id, model_id)."""

    def __init__(self) -> None:
        self._capabilities: dict[tuple[str, str], ProviderCapabilities] = {}

    async def set_capabilities(self, capabilities: ProviderCapabilities) -> None:
        key = (capabilities.provider_id, capabilities.model_id)
        self._capabilities[key] = capabilities

    async def get_capabilities(
        self, provider_id: str, model_id: str
    ) -> ProviderCapabilities | None:
        return self._capabilities.get((provider_id, model_id))

    async def list_capabilities(
        self,
        *,
        provider_id: str | None = None,
    ) -> list[ProviderCapabilities]:
        if provider_id is None:
            return list(self._capabilities.values())
        return [c for c in self._capabilities.values() if c.provider_id == provider_id]

    async def record_observed_limits(
        self,
        provider_id: str,
        model_id: str,
        *,
        requests_per_minute: int | None = None,
        tokens_per_minute: int | None = None,
    ) -> None:
        key = (provider_id, model_id)
        cap = self._capabilities.get(key)
        if cap is None:
            cap = ProviderCapabilities(provider_id=provider_id, model_id=model_id)
            self._capabilities[key] = cap

        cap.rate_limits = RateLimits(
            requests_per_minute=(
                requests_per_minute
                if requests_per_minute is not None
                else cap.rate_limits.requests_per_minute
            ),
            requests_per_day=cap.rate_limits.requests_per_day,
            tokens_per_minute=(
                tokens_per_minute
                if tokens_per_minute is not None
                else cap.rate_limits.tokens_per_minute
            ),
            tokens_per_day=cap.rate_limits.tokens_per_day,
            concurrent_requests=cap.rate_limits.concurrent_requests,
            is_observed=True,
        )
        cap.observed_at = _now()

    async def check_quota(self, provider_id: str, model_id: str) -> bool:
        cap = self._capabilities.get((provider_id, model_id))
        if cap is None:
            return True
        quota = cap.quota
        if quota.daily_remaining is not None and quota.daily_remaining <= 0:
            return False
        if quota.monthly_remaining is not None and quota.monthly_remaining <= 0:
            return False
        return True


# ══════════════════════════════════════════════════════════════════════════
# PolicyRegistry (#68)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryPolicyRegistry:
    """Dict-backed policy store with region and commercial eligibility checks."""

    def __init__(self) -> None:
        self._policies: dict[str, ProviderPolicy] = {}

    async def set_policy(self, policy: ProviderPolicy) -> None:
        self._policies[policy.provider_id] = policy

    async def get_policy(self, provider_id: str) -> ProviderPolicy | None:
        return self._policies.get(provider_id)

    async def list_policies(self) -> list[ProviderPolicy]:
        return list(self._policies.values())

    async def check_eligible(
        self,
        provider_id: str,
        *,
        region: str | None = None,
        commercial: bool = False,
    ) -> bool:
        policy = self._policies.get(provider_id)
        if policy is None:
            return True

        if commercial and not policy.eligibility.commercial_use_allowed:
            return False

        if region is not None:
            elig = policy.eligibility
            if elig.blocked_regions and region in elig.blocked_regions:
                return False
            if elig.allowed_regions and region not in elig.allowed_regions:
                return False

        return True

    async def remove_policy(self, provider_id: str) -> bool:
        if provider_id in self._policies:
            del self._policies[provider_id]
            return True
        return False


# ══════════════════════════════════════════════════════════════════════════
# CatalogSynchronizer (#69)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryCatalogSynchronizer:
    """Dict-backed catalog with version tracking and staleness detection."""

    def __init__(self) -> None:
        self._sources: dict[str, CatalogSource] = {}
        self._entries: dict[str, CatalogEntry] = {}
        self._history: dict[str, list[CatalogEntry]] = {}

    async def add_source(self, source: CatalogSource) -> None:
        self._sources[source.id] = source

    async def list_sources(self) -> list[CatalogSource]:
        return list(self._sources.values())

    async def sync(self, *, source_id: str | None = None) -> SyncResult:
        now = _now()

        if source_id is not None:
            source = self._sources.get(source_id)
            if source is not None:
                source.last_synced_at = now
            return SyncResult(source_id=source_id or "", synced_at=now)

        for source in self._sources.values():
            if source.enabled:
                source.last_synced_at = now

        return SyncResult(source_id="*", synced_at=now)

    async def get_entry(self, entry_id: str) -> CatalogEntry | None:
        return self._entries.get(entry_id)

    async def staleness_report(self) -> StalenessReport:
        stale: list[CatalogEntry] = []
        retired: list[CatalogEntry] = []
        renamed: list[CatalogEntry] = []
        healthy = 0

        for entry in self._entries.values():
            if entry.status == "stale":
                stale.append(entry)
            elif entry.status == "retired":
                retired.append(entry)
            elif entry.status == "renamed":
                renamed.append(entry)
            else:
                healthy += 1

        total = len(self._entries)
        unhealthy = len(stale) + len(retired) + len(renamed)

        return StalenessReport(
            stale_entries=stale,
            retired_entries=retired,
            renamed_entries=renamed,
            total_entries=total,
            healthy_entries=healthy,
            staleness_ratio=unhealthy / total if total > 0 else 0.0,
            checked_at=_now(),
        )

    async def retire_entry(self, entry_id: str) -> bool:
        entry = self._entries.get(entry_id)
        if entry is None:
            return False

        self._history.setdefault(entry_id, []).append(deepcopy(entry))
        entry.status = "retired"
        entry.version += 1
        return True

    async def history(self, entry_id: str, *, limit: int = 10) -> list[CatalogEntry]:
        return self._history.get(entry_id, [])[-limit:]
