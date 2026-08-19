"""In-memory Phase 9 backend implementations for loom-ai.

All classes use only the standard library -- zero external dependencies.
Suitable for testing, local development, and the 'crush' deployment
profile.  All data is lost on process exit.

Classes
-------
InMemoryModelEvaluationCandidate  -- dict-backed model evaluation and profiling
InMemoryCanonicalSourceIndex      -- dict-backed canonical source vs derived index
InMemoryContextCompressor         -- dict-backed reversible context compression
InMemoryPromptCacheOptimizer      -- dict-backed prompt cache optimization
InMemoryPluggableAgentRuntime     -- dict-backed agent runtime
InMemoryContextEngine             -- dict-backed context engineering middleware
InMemoryCapabilityBackend         -- dict-backed capability and tool backend
InMemoryEvaluationEngine          -- dict-backed evaluation and tournament engine
InMemoryHealthCheckPolicy         -- configurable health check policy
InMemoryRequestValidator          -- dict-backed request/response validation
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
    EvaluationScore,
    HealthCheckResult,
    HealthDetail,
    ModelBenchmark,
    ProvenanceRecord,
    ValidationError,
    ValidationReport,
)

# ---- helpers ---------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# ModelEvaluationCandidate
# ============================================================================


class InMemoryModelEvaluationCandidate:
    """Dict-backed model evaluation and capability profiling."""

    def __init__(self) -> None:
        self._profiles: dict[str, CapabilityProfile] = {}

    async def profile(self, model: str, *, provider: str) -> CapabilityProfile:
        key = f"{provider}:{model}"
        if key not in self._profiles:
            self._profiles[key] = CapabilityProfile(model=model, provider=provider)
        return self._profiles[key]

    async def benchmark(
        self,
        model: str,
        *,
        task_type: str,
        test_input: str,
        _provider: str | None = None,
    ) -> ModelBenchmark:
        return ModelBenchmark(
            model=model,
            task_type=task_type,
            score=1.0,
            latency_ms=0.0,
            tokens_used=len(test_input.split()),
        )

    async def compare(
        self,
        candidates: list[str],
        *,
        task_type: str,
        test_input: str,
    ) -> list[ModelBenchmark]:
        results: list[ModelBenchmark] = []
        for model in candidates:
            bm = await self.benchmark(model, task_type=task_type, test_input=test_input)
            results.append(bm)
        return results

    async def list_candidates(self) -> list[CapabilityProfile]:
        return list(self._profiles.values())


# ============================================================================
# CanonicalSourceIndex
# ============================================================================


class InMemoryCanonicalSourceIndex:
    """Dict-backed canonical-source vs derived-index lifecycle."""

    def __init__(self) -> None:
        self._sources: dict[str, CanonicalSource] = {}
        self._indexes: dict[str, DerivedIndex] = {}
        self._provenance: dict[str, list[ProvenanceRecord]] = {}

    async def register_source(
        self,
        uri: str,
        *,
        content_hash: str,
        format: str = "",
        metadata: dict | None = None,
    ) -> CanonicalSource:
        source_id = str(uuid.uuid4())
        now = _now_iso()
        source = CanonicalSource(
            id=source_id,
            uri=uri,
            content_hash=content_hash,
            format=format,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self._sources[source_id] = source
        return source

    async def get_source(self, source_id: str) -> CanonicalSource | None:
        return self._sources.get(source_id)

    async def build_index(
        self,
        index_type: str,
        *,
        source_ids: list[str] | None = None,
    ) -> DerivedIndex:
        index_id = str(uuid.uuid4())
        resolved_ids = source_ids or list(self._sources.keys())
        now = _now_iso()
        index = DerivedIndex(
            id=index_id,
            index_type=index_type,
            source_ids=resolved_ids,
            status="built",
            built_at=now,
        )
        self._indexes[index_id] = index

        records: list[ProvenanceRecord] = []
        for sid in resolved_ids:
            source = self._sources.get(sid)
            records.append(
                ProvenanceRecord(
                    derived_id=index_id,
                    source_id=sid,
                    source_uri=source.uri if source else "",
                    transformation=index_type,
                    created_at=now,
                )
            )
        self._provenance[index_id] = records
        return index

    async def invalidate_index(self, index_id: str) -> bool:
        if index_id not in self._indexes:
            return False
        self._indexes[index_id].status = "stale"
        return True

    async def provenance(self, derived_id: str) -> list[ProvenanceRecord]:
        return list(self._provenance.get(derived_id, []))

    async def sync(self, source_id: str) -> list[str]:
        affected: list[str] = []
        for index in self._indexes.values():
            if source_id in index.source_ids:
                index.status = "stale"
                affected.append(index.id)
        return affected


# ============================================================================
# ContextCompressor
# ============================================================================


class InMemoryContextCompressor:
    """Dict-backed reversible context compression via sentence truncation."""

    def __init__(self) -> None:
        self._originals: dict[str, str] = {}

    async def compress(
        self,
        content: str,
        *,
        content_type: str = "",
        target_ratio: float = 0.5,
    ) -> CompressedProjection:
        projection_id = str(uuid.uuid4())
        original_id = str(uuid.uuid4())
        self._originals[projection_id] = content

        sentences = [s.strip() for s in content.split(".") if s.strip()]
        keep = max(1, int(len(sentences) * target_ratio))
        compressed = ". ".join(sentences[:keep])
        if compressed and not compressed.endswith("."):
            compressed += "."

        ratio = len(compressed) / len(content) if content else 0.0
        return CompressedProjection(
            id=projection_id,
            original_id=original_id,
            compressed_content=compressed,
            content_type=content_type,
            compression_ratio=ratio,
            reversible=True,
        )

    async def decompress(self, projection_id: str) -> str:
        if projection_id not in self._originals:
            raise KeyError(f"Unknown projection: {projection_id}")
        return self._originals[projection_id]

    async def evaluate_quality(
        self,
        original: str,
        compressed: str,
        *,
        content_type: str = "",
    ) -> CompressionQuality:
        orig_words = set(original.lower().split())
        comp_words = set(compressed.lower().split())
        overlap = len(orig_words & comp_words)
        preservation = overlap / len(orig_words) if orig_words else 1.0
        reduction = 1.0 - (len(compressed) / len(original)) if original else 0.0
        return CompressionQuality(
            semantic_preservation=preservation,
            token_reduction=reduction,
            information_loss=1.0 - preservation,
            content_type=content_type,
        )

    async def supported_content_types(self) -> list[str]:
        return ["text/plain", "text/markdown", "application/json"]


# ============================================================================
# PromptCacheOptimizer
# ============================================================================


class InMemoryPromptCacheOptimizer:
    """Dict-backed prompt cache optimization with stable-prefix reordering."""

    def __init__(self) -> None:
        self._events: list[CacheEvent] = []
        self._capabilities: dict[str, CacheCapability] = {}

    async def discover_capabilities(self, provider: str) -> CacheCapability:
        if provider not in self._capabilities:
            self._capabilities[provider] = CacheCapability(
                provider=provider,
                supported=True,
                prefix_based=True,
                max_ttl_seconds=300,
                max_cached_tokens=4096,
            )
        return self._capabilities[provider]

    async def optimize_messages(
        self,
        messages: list[dict],
        *,
        provider: str,
    ) -> list[dict]:
        system: list[dict] = []
        other: list[dict] = []
        for msg in messages:
            if msg.get("role") == "system":
                system.append(msg)
            else:
                other.append(msg)
        return system + other

    async def record_event(self, event: CacheEvent) -> None:
        self._events.append(event)

    async def metrics(self, *, provider: str | None = None) -> dict[str, object]:
        filtered = self._events
        if provider is not None:
            filtered = [e for e in self._events if e.provider == provider]
        hits = sum(1 for e in filtered if e.event_type == "hit")
        misses = sum(1 for e in filtered if e.event_type == "miss")
        total = hits + misses
        return {
            "total_events": len(filtered),
            "hits": hits,
            "misses": misses,
            "hit_rate": hits / total if total else 0.0,
            "total_tokens_affected": sum(e.tokens_affected for e in filtered),
            "total_latency_saved_ms": sum(e.latency_saved_ms for e in filtered),
            "total_cost_saved": sum(e.cost_saved for e in filtered),
        }


# ============================================================================
# PluggableAgentRuntime
# ============================================================================


class InMemoryPluggableAgentRuntime:
    """Dict-backed agent runtime that echoes tasks as completed results."""

    def __init__(self) -> None:
        self._invocations: dict[str, AgentResult] = {}

    async def invoke(self, invocation: AgentInvocation) -> AgentResult:
        result_id = str(uuid.uuid4())
        result = AgentResult(
            id=result_id,
            status="completed",
            output=f"Completed: {invocation.task}",
            tool_calls_made=0,
            tokens_used=len(invocation.task.split()),
        )
        self._invocations[result_id] = result
        return result

    async def cancel(self, invocation_id: str) -> bool:
        if invocation_id not in self._invocations:
            return False
        self._invocations[invocation_id].status = "cancelled"
        return True

    async def capabilities(self) -> list[str]:
        return ["text-generation", "tool-calling", "structured-output"]

    async def health(self) -> dict[str, object]:
        return {"status": "healthy", "runtime": "in-memory", "active": True}


# ============================================================================
# ContextEngine
# ============================================================================


class InMemoryContextEngine:
    """Dict-backed context engineering middleware."""

    def __init__(self) -> None:
        self._transformations: dict[str, tuple[str, float]] = {}

    async def transform(
        self,
        content: str,
        *,
        content_type: str = "",
        budget: ContextBudget | None = None,
    ) -> ContextTransformation:
        tid = str(uuid.uuid4())
        input_tokens = len(content.split())

        if budget and input_tokens > budget.remaining_tokens:
            words = content.split()[: budget.remaining_tokens]
            output_tokens = len(words)
        else:
            output_tokens = input_tokens

        quality = 1.0 if output_tokens == input_tokens else output_tokens / input_tokens
        self._transformations[tid] = (content, quality)
        return ContextTransformation(
            id=tid,
            transformation_type=(
                "passthrough" if output_tokens == input_tokens else "truncation"
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            content_type=content_type,
            quality_score=quality,
        )

    async def allocate_budget(
        self,
        total_tokens: int,
        *,
        system_tokens: int = 0,
        retrieval_tokens: int = 0,
        history_tokens: int = 0,
    ) -> ContextBudget:
        allocated = system_tokens + retrieval_tokens + history_tokens
        remaining = max(0, total_tokens - allocated)
        return ContextBudget(
            total_tokens=total_tokens,
            system_tokens=system_tokens,
            retrieval_tokens=retrieval_tokens,
            history_tokens=history_tokens,
            remaining_tokens=remaining,
        )

    async def retrieve_original(self, transformation_id: str) -> str:
        if transformation_id not in self._transformations:
            raise KeyError(f"Unknown transformation: {transformation_id}")
        return self._transformations[transformation_id][0]

    async def quality_score(self, transformation_id: str) -> float:
        if transformation_id not in self._transformations:
            raise KeyError(f"Unknown transformation: {transformation_id}")
        return self._transformations[transformation_id][1]


# ============================================================================
# CapabilityBackend
# ============================================================================


class InMemoryCapabilityBackend:
    """Dict-backed capability and tool backend."""

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityDescriptor] = {}

    def register(self, descriptor: CapabilityDescriptor) -> None:
        """Register a capability descriptor (not part of the protocol)."""
        self._capabilities[descriptor.name] = descriptor

    async def discover(self) -> list[CapabilityDescriptor]:
        return list(self._capabilities.values())

    async def invoke(
        self,
        name: str,
        arguments: dict,
        *,
        auth_token: str | None = None,
    ) -> CapabilityResult:
        if name not in self._capabilities:
            return CapabilityResult(
                capability_name=name,
                backend_type="in-memory",
                error=f"Unknown capability: {name}",
            )
        desc = self._capabilities[name]
        if desc.requires_auth and not auth_token:
            return CapabilityResult(
                capability_name=name,
                backend_type="in-memory",
                error="Authentication required",
            )
        return CapabilityResult(
            capability_name=name,
            backend_type="in-memory",
            output=arguments,
            provenance="in-memory-backend",
        )

    async def health(self, name: str | None = None) -> dict[str, bool]:
        if name is not None:
            return {name: name in self._capabilities}
        return dict.fromkeys(self._capabilities, True)

    async def supports(self, name: str) -> bool:
        return name in self._capabilities


# ============================================================================
# EvaluationEngine
# ============================================================================


class InMemoryEvaluationEngine:
    """Dict-backed evaluation and tournament engine."""

    def __init__(self) -> None:
        self._candidates: dict[str, EvaluationCandidate] = {}
        self._evidence: dict[str, EvaluationEvidence] = {}

    async def register_candidate(self, candidate: EvaluationCandidate) -> str:
        self._candidates[candidate.id] = candidate
        return candidate.id

    async def score(
        self,
        candidate_id: str,
        *,
        dimensions: list[str] | None = None,
        evaluators: list[str] | None = None,
    ) -> EvaluationEvidence:
        if candidate_id not in self._candidates:
            raise KeyError(f"Unknown candidate: {candidate_id}")

        dims = dimensions or ["quality", "relevance", "coherence"]
        evals = evaluators or ["in-memory"]
        evaluation_id = str(uuid.uuid4())

        scores: list[EvaluationScore] = []
        for dim in dims:
            for evaluator in evals:
                scores.append(
                    EvaluationScore(
                        candidate_id=candidate_id,
                        dimension=dim,
                        score=1.0,
                        evaluator=evaluator,
                        confidence=1.0,
                    )
                )

        evidence = EvaluationEvidence(
            evaluation_id=evaluation_id,
            candidates=[candidate_id],
            scores=scores,
            verdict="pass",
            consensus_method="unanimous",
            reproducible=True,
        )
        self._evidence[evaluation_id] = evidence
        return evidence

    async def compare(
        self,
        candidate_ids: list[str],
        *,
        dimensions: list[str] | None = None,
    ) -> EvaluationEvidence:
        dims = dimensions or ["quality", "relevance", "coherence"]
        evaluation_id = str(uuid.uuid4())

        scores: list[EvaluationScore] = []
        for cid in candidate_ids:
            for dim in dims:
                scores.append(
                    EvaluationScore(
                        candidate_id=cid,
                        dimension=dim,
                        score=1.0,
                        evaluator="in-memory",
                        confidence=1.0,
                    )
                )

        evidence = EvaluationEvidence(
            evaluation_id=evaluation_id,
            candidates=list(candidate_ids),
            scores=scores,
            verdict="tie",
            consensus_method="pairwise",
            reproducible=True,
        )
        self._evidence[evaluation_id] = evidence
        return evidence

    async def get_evidence(self, evaluation_id: str) -> EvaluationEvidence | None:
        return self._evidence.get(evaluation_id)


# ============================================================================
# HealthCheckPolicy
# ============================================================================


class InMemoryHealthCheckPolicy:
    """Configurable health check policy with auth requirements per endpoint."""

    def __init__(
        self,
        *,
        auth_endpoints: set[str] | None = None,
        healthy: bool = True,
        ready: bool = True,
    ) -> None:
        self._auth_endpoints: set[str] = auth_endpoints or set()
        self._healthy = healthy
        self._ready = ready

    async def check_health(self, *, authenticated: bool = False) -> HealthCheckResult:
        details: list[HealthDetail] = []
        if authenticated:
            details.append(
                HealthDetail(
                    component="storage",
                    healthy=self._healthy,
                    message="in-memory",
                )
            )
        return HealthCheckResult(
            healthy=self._healthy,
            status="ok" if self._healthy else "degraded",
            details=details,
            authenticated=authenticated,
            checked_at=_now_iso(),
        )

    async def check_readiness(
        self,
        *,
        authenticated: bool = False,
    ) -> HealthCheckResult:
        details: list[HealthDetail] = []
        if authenticated:
            details.append(
                HealthDetail(
                    component="runtime",
                    healthy=self._ready,
                    message="in-memory",
                )
            )
        return HealthCheckResult(
            healthy=self._ready,
            status="ready" if self._ready else "not_ready",
            details=details,
            authenticated=authenticated,
            checked_at=_now_iso(),
        )

    def requires_auth(self, endpoint: str) -> bool:
        return endpoint in self._auth_endpoints


# ============================================================================
# RequestValidator
# ============================================================================


class InMemoryRequestValidator:
    """Dict-backed request/response validation against registered schemas."""

    def __init__(self) -> None:
        self._request_schemas: dict[str, dict] = {}
        self._response_schemas: dict[str, dict] = {}

    async def validate_request(
        self,
        endpoint: str,
        payload: dict,
        *,
        method: str = "POST",
    ) -> ValidationReport:
        schema = self._request_schemas.get(endpoint)
        if schema is None:
            return ValidationReport(valid=True, endpoint=endpoint)
        return self._validate_payload(payload, schema, endpoint)

    async def validate_response(
        self,
        endpoint: str,
        payload: dict,
        *,
        status_code: int = 200,
    ) -> ValidationReport:
        schema = self._response_schemas.get(endpoint)
        if schema is None:
            return ValidationReport(
                valid=True,
                endpoint=endpoint,
                http_status=status_code,
            )
        report = self._validate_payload(payload, schema, endpoint)
        report.http_status = status_code
        return report

    async def list_schemas(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        all_endpoints = set(self._request_schemas) | set(self._response_schemas)
        for ep in sorted(all_endpoints):
            result[ep] = {
                "request": self._request_schemas.get(ep, {}),
                "response": self._response_schemas.get(ep, {}),
            }
        return result

    async def register_schema(
        self,
        endpoint: str,
        *,
        request_schema: dict | None = None,
        response_schema: dict | None = None,
    ) -> None:
        if request_schema is not None:
            self._request_schemas[endpoint] = request_schema
        if response_schema is not None:
            self._response_schemas[endpoint] = response_schema

    def _validate_payload(
        self, payload: dict, schema: dict, endpoint: str
    ) -> ValidationReport:
        errors: list[ValidationError] = []
        required = schema.get("required", [])
        for field_name in required:
            if field_name not in payload:
                errors.append(
                    ValidationError(
                        field=field_name,
                        message=f"Required field '{field_name}' is missing",
                        code="required",
                    )
                )
        return ValidationReport(
            valid=len(errors) == 0,
            errors=errors,
            endpoint=endpoint,
            http_status=400 if errors else 200,
        )
