"""Phase 7 data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  Phase 7 protocols reference these types for their method
signatures.

Phase 7 covers provider registry and catalog management:

- **ProviderDescriptor / ModelDescriptor** -- provider and model discovery (#66)
- **RateLimits / QuotaStatus / ProviderCapabilities** -- capability
  and quota metadata (#67)
- **DataPolicy / EligibilityRequirements / ProviderPolicy** -- policy
  and privacy metadata (#68)
- **CatalogSource / CatalogEntry / SyncResult / StalenessReport** --
  catalog synchronization (#69)
"""

from __future__ import annotations

from dataclasses import dataclass, field

# -- Discovery models (#66) --------------------------------------------------


@dataclass
class ProviderDescriptor:
    """Metadata describing a registered AI model provider."""

    id: str
    name: str
    provider_type: str  # e.g. "api", "local", "proxy"
    protocol: str  # e.g. "openai", "anthropic", "google"
    base_url: str = ""
    auth_required: bool = True
    capabilities: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    discovered_at: str = ""


@dataclass
class ModelDescriptor:
    """Metadata describing a discoverable model within a provider."""

    id: str
    name: str
    provider_id: str
    context_length: int = 0
    max_output_tokens: int = 0
    modalities: list[str] = field(default_factory=list)
    supports_tool_calling: bool = False
    supports_structured_output: bool = False
    supports_embeddings: bool = False
    supports_reasoning: bool = False
    supports_streaming: bool = False
    metadata: dict = field(default_factory=dict)
    discovered_at: str = ""


@dataclass
class DiscoveryResult:
    """Outcome of a provider or model discovery operation."""

    providers_found: int = 0
    models_found: int = 0
    sources_queried: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    discovered_at: str = ""


# -- Capability and quota models (#67) ---------------------------------------


@dataclass
class RateLimits:
    """Request and token rate limits for a provider or model."""

    requests_per_minute: int | None = None
    requests_per_day: int | None = None
    tokens_per_minute: int | None = None
    tokens_per_day: int | None = None
    concurrent_requests: int | None = None
    is_observed: bool = False


@dataclass
class QuotaStatus:
    """Current quota consumption and remaining capacity."""

    daily_limit: int | None = None
    daily_used: int = 0
    daily_remaining: int | None = None
    monthly_limit: int | None = None
    monthly_used: int = 0
    monthly_remaining: int | None = None
    reset_at: str = ""


@dataclass
class PricingInfo:
    """Pricing metadata for a model or provider."""

    input_cost_per_1k_tokens: float = 0.0
    output_cost_per_1k_tokens: float = 0.0
    is_free_tier: bool = False
    free_tier_limits: dict = field(default_factory=dict)
    currency: str = "USD"


@dataclass
class ProviderCapabilities:
    """Aggregated operational constraints for routing decisions."""

    provider_id: str
    model_id: str
    rate_limits: RateLimits = field(default_factory=RateLimits)
    quota: QuotaStatus = field(default_factory=QuotaStatus)
    pricing: PricingInfo = field(default_factory=PricingInfo)
    context_limit: int = 0
    output_limit: int = 0
    regions: list[str] = field(default_factory=list)
    declared_at: str = ""
    observed_at: str = ""


# -- Policy and privacy models (#68) -----------------------------------------


@dataclass
class DataPolicy:
    """Data retention and training-use policy for a provider."""

    retains_prompts: bool | None = None
    retention_days: int | None = None
    uses_for_training: bool | None = None
    allows_opt_out: bool | None = None
    privacy_url: str = ""


@dataclass
class EligibilityRequirements:
    """Account and eligibility requirements for provider access."""

    requires_account: bool = False
    requires_credit_card: bool = False
    requires_api_key: bool = True
    allowed_regions: list[str] = field(default_factory=list)
    blocked_regions: list[str] = field(default_factory=list)
    commercial_use_allowed: bool = True
    restrictions: list[str] = field(default_factory=list)


@dataclass
class ProviderPolicy:
    """Aggregated policy metadata for a provider."""

    provider_id: str
    data_policy: DataPolicy = field(default_factory=DataPolicy)
    eligibility: EligibilityRequirements = field(
        default_factory=EligibilityRequirements
    )
    compliance_standards: list[str] = field(default_factory=list)
    data_residency: list[str] = field(default_factory=list)
    effective_date: str = ""
    provenance: str = ""
    confidence: float = 1.0


# -- Catalog synchronization models (#69) ------------------------------------


@dataclass
class CatalogSource:
    """A discovery source for model/provider catalog data."""

    id: str
    name: str
    source_type: str  # e.g. "api", "static", "community"
    url: str = ""
    priority: int = 0
    last_synced_at: str = ""
    enabled: bool = True


@dataclass
class CatalogEntry:
    """A versioned catalog entry for a model or provider."""

    entry_id: str
    entry_type: str  # "model" or "provider"
    name: str
    version: int = 1
    status: str = "active"  # "active", "stale", "retired", "renamed"
    source_id: str = ""
    last_verified_at: str = ""
    created_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class SyncResult:
    """Outcome of a catalog synchronization run."""

    source_id: str
    entries_added: int = 0
    entries_updated: int = 0
    entries_retired: int = 0
    conflicts: int = 0
    errors: list[str] = field(default_factory=list)
    synced_at: str = ""


@dataclass
class StalenessReport:
    """Report on stale, retired, and renamed catalog entries."""

    stale_entries: list[CatalogEntry] = field(default_factory=list)
    retired_entries: list[CatalogEntry] = field(default_factory=list)
    renamed_entries: list[CatalogEntry] = field(default_factory=list)
    total_entries: int = 0
    healthy_entries: int = 0
    staleness_ratio: float = 0.0
    checked_at: str = ""
