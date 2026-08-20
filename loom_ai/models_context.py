"""Phase 9 data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  Phase 9 protocols reference these types for their method
signatures.

Phase 9 covers ten contract areas:

- **CapabilityProfile / ModelBenchmark** -- model evaluation (#79)
- **CanonicalSource / DerivedIndex / ProvenanceRecord** -- source indexing (#80)
- **CompressedProjection / CompressionQuality** -- context compression (#81)
- **CacheCapability / CacheEvent** -- prompt-cache awareness (#82)
- **AgentInvocation / AgentResult** -- pluggable agent runtime (#83)
- **ContextTransformation / ContextBudget** -- pluggable context engine (#84)
- **CapabilityDescriptor / CapabilityResult** -- pluggable capability/tool (#85)
- **EvaluationCandidate / EvaluationScore / EvaluationEvidence** -- evaluation (#86)
- **HealthDetail / HealthCheckResult** -- authenticated health checks (#87)
- **ValidationError / ValidationReport** -- REST API validation (#88)
"""

from __future__ import annotations

from dataclasses import dataclass, field

# -- Model evaluation (#79) --------------------------------------------------


@dataclass
class CapabilityProfile:
    """Capabilities and benchmarks for a candidate model."""

    model: str
    provider: str
    context_length: int = 0
    supports_tool_calling: bool = False
    supports_structured_output: bool = False
    supports_streaming: bool = False
    supports_agent_loops: bool = False
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ModelBenchmark:
    """Result of benchmarking a model on a specific task type."""

    model: str
    task_type: str
    score: float
    latency_ms: float
    tokens_used: int
    quality_notes: str = ""
    metadata: dict = field(default_factory=dict)


# -- Canonical source indexing (#80) -----------------------------------------


@dataclass
class CanonicalSource:
    """A human-readable canonical knowledge source."""

    id: str
    uri: str
    content_hash: str
    format: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class DerivedIndex:
    """A rebuildable index derived from canonical sources."""

    id: str
    index_type: str
    source_ids: list[str] = field(default_factory=list)
    status: str = "stale"
    built_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ProvenanceRecord:
    """Tracks the lineage from a derived artifact back to its canonical source."""

    derived_id: str
    source_id: str
    source_uri: str
    transformation: str = ""
    created_at: str = ""


# -- Context compression (#81) -----------------------------------------------


@dataclass
class CompressedProjection:
    """A compressed representation of original content."""

    id: str
    original_id: str
    compressed_content: str
    content_type: str = ""
    compression_ratio: float = 0.0
    reversible: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass
class CompressionQuality:
    """Quality metrics for a compression operation."""

    semantic_preservation: float = 0.0
    token_reduction: float = 0.0
    information_loss: float = 0.0
    content_type: str = ""
    metadata: dict = field(default_factory=dict)


# -- Prompt-cache awareness (#82) --------------------------------------------


@dataclass
class CacheCapability:
    """Provider-specific prompt-cache capability descriptor."""

    provider: str
    supported: bool = False
    max_ttl_seconds: int = 0
    prefix_based: bool = False
    max_cached_tokens: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class CacheEvent:
    """A single cache interaction event for observability."""

    provider: str
    event_type: str  # "hit", "miss", "eviction", "bypass"
    tokens_affected: int = 0
    latency_saved_ms: float = 0.0
    cost_saved: float = 0.0
    cache_key: str = ""
    metadata: dict = field(default_factory=dict)


# -- Pluggable agent runtime (#83) -------------------------------------------


@dataclass
class AgentInvocation:
    """Input specification for an agent runtime invocation."""

    task: str
    tools: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    timeout_seconds: float = 0.0
    permissions: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentResult:
    """Outcome of an agent runtime invocation."""

    id: str
    status: str  # "completed", "failed", "cancelled", "timeout"
    output: str = ""
    structured_output: dict = field(default_factory=dict)
    tool_calls_made: int = 0
    tokens_used: int = 0
    duration_ms: float = 0.0
    error: str | None = None
    metadata: dict = field(default_factory=dict)


# -- Pluggable context engine (#84) ------------------------------------------


@dataclass
class ContextTransformation:
    """Record of a context transformation applied by a context engine."""

    id: str
    transformation_type: str
    input_tokens: int = 0
    output_tokens: int = 0
    content_type: str = ""
    quality_score: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ContextBudget:
    """Token budget allocation for context construction."""

    total_tokens: int
    system_tokens: int = 0
    retrieval_tokens: int = 0
    history_tokens: int = 0
    tool_tokens: int = 0
    remaining_tokens: int = 0


# -- Pluggable capability/tool backend (#85) ---------------------------------


@dataclass
class CapabilityDescriptor:
    """Descriptor for a capability exposed by a capability backend."""

    name: str
    description: str
    backend_type: str = ""
    input_schema: dict = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    requires_auth: bool = False
    rate_limit: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class CapabilityResult:
    """Result of invoking a capability through a capability backend."""

    capability_name: str
    backend_type: str
    output: object = None
    error: str | None = None
    duration_ms: float = 0.0
    provenance: str = ""
    metadata: dict = field(default_factory=dict)


# -- Pluggable evaluation engine (#86) ---------------------------------------


@dataclass
class EvaluationCandidate:
    """A candidate output submitted for evaluation."""

    id: str
    model: str
    output: str
    task: str
    metadata: dict = field(default_factory=dict)


@dataclass
class EvaluationScore:
    """Score assigned to an evaluation candidate."""

    candidate_id: str
    dimension: str
    score: float
    evaluator: str = ""
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class EvaluationEvidence:
    """Evidence and trace data from an evaluation run."""

    evaluation_id: str
    candidates: list[str] = field(default_factory=list)
    scores: list[EvaluationScore] = field(default_factory=list)
    verdict: str = ""
    consensus_method: str = ""
    reproducible: bool = False
    metadata: dict = field(default_factory=dict)


# -- Authenticated health checks (#87) ---------------------------------------


@dataclass
class HealthDetail:
    """Detailed status of a single health-check component."""

    component: str
    healthy: bool
    message: str = ""
    latency_ms: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class HealthCheckResult:
    """Aggregate result of a health check."""

    healthy: bool
    status: str = "ok"
    details: list[HealthDetail] = field(default_factory=list)
    authenticated: bool = False
    checked_at: str = ""


# -- REST API validation (#88) -----------------------------------------------


@dataclass
class ValidationError:
    """A single validation error for a request field."""

    field: str
    message: str
    code: str = ""
    value: object = None


@dataclass
class ValidationReport:
    """Aggregate validation result for a request."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    endpoint: str = ""
    http_status: int = 200
