"""Phase 5 data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  Phase 5 protocols reference these types for their method
signatures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# -- Evaluation & Regression Testing (#51) -----------------------------------


@dataclass
class EvalCase:
    """A single evaluation case pairing an input with expected output."""

    id: str
    input: str
    expected: str
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class EvalDataset:
    """A named collection of evaluation cases."""

    id: str
    name: str
    cases: list[EvalCase] = field(default_factory=list)
    version: str = ""
    description: str = ""


@dataclass
class MetricScore:
    """A single metric measurement from an evaluation run."""

    metric: str
    value: float
    evidence: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class EvalRunResult:
    """Aggregated outcome of an evaluation run across a dataset."""

    run_id: str
    dataset_id: str
    scores: list[MetricScore] = field(default_factory=list)
    model: str = ""
    config_version: str = ""
    passed: bool = True
    duration_ms: float = 0.0
    created_at: str = ""


@dataclass
class RegressionComparison:
    """Side-by-side comparison of two evaluation runs for regression detection."""

    baseline_run_id: str
    candidate_run_id: str
    regressions: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    verdict: str = ""


# -- GenAI Observability & Telemetry (#52) -----------------------------------


@dataclass
class GenAISpanAttributes:
    """Semantic attributes for a GenAI operation span.

    Captures model, provider, token usage, cost, and error details
    following OpenTelemetry GenAI semantic conventions.
    """

    operation: str
    model: str = ""
    provider: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    error: str | None = None
    tool_calls: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class RedactionPolicy:
    """Policy controlling what content is redacted in telemetry."""

    redact_prompts: bool = True
    redact_completions: bool = True
    redact_tool_arguments: bool = False
    allowed_metadata_keys: list[str] = field(default_factory=list)


@dataclass
class TelemetrySummary:
    """Aggregated telemetry summary over a time window."""

    total_spans: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    error_count: int = 0
    by_model: dict = field(default_factory=dict)
    by_operation: dict = field(default_factory=dict)


# -- Model Provider, Inference, and Routing (#53) ----------------------------


@dataclass
class ModelCapabilities:
    """Declared capabilities of a model for capability-based routing."""

    streaming: bool = False
    structured_output: bool = False
    tool_calling: bool = False
    vision: bool = False
    embeddings: bool = False
    max_context_tokens: int = 0
    max_output_tokens: int = 0
    supported_formats: list[str] = field(default_factory=list)


@dataclass
class InferenceEndpoint:
    """Connection descriptor for a model inference backend."""

    id: str
    provider: str
    base_url: str = ""
    model_id: str = ""
    api_type: str = "openai"
    healthy: bool = True
    latency_ms: float = 0.0
    quota_remaining: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class RoutingDecision:
    """Record of a routing decision with rationale."""

    selected_endpoint: str
    model: str
    reason: str = ""
    fallback_used: bool = False
    candidates_considered: int = 0
    latency_ms: float = 0.0


# -- Agent Runtime, State, and Durable Execution (#54) ----------------------


@dataclass
class AgentLifecycleState:
    """Serialisable snapshot of an agent's execution state."""

    agent_id: str
    step: str
    data: dict = field(default_factory=dict)
    status: str = "running"
    created_at: str = ""


@dataclass
class Checkpoint:
    """A durable checkpoint for agent or workflow resumption."""

    id: str
    agent_id: str
    state: AgentLifecycleState | None = None
    step: str = ""
    created_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class Handoff:
    """Record of control transfer between agents or agent and human."""

    id: str
    from_agent: str
    to_agent: str
    reason: str = ""
    context: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class AgentEvent:
    """Lifecycle event emitted during agent execution."""

    event_type: str
    agent_id: str
    step: str = ""
    detail: str = ""
    created_at: str = ""


# -- Persistent Agent Memory (#55) ------------------------------------------


@dataclass
class AgentMemoryEntry:
    """A single entry in agent-scoped persistent memory."""

    id: str
    agent_id: str
    scope: str
    memory_type: str
    content: str
    confidence: float = 1.0
    valid_from: str = ""
    valid_until: str | None = None
    superseded_by: str | None = None
    source_context: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class MemoryQuery:
    """Query descriptor for agent memory retrieval."""

    query: str
    agent_id: str | None = None
    scope: str | None = None
    memory_type: str | None = None
    limit: int = 10
    min_confidence: float = 0.0


@dataclass
class MemoryScope:
    """Isolation scope for agent memory."""

    scope: str
    agent_id: str | None = None
    user_id: str | None = None
    application_id: str | None = None


# -- Structured Output & Tool (#56) -----------------------------------------


@dataclass
class SchemaDefinition:
    """Versioned JSON Schema definition for structured outputs."""

    id: str
    name: str
    schema: dict = field(default_factory=dict)
    version: str = "1.0"
    description: str = ""


@dataclass
class ValidationResult:
    """Outcome of validating a model output against a schema."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    repaired: bool = False
    repair_detail: str = ""


@dataclass
class ToolIntent:
    """Model-generated intent to invoke a tool (pre-authorization)."""

    tool_name: str
    arguments: dict = field(default_factory=dict)
    request_id: str = ""
    model: str = ""


@dataclass
class ToolExecutionResult:
    """Result of an authorized tool execution."""

    request_id: str
    tool_name: str
    output: object = None
    error: str | None = None
    authorized: bool = True
    duration_ms: float = 0.0


# -- AI Security, Authorization, and Trust Boundary (#57) -------------------


@dataclass
class TrustBoundary:
    """Defines a trust boundary between system components."""

    id: str
    name: str
    components: list[str] = field(default_factory=list)
    trust_level: str = "untrusted"
    description: str = ""


@dataclass
class CapabilityPolicy:
    """Authorization policy for tool and resource access."""

    id: str
    agent_id: str
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    allowed_resources: list[str] = field(default_factory=list)
    max_cost_usd: float | None = None
    require_human_approval: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class SecurityEvent:
    """An auditable security event."""

    id: str
    event_type: str
    agent_id: str = ""
    detail: str = ""
    severity: str = "info"
    created_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ContentScanResult:
    """Result of scanning content for prompt injection or policy violations."""

    safe: bool
    threats: list[str] = field(default_factory=list)
    detail: str = ""
    scanned_at: str = ""


# -- AI Program Optimization (#58) ------------------------------------------


@dataclass
class OptimizationTarget:
    """A parameter or component eligible for programmatic optimization."""

    id: str
    name: str
    target_type: str
    current_value: str = ""
    search_space: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class ExperimentRun:
    """Record of a single optimization experiment run."""

    id: str
    target_id: str
    variant: str
    objective_scores: dict = field(default_factory=dict)
    eval_run_id: str = ""
    created_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class OptimizationResult:
    """Outcome of an optimization loop over an objective."""

    target_id: str
    best_variant: str
    best_scores: dict = field(default_factory=dict)
    total_experiments: int = 0
    improvement_pct: float = 0.0
    converged: bool = False
    metadata: dict = field(default_factory=dict)
