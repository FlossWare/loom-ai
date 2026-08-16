"""Conformance tests for Phase 7 protocol contracts.

Verifies that concrete stub implementations satisfy each protocol via
``isinstance`` checks (runtime_checkable) and that the protocols'
async methods behave correctly when backed by minimal in-memory stubs.
"""

from __future__ import annotations

import pytest

from loom_ai.contracts_phase7 import (
    CapabilityRegistry,
    CatalogSynchronizer,
    PolicyRegistry,
    ProviderRegistry,
)
from loom_ai.models_phase7 import (
    CatalogEntry,
    CatalogSource,
    DataPolicy,
    DiscoveryResult,
    EligibilityRequirements,
    ModelDescriptor,
    PricingInfo,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderPolicy,
    QuotaStatus,
    RateLimits,
    StalenessReport,
    SyncResult,
)

# ── helpers ──────────────────────────────────────────────────────────────


def _provider(
    pid: str = "openrouter",
    **kwargs,
) -> ProviderDescriptor:
    return ProviderDescriptor(
        id=pid,
        name=kwargs.get("name", f"Provider {pid}"),
        provider_type=kwargs.get("provider_type", "api"),
        protocol=kwargs.get("protocol", "openai"),
        **{
            k: v
            for k, v in kwargs.items()
            if k not in ("name", "provider_type", "protocol")
        },
    )


def _model(
    mid: str = "gpt-4o",
    provider_id: str = "openrouter",
    **kwargs,
) -> ModelDescriptor:
    return ModelDescriptor(
        id=mid,
        name=kwargs.get("name", mid),
        provider_id=provider_id,
        **{k: v for k, v in kwargs.items() if k != "name"},
    )


def _capabilities(
    provider_id: str = "openrouter",
    model_id: str = "gpt-4o",
) -> ProviderCapabilities:
    return ProviderCapabilities(provider_id=provider_id, model_id=model_id)


def _policy(provider_id: str = "openrouter") -> ProviderPolicy:
    return ProviderPolicy(provider_id=provider_id)


def _source(sid: str = "awesome-llm") -> CatalogSource:
    return CatalogSource(id=sid, name=f"Source {sid}", source_type="static")


def _entry(eid: str = "e1", name: str = "gpt-4o") -> CatalogEntry:
    return CatalogEntry(entry_id=eid, entry_type="model", name=name)


# ── Stub: ProviderRegistry ──────────────────────────────────────────────


class StubProviderRegistry:
    """Minimal in-memory ProviderRegistry for conformance testing."""

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
        result = list(self._providers.values())
        if provider_type is not None:
            result = [p for p in result if p.provider_type == provider_type]
        if protocol is not None:
            result = [p for p in result if p.protocol == protocol]
        return result

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
        result = list(self._models.values())
        if provider_id is not None:
            result = [m for m in result if m.provider_id == provider_id]
        if modality is not None:
            result = [m for m in result if modality in m.modalities]
        return result

    async def discover(self) -> DiscoveryResult:
        return DiscoveryResult(
            providers_found=len(self._providers),
            models_found=len(self._models),
        )

    async def remove_provider(self, provider_id: str) -> bool:
        if provider_id not in self._providers:
            return False
        del self._providers[provider_id]
        self._models = {
            k: v for k, v in self._models.items() if v.provider_id != provider_id
        }
        return True


# ── Stub: CapabilityRegistry ────────────────────────────────────────────


class StubCapabilityRegistry:
    """Minimal in-memory CapabilityRegistry for conformance testing."""

    def __init__(self) -> None:
        self._caps: dict[tuple[str, str], ProviderCapabilities] = {}

    async def set_capabilities(self, capabilities: ProviderCapabilities) -> None:
        key = (capabilities.provider_id, capabilities.model_id)
        self._caps[key] = capabilities

    async def get_capabilities(
        self, provider_id: str, model_id: str
    ) -> ProviderCapabilities | None:
        return self._caps.get((provider_id, model_id))

    async def list_capabilities(
        self,
        *,
        provider_id: str | None = None,
    ) -> list[ProviderCapabilities]:
        result = list(self._caps.values())
        if provider_id is not None:
            result = [c for c in result if c.provider_id == provider_id]
        return result

    async def record_observed_limits(
        self,
        provider_id: str,
        model_id: str,
        *,
        requests_per_minute: int | None = None,
        tokens_per_minute: int | None = None,
    ) -> None:
        key = (provider_id, model_id)
        caps = self._caps.get(key)
        if caps is not None:
            caps.rate_limits = RateLimits(
                requests_per_minute=requests_per_minute,
                tokens_per_minute=tokens_per_minute,
                is_observed=True,
            )

    async def check_quota(self, provider_id: str, model_id: str) -> bool:
        caps = self._caps.get((provider_id, model_id))
        if caps is None:
            return True
        if caps.quota.daily_remaining is not None:
            return caps.quota.daily_remaining > 0
        return True


# ── Stub: PolicyRegistry ────────────────────────────────────────────────


class StubPolicyRegistry:
    """Minimal in-memory PolicyRegistry for conformance testing."""

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
            if (
                policy.eligibility.blocked_regions
                and region in policy.eligibility.blocked_regions
            ):
                return False
            if (
                policy.eligibility.allowed_regions
                and region not in policy.eligibility.allowed_regions
            ):
                return False
        return True

    async def remove_policy(self, provider_id: str) -> bool:
        if provider_id not in self._policies:
            return False
        del self._policies[provider_id]
        return True


# ── Stub: CatalogSynchronizer ──────────────────────────────────────────


class StubCatalogSynchronizer:
    """Minimal in-memory CatalogSynchronizer for conformance testing."""

    def __init__(self) -> None:
        self._sources: dict[str, CatalogSource] = {}
        self._entries: dict[str, list[CatalogEntry]] = {}

    async def add_source(self, source: CatalogSource) -> None:
        self._sources[source.id] = source

    async def list_sources(self) -> list[CatalogSource]:
        return list(self._sources.values())

    async def sync(self, *, source_id: str | None = None) -> SyncResult:
        sid = source_id or "all"
        return SyncResult(source_id=sid)

    async def get_entry(self, entry_id: str) -> CatalogEntry | None:
        versions = self._entries.get(entry_id)
        if versions:
            return versions[-1]
        return None

    async def staleness_report(self) -> StalenessReport:
        all_entries = [v[-1] for v in self._entries.values() if v]
        stale = [e for e in all_entries if e.status == "stale"]
        retired = [e for e in all_entries if e.status == "retired"]
        renamed = [e for e in all_entries if e.status == "renamed"]
        total = len(all_entries)
        healthy = total - len(stale) - len(retired) - len(renamed)
        ratio = (total - healthy) / total if total > 0 else 0.0
        return StalenessReport(
            stale_entries=stale,
            retired_entries=retired,
            renamed_entries=renamed,
            total_entries=total,
            healthy_entries=healthy,
            staleness_ratio=ratio,
        )

    async def retire_entry(self, entry_id: str) -> bool:
        versions = self._entries.get(entry_id)
        if not versions:
            return False
        versions[-1].status = "retired"
        return True

    async def history(self, entry_id: str, *, limit: int = 10) -> list[CatalogEntry]:
        versions = self._entries.get(entry_id, [])
        return versions[:limit]

    # Helper for tests -- not part of the protocol
    def _add_entry(self, entry: CatalogEntry) -> None:
        self._entries.setdefault(entry.entry_id, []).append(entry)


# ═══════════════════════════════════════════════════════════════════════
# Protocol conformance tests
# ═══════════════════════════════════════════════════════════════════════


class TestProviderRegistryConformance:
    """ProviderRegistry protocol conformance and basic behaviour."""

    def test_isinstance_check(self):
        assert isinstance(StubProviderRegistry(), ProviderRegistry)

    async def test_register_and_get_provider(self):
        reg = StubProviderRegistry()
        p = _provider("or1")
        await reg.register_provider(p)
        assert (await reg.get_provider("or1")) is p

    async def test_get_provider_not_found(self):
        reg = StubProviderRegistry()
        assert (await reg.get_provider("missing")) is None

    async def test_list_providers_unfiltered(self):
        reg = StubProviderRegistry()
        await reg.register_provider(_provider("a", provider_type="api"))
        await reg.register_provider(_provider("b", provider_type="proxy"))
        result = await reg.list_providers()
        assert len(result) == 2

    async def test_list_providers_filtered_by_type(self):
        reg = StubProviderRegistry()
        await reg.register_provider(_provider("a", provider_type="api"))
        await reg.register_provider(_provider("b", provider_type="proxy"))
        result = await reg.list_providers(provider_type="api")
        assert len(result) == 1
        assert result[0].id == "a"

    async def test_list_providers_filtered_by_protocol(self):
        reg = StubProviderRegistry()
        await reg.register_provider(_provider("a", protocol="openai"))
        await reg.register_provider(_provider("b", protocol="anthropic"))
        result = await reg.list_providers(protocol="anthropic")
        assert len(result) == 1
        assert result[0].id == "b"

    async def test_register_and_get_model(self):
        reg = StubProviderRegistry()
        m = _model("gpt-4o")
        await reg.register_model(m)
        assert (await reg.get_model("gpt-4o")) is m

    async def test_get_model_not_found(self):
        reg = StubProviderRegistry()
        assert (await reg.get_model("missing")) is None

    async def test_list_models_by_provider(self):
        reg = StubProviderRegistry()
        await reg.register_model(_model("m1", provider_id="or1"))
        await reg.register_model(_model("m2", provider_id="or2"))
        result = await reg.list_models(provider_id="or1")
        assert len(result) == 1
        assert result[0].id == "m1"

    async def test_list_models_by_modality(self):
        reg = StubProviderRegistry()
        await reg.register_model(_model("m1", modalities=["text", "image"]))
        await reg.register_model(_model("m2", modalities=["text"]))
        result = await reg.list_models(modality="image")
        assert len(result) == 1
        assert result[0].id == "m1"

    async def test_discover(self):
        reg = StubProviderRegistry()
        await reg.register_provider(_provider("p1"))
        await reg.register_model(_model("m1"))
        result = await reg.discover()
        assert isinstance(result, DiscoveryResult)
        assert result.providers_found == 1
        assert result.models_found == 1

    async def test_remove_provider(self):
        reg = StubProviderRegistry()
        await reg.register_provider(_provider("p1"))
        await reg.register_model(_model("m1", provider_id="p1"))
        assert await reg.remove_provider("p1") is True
        assert (await reg.get_provider("p1")) is None
        assert (await reg.list_models(provider_id="p1")) == []

    async def test_remove_provider_not_found(self):
        reg = StubProviderRegistry()
        assert await reg.remove_provider("ghost") is False

    async def test_register_provider_overwrites(self):
        reg = StubProviderRegistry()
        await reg.register_provider(_provider("p1", name="Original"))
        await reg.register_provider(_provider("p1", name="Updated"))
        p = await reg.get_provider("p1")
        assert p is not None
        assert p.name == "Updated"


# ═══════════════════════════════════════════════════════════════════════


class TestCapabilityRegistryConformance:
    """CapabilityRegistry protocol conformance and basic behaviour."""

    def test_isinstance_check(self):
        assert isinstance(StubCapabilityRegistry(), CapabilityRegistry)

    async def test_set_and_get_capabilities(self):
        reg = StubCapabilityRegistry()
        caps = _capabilities("or1", "gpt-4o")
        await reg.set_capabilities(caps)
        assert (await reg.get_capabilities("or1", "gpt-4o")) is caps

    async def test_get_capabilities_not_found(self):
        reg = StubCapabilityRegistry()
        assert (await reg.get_capabilities("x", "y")) is None

    async def test_list_capabilities_unfiltered(self):
        reg = StubCapabilityRegistry()
        await reg.set_capabilities(_capabilities("or1", "m1"))
        await reg.set_capabilities(_capabilities("or2", "m2"))
        result = await reg.list_capabilities()
        assert len(result) == 2

    async def test_list_capabilities_filtered(self):
        reg = StubCapabilityRegistry()
        await reg.set_capabilities(_capabilities("or1", "m1"))
        await reg.set_capabilities(_capabilities("or2", "m2"))
        result = await reg.list_capabilities(provider_id="or1")
        assert len(result) == 1
        assert result[0].model_id == "m1"

    async def test_record_observed_limits(self):
        reg = StubCapabilityRegistry()
        await reg.set_capabilities(_capabilities("or1", "m1"))
        await reg.record_observed_limits(
            "or1", "m1", requests_per_minute=60, tokens_per_minute=10000
        )
        caps = await reg.get_capabilities("or1", "m1")
        assert caps is not None
        assert caps.rate_limits.is_observed is True
        assert caps.rate_limits.requests_per_minute == 60
        assert caps.rate_limits.tokens_per_minute == 10000

    async def test_check_quota_with_remaining(self):
        reg = StubCapabilityRegistry()
        caps = _capabilities("or1", "m1")
        caps.quota = QuotaStatus(daily_limit=100, daily_used=50, daily_remaining=50)
        await reg.set_capabilities(caps)
        assert await reg.check_quota("or1", "m1") is True

    async def test_check_quota_exhausted(self):
        reg = StubCapabilityRegistry()
        caps = _capabilities("or1", "m1")
        caps.quota = QuotaStatus(daily_limit=100, daily_used=100, daily_remaining=0)
        await reg.set_capabilities(caps)
        assert await reg.check_quota("or1", "m1") is False

    async def test_check_quota_unknown_provider(self):
        reg = StubCapabilityRegistry()
        assert await reg.check_quota("unknown", "unknown") is True

    async def test_set_capabilities_overwrites(self):
        reg = StubCapabilityRegistry()
        caps1 = _capabilities("or1", "m1")
        caps1.context_limit = 4096
        await reg.set_capabilities(caps1)
        caps2 = _capabilities("or1", "m1")
        caps2.context_limit = 128000
        await reg.set_capabilities(caps2)
        result = await reg.get_capabilities("or1", "m1")
        assert result is not None
        assert result.context_limit == 128000


# ═══════════════════════════════════════════════════════════════════════


class TestPolicyRegistryConformance:
    """PolicyRegistry protocol conformance and basic behaviour."""

    def test_isinstance_check(self):
        assert isinstance(StubPolicyRegistry(), PolicyRegistry)

    async def test_set_and_get_policy(self):
        reg = StubPolicyRegistry()
        pol = _policy("or1")
        await reg.set_policy(pol)
        assert (await reg.get_policy("or1")) is pol

    async def test_get_policy_not_found(self):
        reg = StubPolicyRegistry()
        assert (await reg.get_policy("missing")) is None

    async def test_list_policies(self):
        reg = StubPolicyRegistry()
        await reg.set_policy(_policy("a"))
        await reg.set_policy(_policy("b"))
        result = await reg.list_policies()
        assert len(result) == 2

    async def test_check_eligible_no_policy(self):
        reg = StubPolicyRegistry()
        assert await reg.check_eligible("unknown") is True

    async def test_check_eligible_commercial_allowed(self):
        reg = StubPolicyRegistry()
        pol = _policy("or1")
        pol.eligibility = EligibilityRequirements(commercial_use_allowed=True)
        await reg.set_policy(pol)
        assert await reg.check_eligible("or1", commercial=True) is True

    async def test_check_eligible_commercial_blocked(self):
        reg = StubPolicyRegistry()
        pol = _policy("or1")
        pol.eligibility = EligibilityRequirements(commercial_use_allowed=False)
        await reg.set_policy(pol)
        assert await reg.check_eligible("or1", commercial=True) is False

    async def test_check_eligible_region_allowed(self):
        reg = StubPolicyRegistry()
        pol = _policy("or1")
        pol.eligibility = EligibilityRequirements(allowed_regions=["US", "EU"])
        await reg.set_policy(pol)
        assert await reg.check_eligible("or1", region="US") is True

    async def test_check_eligible_region_not_in_allowlist(self):
        reg = StubPolicyRegistry()
        pol = _policy("or1")
        pol.eligibility = EligibilityRequirements(allowed_regions=["US", "EU"])
        await reg.set_policy(pol)
        assert await reg.check_eligible("or1", region="CN") is False

    async def test_check_eligible_region_in_blocklist(self):
        reg = StubPolicyRegistry()
        pol = _policy("or1")
        pol.eligibility = EligibilityRequirements(blocked_regions=["CN", "RU"])
        await reg.set_policy(pol)
        assert await reg.check_eligible("or1", region="CN") is False

    async def test_check_eligible_region_not_blocked(self):
        reg = StubPolicyRegistry()
        pol = _policy("or1")
        pol.eligibility = EligibilityRequirements(blocked_regions=["CN"])
        await reg.set_policy(pol)
        assert await reg.check_eligible("or1", region="US") is True

    async def test_remove_policy(self):
        reg = StubPolicyRegistry()
        await reg.set_policy(_policy("or1"))
        assert await reg.remove_policy("or1") is True
        assert (await reg.get_policy("or1")) is None

    async def test_remove_policy_not_found(self):
        reg = StubPolicyRegistry()
        assert await reg.remove_policy("ghost") is False

    async def test_set_policy_with_data_policy(self):
        reg = StubPolicyRegistry()
        pol = _policy("or1")
        pol.data_policy = DataPolicy(
            retains_prompts=True,
            retention_days=30,
            uses_for_training=False,
        )
        await reg.set_policy(pol)
        result = await reg.get_policy("or1")
        assert result is not None
        assert result.data_policy.retains_prompts is True
        assert result.data_policy.retention_days == 30
        assert result.data_policy.uses_for_training is False


# ═══════════════════════════════════════════════════════════════════════


class TestCatalogSynchronizerConformance:
    """CatalogSynchronizer protocol conformance and basic behaviour."""

    def test_isinstance_check(self):
        assert isinstance(StubCatalogSynchronizer(), CatalogSynchronizer)

    async def test_add_and_list_sources(self):
        sync = StubCatalogSynchronizer()
        src = _source("s1")
        await sync.add_source(src)
        sources = await sync.list_sources()
        assert len(sources) == 1
        assert sources[0].id == "s1"

    async def test_sync_returns_result(self):
        sync = StubCatalogSynchronizer()
        result = await sync.sync()
        assert isinstance(result, SyncResult)

    async def test_sync_with_source_id(self):
        sync = StubCatalogSynchronizer()
        await sync.add_source(_source("s1"))
        result = await sync.sync(source_id="s1")
        assert result.source_id == "s1"

    async def test_get_entry(self):
        sync = StubCatalogSynchronizer()
        entry = _entry("e1", "gpt-4o")
        sync._add_entry(entry)
        assert (await sync.get_entry("e1")) is entry

    async def test_get_entry_not_found(self):
        sync = StubCatalogSynchronizer()
        assert (await sync.get_entry("missing")) is None

    async def test_retire_entry(self):
        sync = StubCatalogSynchronizer()
        sync._add_entry(_entry("e1"))
        assert await sync.retire_entry("e1") is True
        entry = await sync.get_entry("e1")
        assert entry is not None
        assert entry.status == "retired"

    async def test_retire_entry_not_found(self):
        sync = StubCatalogSynchronizer()
        assert await sync.retire_entry("ghost") is False

    async def test_staleness_report_healthy(self):
        sync = StubCatalogSynchronizer()
        sync._add_entry(_entry("e1", "gpt-4o"))
        sync._add_entry(_entry("e2", "claude-4"))
        report = await sync.staleness_report()
        assert isinstance(report, StalenessReport)
        assert report.total_entries == 2
        assert report.healthy_entries == 2
        assert report.staleness_ratio == pytest.approx(0.0)

    async def test_staleness_report_with_stale(self):
        sync = StubCatalogSynchronizer()
        e1 = _entry("e1", "gpt-4o")
        e1.status = "stale"
        sync._add_entry(e1)
        sync._add_entry(_entry("e2", "claude-4"))
        report = await sync.staleness_report()
        assert report.total_entries == 2
        assert report.healthy_entries == 1
        assert len(report.stale_entries) == 1
        assert report.staleness_ratio == pytest.approx(0.5)

    async def test_staleness_report_with_retired(self):
        sync = StubCatalogSynchronizer()
        e1 = _entry("e1", "old-model")
        e1.status = "retired"
        sync._add_entry(e1)
        report = await sync.staleness_report()
        assert len(report.retired_entries) == 1
        assert report.healthy_entries == 0

    async def test_staleness_report_empty(self):
        sync = StubCatalogSynchronizer()
        report = await sync.staleness_report()
        assert report.total_entries == 0
        assert report.staleness_ratio == pytest.approx(0.0)

    async def test_history_returns_versions(self):
        sync = StubCatalogSynchronizer()
        v1 = _entry("e1", "gpt-4o")
        v1.version = 1
        v2 = CatalogEntry(entry_id="e1", entry_type="model", name="gpt-4o", version=2)
        sync._add_entry(v1)
        sync._add_entry(v2)
        versions = await sync.history("e1")
        assert len(versions) == 2
        assert versions[0].version == 1
        assert versions[1].version == 2

    async def test_history_respects_limit(self):
        sync = StubCatalogSynchronizer()
        for i in range(5):
            sync._add_entry(
                CatalogEntry(
                    entry_id="e1",
                    entry_type="model",
                    name="gpt-4o",
                    version=i + 1,
                )
            )
        versions = await sync.history("e1", limit=3)
        assert len(versions) == 3

    async def test_history_empty(self):
        sync = StubCatalogSynchronizer()
        assert (await sync.history("missing")) == []


# ═══════════════════════════════════════════════════════════════════════
# Data model construction tests
# ═══════════════════════════════════════════════════════════════════════


class TestModelConstruction:
    """Verify all Phase 7 dataclasses construct with sensible defaults."""

    def test_provider_descriptor_defaults(self):
        p = ProviderDescriptor(
            id="p1", name="Test", provider_type="api", protocol="openai"
        )
        assert p.base_url == ""
        assert p.auth_required is True
        assert p.capabilities == []
        assert p.models == []

    def test_model_descriptor_defaults(self):
        m = ModelDescriptor(id="m1", name="model", provider_id="p1")
        assert m.context_length == 0
        assert m.supports_tool_calling is False
        assert m.supports_structured_output is False
        assert m.modalities == []

    def test_model_descriptor_with_capabilities(self):
        m = ModelDescriptor(
            id="m1",
            name="gpt-4o",
            provider_id="openrouter",
            context_length=128000,
            modalities=["text", "image"],
            supports_tool_calling=True,
            supports_structured_output=True,
            supports_streaming=True,
        )
        assert m.context_length == 128000
        assert "image" in m.modalities
        assert m.supports_tool_calling is True

    def test_rate_limits_defaults(self):
        rl = RateLimits()
        assert rl.requests_per_minute is None
        assert rl.is_observed is False

    def test_quota_status_defaults(self):
        qs = QuotaStatus()
        assert qs.daily_limit is None
        assert qs.daily_used == 0

    def test_pricing_info_free_tier(self):
        pi = PricingInfo(is_free_tier=True, free_tier_limits={"rpm": 10})
        assert pi.is_free_tier is True
        assert pi.free_tier_limits == {"rpm": 10}

    def test_data_policy_defaults(self):
        dp = DataPolicy()
        assert dp.retains_prompts is None
        assert dp.uses_for_training is None

    def test_eligibility_requirements_defaults(self):
        er = EligibilityRequirements()
        assert er.requires_account is False
        assert er.commercial_use_allowed is True
        assert er.allowed_regions == []

    def test_provider_policy_defaults(self):
        pp = ProviderPolicy(provider_id="p1")
        assert pp.confidence == 1.0
        assert pp.compliance_standards == []

    def test_catalog_source_defaults(self):
        cs = CatalogSource(id="s1", name="Source", source_type="api")
        assert cs.enabled is True
        assert cs.priority == 0

    def test_catalog_entry_defaults(self):
        ce = CatalogEntry(entry_id="e1", entry_type="model", name="test")
        assert ce.version == 1
        assert ce.status == "active"

    def test_sync_result_defaults(self):
        sr = SyncResult(source_id="s1")
        assert sr.entries_added == 0
        assert sr.errors == []

    def test_staleness_report_defaults(self):
        sr = StalenessReport()
        assert sr.total_entries == 0
        assert sr.staleness_ratio == 0.0

    def test_discovery_result_defaults(self):
        dr = DiscoveryResult()
        assert dr.providers_found == 0
        assert dr.errors == []
