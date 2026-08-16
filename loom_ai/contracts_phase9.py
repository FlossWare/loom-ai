"""Phase 9 protocol contracts for loom-ai.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required.  All I/O methods
are async.  Nothing outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.

Phase 9 covers ten contract areas:

- **ModelEvaluationCandidate** -- provider-neutral model evaluation (#79)
- **CanonicalSourceIndex** -- canonical-source vs derived-index pattern (#80)
- **ContextCompressor** -- reversible context compression (#81)
- **PromptCacheOptimizer** -- prompt-cache awareness and optimization (#82)
- **AgentRuntime** -- pluggable agent runtime (#83)
- **ContextEngine** -- pluggable context engine (#84)
- **CapabilityBackend** -- pluggable capability and tool backend (#85)
- **EvaluationEngine** -- pluggable evaluation engine (#86)
- **HealthCheckPolicy** -- authenticated health-check semantics (#87)
- **RequestValidator** -- REST API request/response validation (#88)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.models_phase9 import (
        AgentInvocation,
        AgentResult,
        CacheCapability,
        CacheEvent,
        CanonicalSource,
        CapabilityDescriptor,
        CapabilityProfile,
        CapabilityResult,
        CompressedProjection,
        CompressionQuality,
        ContextBudget,
        ContextTransformation,
        DerivedIndex,
        EvaluationCandidate,
        EvaluationEvidence,
        HealthCheckResult,
        ModelBenchmark,
        ProvenanceRecord,
        ValidationReport,
    )


# -- Model Evaluation (#79) -------------------------------------------------


@runtime_checkable
class ModelEvaluationCandidate(Protocol):
    """Provider-neutral model evaluation and capability profiling.

    Supports discovering provider capabilities, benchmarking models on
    task types, and comparing candidates without coupling to any
    specific provider or inference backend.
    """

    async def profile(self, model: str, *, provider: str) -> CapabilityProfile:
        """Return the capability profile for *model* on *provider*."""
        ...

    async def benchmark(
        self,
        model: str,
        *,
        task_type: str,
        test_input: str,
        provider: str | None = None,
    ) -> ModelBenchmark:
        """Run a benchmark of *model* on a *task_type* and return metrics."""
        ...

    async def compare(
        self,
        candidates: list[str],
        *,
        task_type: str,
        test_input: str,
    ) -> list[ModelBenchmark]:
        """Compare multiple candidate models and return ranked benchmarks."""
        ...

    async def list_candidates(self) -> list[CapabilityProfile]:
        """Return capability profiles for all known candidate models."""
        ...


# -- Canonical Source Index (#80) --------------------------------------------


@runtime_checkable
class CanonicalSourceIndex(Protocol):
    """Canonical-source vs derived-index lifecycle management.

    Separates human-readable canonical knowledge from rebuildable
    derived indexes (graph, vector, search).  Preserves provenance
    from derived artifacts back to canonical sources.
    """

    async def register_source(
        self,
        uri: str,
        *,
        content_hash: str,
        format: str = "",
        metadata: dict | None = None,
    ) -> CanonicalSource:
        """Register a canonical source and return its record."""
        ...

    async def get_source(self, source_id: str) -> CanonicalSource | None:
        """Return a canonical source by id, or ``None`` if not found."""
        ...

    async def build_index(
        self,
        index_type: str,
        *,
        source_ids: list[str] | None = None,
    ) -> DerivedIndex:
        """Build (or rebuild) a derived index from canonical sources."""
        ...

    async def invalidate_index(self, index_id: str) -> bool:
        """Mark a derived index as stale, requiring a rebuild."""
        ...

    async def provenance(self, derived_id: str) -> list[ProvenanceRecord]:
        """Return provenance records tracing *derived_id* to its sources."""
        ...

    async def sync(self, source_id: str) -> list[str]:
        """Detect external edits to a source and return affected index ids."""
        ...


# -- Context Compressor (#81) ------------------------------------------------


@runtime_checkable
class ContextCompressor(Protocol):
    """Reversible, content-aware context compression.

    Supports compressing content for token efficiency while preserving
    the ability to retrieve the original.  Measures semantic preservation
    so token reduction can be balanced against answer quality.
    """

    async def compress(
        self,
        content: str,
        *,
        content_type: str = "",
        target_ratio: float = 0.5,
    ) -> CompressedProjection:
        """Compress *content* and return a projection with the original id."""
        ...

    async def decompress(self, projection_id: str) -> str:
        """Retrieve the original content from a compressed projection."""
        ...

    async def evaluate_quality(
        self,
        original: str,
        compressed: str,
        *,
        content_type: str = "",
    ) -> CompressionQuality:
        """Measure semantic preservation between original and compressed text."""
        ...

    async def supported_content_types(self) -> list[str]:
        """Return content types this compressor handles."""
        ...


# -- Prompt Cache Optimizer (#82) --------------------------------------------


@runtime_checkable
class PromptCacheOptimizer(Protocol):
    """Provider-neutral prompt-cache awareness and optimization.

    Discovers provider cache capabilities, constructs cache-friendly
    message sequences with stable prefixes, and tracks cache
    performance metrics.
    """

    async def discover_capabilities(self, provider: str) -> CacheCapability:
        """Return cache capabilities for *provider*."""
        ...

    async def optimize_messages(
        self,
        messages: list[dict],
        *,
        provider: str,
    ) -> list[dict]:
        """Reorder and annotate *messages* to maximize cache reuse."""
        ...

    async def record_event(self, event: CacheEvent) -> None:
        """Record a cache interaction event for observability."""
        ...

    async def metrics(self, *, provider: str | None = None) -> dict[str, Any]:
        """Return cache performance metrics, optionally filtered by provider."""
        ...


# -- Pluggable Agent Runtime (#83) -------------------------------------------


@runtime_checkable
class AgentRuntime(Protocol):
    """Provider-neutral contract for interchangeable agent runtimes.

    Supports lifecycle management, invocation, cancellation, capability
    discovery, and health monitoring for agent runtimes such as Goose,
    Claude Code, or a native Loom runtime.
    """

    async def invoke(self, invocation: AgentInvocation) -> AgentResult:
        """Execute an agent task and return the result."""
        ...

    async def cancel(self, invocation_id: str) -> bool:
        """Cancel a running invocation.  Return ``True`` if cancelled."""
        ...

    async def capabilities(self) -> list[str]:
        """Return capabilities supported by this runtime."""
        ...

    async def health(self) -> dict[str, Any]:
        """Return runtime health and availability information."""
        ...


# -- Pluggable Context Engine (#84) ------------------------------------------


@runtime_checkable
class ContextEngine(Protocol):
    """Provider-neutral context-engineering middleware.

    Sits between agents/retrieval and model providers.  Handles
    content-aware transformation, token-budget management,
    cache-aware construction, and quality measurement.
    """

    async def transform(
        self,
        content: str,
        *,
        content_type: str = "",
        budget: ContextBudget | None = None,
    ) -> ContextTransformation:
        """Transform *content* within an optional token budget."""
        ...

    async def allocate_budget(
        self,
        total_tokens: int,
        *,
        system_tokens: int = 0,
        retrieval_tokens: int = 0,
        history_tokens: int = 0,
    ) -> ContextBudget:
        """Compute a token budget allocation for context construction."""
        ...

    async def retrieve_original(self, transformation_id: str) -> str:
        """Retrieve the original content for a transformation."""
        ...

    async def quality_score(self, transformation_id: str) -> float:
        """Return the quality/faithfulness score for a transformation."""
        ...


# -- Pluggable Capability and Tool Backend (#85) -----------------------------


@runtime_checkable
class CapabilityBackend(Protocol):
    """Provider-neutral contract for interchangeable capability backends.

    Supports MCP servers, native tools, and external capability layers
    with discovery, fallback, health, authentication, permissions,
    and provenance.
    """

    async def discover(self) -> list[CapabilityDescriptor]:
        """Return descriptors for all capabilities available from this backend."""
        ...

    async def invoke(
        self,
        name: str,
        arguments: dict,
        *,
        auth_token: str | None = None,
    ) -> CapabilityResult:
        """Invoke a capability by name and return the result."""
        ...

    async def health(self, name: str | None = None) -> dict[str, bool]:
        """Return health status for capabilities, or all if *name* is ``None``."""
        ...

    async def supports(self, name: str) -> bool:
        """Return whether this backend provides the named capability."""
        ...


# -- Pluggable Evaluation Engine (#86) ---------------------------------------


@runtime_checkable
class EvaluationEngine(Protocol):
    """Provider-neutral evaluation and tournament engine.

    Supports candidate registration, multi-dimensional scoring,
    pairwise comparison, consensus strategies, and evidence
    preservation for reproducibility.
    """

    async def register_candidate(self, candidate: EvaluationCandidate) -> str:
        """Register a candidate for evaluation and return its id."""
        ...

    async def score(
        self,
        candidate_id: str,
        *,
        dimensions: list[str] | None = None,
        evaluators: list[str] | None = None,
    ) -> EvaluationEvidence:
        """Score a candidate across dimensions and return evidence."""
        ...

    async def compare(
        self,
        candidate_ids: list[str],
        *,
        dimensions: list[str] | None = None,
    ) -> EvaluationEvidence:
        """Compare multiple candidates and return ranked evidence."""
        ...

    async def get_evidence(self, evaluation_id: str) -> EvaluationEvidence | None:
        """Retrieve stored evidence for a past evaluation."""
        ...


# -- Health Check Policy (#87) -----------------------------------------------


@runtime_checkable
class HealthCheckPolicy(Protocol):
    """Authentication boundary and policy for health/readiness endpoints.

    Defines whether liveness and readiness probes require authentication,
    controls what information is exposed in unauthenticated responses,
    and supports Kubernetes/load-balancer/monitoring integration.
    """

    async def check_health(self, *, authenticated: bool = False) -> HealthCheckResult:
        """Run a health check.

        When *authenticated* is ``False``, the result must exclude
        sensitive diagnostic information.
        """
        ...

    async def check_readiness(
        self, *, authenticated: bool = False
    ) -> HealthCheckResult:
        """Run a readiness check.

        Readiness indicates the service can accept traffic.  When
        *authenticated* is ``False``, sensitive details are omitted.
        """
        ...

    def requires_auth(self, endpoint: str) -> bool:
        """Return whether *endpoint* requires authentication.

        Common endpoints: ``"/health"``, ``"/ready"``, ``"/healthz"``.
        """
        ...


# -- Request Validator (#88) -------------------------------------------------


@runtime_checkable
class RequestValidator(Protocol):
    """Typed request/response validation for REST API endpoints.

    Validates request payloads against schemas, returns consistent
    error responses, and ensures the OpenAPI contract accurately
    reflects the API surface.
    """

    async def validate_request(
        self,
        endpoint: str,
        payload: dict,
        *,
        method: str = "POST",
    ) -> ValidationReport:
        """Validate *payload* against the schema for *endpoint*."""
        ...

    async def validate_response(
        self,
        endpoint: str,
        payload: dict,
        *,
        status_code: int = 200,
    ) -> ValidationReport:
        """Validate a response payload against the schema for *endpoint*."""
        ...

    async def list_schemas(self) -> dict[str, dict]:
        """Return registered request/response schemas keyed by endpoint."""
        ...

    async def register_schema(
        self,
        endpoint: str,
        *,
        request_schema: dict | None = None,
        response_schema: dict | None = None,
    ) -> None:
        """Register or update request/response schemas for *endpoint*."""
        ...
