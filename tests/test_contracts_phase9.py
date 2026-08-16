"""Conformance tests for Phase 9 protocol contracts.

Each protocol is verified by constructing a minimal stub class that
implements the required method signatures and asserting that it
satisfies the ``@runtime_checkable`` protocol via ``isinstance``.

Tests also verify that dataclass models instantiate correctly and
carry the expected default values.
"""

from __future__ import annotations

from typing import Any

from loom_ai.contracts_phase9 import (
    AgentRuntime,
    CanonicalSourceIndex,
    CapabilityBackend,
    ContextCompressor,
    ContextEngine,
    EvaluationEngine,
    HealthCheckPolicy,
    ModelEvaluationCandidate,
    PromptCacheOptimizer,
    RequestValidator,
)
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

# ── Stub implementations ────────────────────────────────────────────────


class StubModelEvaluationCandidate:
    async def profile(self, model: str, *, provider: str) -> CapabilityProfile:
        return CapabilityProfile(model=model, provider=provider)

    async def benchmark(
        self,
        model: str,
        *,
        task_type: str,
        test_input: str,
        provider: str | None = None,
    ) -> ModelBenchmark:
        return ModelBenchmark(
            model=model, task_type=task_type, score=0.0, latency_ms=0.0, tokens_used=0
        )

    async def compare(
        self, candidates: list[str], *, task_type: str, test_input: str
    ) -> list[ModelBenchmark]:
        return []

    async def list_candidates(self) -> list[CapabilityProfile]:
        return []


class StubCanonicalSourceIndex:
    async def register_source(
        self,
        uri: str,
        *,
        content_hash: str,
        format: str = "",
        metadata: dict | None = None,
    ) -> CanonicalSource:
        return CanonicalSource(id="src-1", uri=uri, content_hash=content_hash)

    async def get_source(self, source_id: str) -> CanonicalSource | None:
        return None

    async def build_index(
        self, index_type: str, *, source_ids: list[str] | None = None
    ) -> DerivedIndex:
        return DerivedIndex(id="idx-1", index_type=index_type)

    async def invalidate_index(self, index_id: str) -> bool:
        return True

    async def provenance(self, derived_id: str) -> list[ProvenanceRecord]:
        return []

    async def sync(self, source_id: str) -> list[str]:
        return []


class StubContextCompressor:
    async def compress(
        self,
        content: str,
        *,
        content_type: str = "",
        target_ratio: float = 0.5,
    ) -> CompressedProjection:
        return CompressedProjection(
            id="proj-1", original_id="orig-1", compressed_content=content[:10]
        )

    async def decompress(self, projection_id: str) -> str:
        return ""

    async def evaluate_quality(
        self, original: str, compressed: str, *, content_type: str = ""
    ) -> CompressionQuality:
        return CompressionQuality()

    async def supported_content_types(self) -> list[str]:
        return ["text/plain"]


class StubPromptCacheOptimizer:
    async def discover_capabilities(self, provider: str) -> CacheCapability:
        return CacheCapability(provider=provider)

    async def optimize_messages(
        self, messages: list[dict], *, provider: str
    ) -> list[dict]:
        return messages

    async def record_event(self, event: CacheEvent) -> None:
        pass

    async def metrics(self, *, provider: str | None = None) -> dict[str, Any]:
        return {}


class StubAgentRuntime:
    async def invoke(self, invocation: AgentInvocation) -> AgentResult:
        return AgentResult(id="run-1", status="completed", output="done")

    async def cancel(self, invocation_id: str) -> bool:
        return True

    async def capabilities(self) -> list[str]:
        return ["tool_calling"]

    async def health(self) -> dict[str, Any]:
        return {"healthy": True}


class StubContextEngine:
    async def transform(
        self,
        content: str,
        *,
        content_type: str = "",
        budget: ContextBudget | None = None,
    ) -> ContextTransformation:
        return ContextTransformation(id="tx-1", transformation_type="compress")

    async def allocate_budget(
        self,
        total_tokens: int,
        *,
        system_tokens: int = 0,
        retrieval_tokens: int = 0,
        history_tokens: int = 0,
    ) -> ContextBudget:
        remaining = total_tokens - system_tokens - retrieval_tokens - history_tokens
        return ContextBudget(
            total_tokens=total_tokens,
            system_tokens=system_tokens,
            retrieval_tokens=retrieval_tokens,
            history_tokens=history_tokens,
            remaining_tokens=max(0, remaining),
        )

    async def retrieve_original(self, transformation_id: str) -> str:
        return ""

    async def quality_score(self, transformation_id: str) -> float:
        return 1.0


class StubCapabilityBackend:
    async def discover(self) -> list[CapabilityDescriptor]:
        return []

    async def invoke(
        self, name: str, arguments: dict, *, auth_token: str | None = None
    ) -> CapabilityResult:
        return CapabilityResult(capability_name=name, backend_type="stub")

    async def health(self, name: str | None = None) -> dict[str, bool]:
        return {"stub": True}

    async def supports(self, name: str) -> bool:
        return False


class StubEvaluationEngine:
    async def register_candidate(self, candidate: EvaluationCandidate) -> str:
        return candidate.id

    async def score(
        self,
        candidate_id: str,
        *,
        dimensions: list[str] | None = None,
        evaluators: list[str] | None = None,
    ) -> EvaluationEvidence:
        return EvaluationEvidence(evaluation_id="eval-1")

    async def compare(
        self,
        candidate_ids: list[str],
        *,
        dimensions: list[str] | None = None,
    ) -> EvaluationEvidence:
        return EvaluationEvidence(evaluation_id="eval-2", candidates=candidate_ids)

    async def get_evidence(self, evaluation_id: str) -> EvaluationEvidence | None:
        return None


class StubHealthCheckPolicy:
    async def check_health(self, *, authenticated: bool = False) -> HealthCheckResult:
        return HealthCheckResult(healthy=True, authenticated=authenticated)

    async def check_readiness(
        self, *, authenticated: bool = False
    ) -> HealthCheckResult:
        return HealthCheckResult(healthy=True, authenticated=authenticated)

    def requires_auth(self, endpoint: str) -> bool:
        return endpoint not in ("/health", "/healthz")


class StubRequestValidator:
    async def validate_request(
        self, endpoint: str, payload: dict, *, method: str = "POST"
    ) -> ValidationReport:
        return ValidationReport(valid=True, endpoint=endpoint)

    async def validate_response(
        self, endpoint: str, payload: dict, *, status_code: int = 200
    ) -> ValidationReport:
        return ValidationReport(valid=True, endpoint=endpoint)

    async def list_schemas(self) -> dict[str, dict]:
        return {}

    async def register_schema(
        self,
        endpoint: str,
        *,
        request_schema: dict | None = None,
        response_schema: dict | None = None,
    ) -> None:
        pass


# ── Protocol conformance tests ──────────────────────────────────────────


def test_model_evaluation_candidate_conformance():
    """StubModelEvaluationCandidate satisfies the protocol."""
    assert isinstance(StubModelEvaluationCandidate(), ModelEvaluationCandidate)


def test_canonical_source_index_conformance():
    """StubCanonicalSourceIndex satisfies the protocol."""
    assert isinstance(StubCanonicalSourceIndex(), CanonicalSourceIndex)


def test_context_compressor_conformance():
    """StubContextCompressor satisfies the protocol."""
    assert isinstance(StubContextCompressor(), ContextCompressor)


def test_prompt_cache_optimizer_conformance():
    """StubPromptCacheOptimizer satisfies the protocol."""
    assert isinstance(StubPromptCacheOptimizer(), PromptCacheOptimizer)


def test_agent_runtime_conformance():
    """StubAgentRuntime satisfies the protocol."""
    assert isinstance(StubAgentRuntime(), AgentRuntime)


def test_context_engine_conformance():
    """StubContextEngine satisfies the protocol."""
    assert isinstance(StubContextEngine(), ContextEngine)


def test_capability_backend_conformance():
    """StubCapabilityBackend satisfies the protocol."""
    assert isinstance(StubCapabilityBackend(), CapabilityBackend)


def test_evaluation_engine_conformance():
    """StubEvaluationEngine satisfies the protocol."""
    assert isinstance(StubEvaluationEngine(), EvaluationEngine)


def test_health_check_policy_conformance():
    """StubHealthCheckPolicy satisfies the protocol."""
    assert isinstance(StubHealthCheckPolicy(), HealthCheckPolicy)


def test_request_validator_conformance():
    """StubRequestValidator satisfies the protocol."""
    assert isinstance(StubRequestValidator(), RequestValidator)


# ── Stub behavior tests ─────────────────────────────────────────────────


async def test_model_evaluation_profile():
    """profile() returns a CapabilityProfile for the requested model."""
    stub = StubModelEvaluationCandidate()
    profile = await stub.profile("nemotron-ultra", provider="nvidia")
    assert isinstance(profile, CapabilityProfile)
    assert profile.model == "nemotron-ultra"
    assert profile.provider == "nvidia"


async def test_model_evaluation_benchmark():
    """benchmark() returns a ModelBenchmark with the given task type."""
    stub = StubModelEvaluationCandidate()
    result = await stub.benchmark(
        "gpt-4o", task_type="reasoning", test_input="solve x+1=2"
    )
    assert isinstance(result, ModelBenchmark)
    assert result.task_type == "reasoning"


async def test_model_evaluation_compare():
    """compare() returns a list of ModelBenchmark."""
    stub = StubModelEvaluationCandidate()
    results = await stub.compare(
        ["model-a", "model-b"], task_type="code", test_input="write hello world"
    )
    assert isinstance(results, list)


async def test_model_evaluation_list_candidates():
    """list_candidates() returns a list of CapabilityProfile."""
    stub = StubModelEvaluationCandidate()
    candidates = await stub.list_candidates()
    assert isinstance(candidates, list)


async def test_canonical_source_register():
    """register_source() returns a CanonicalSource with correct uri."""
    stub = StubCanonicalSourceIndex()
    source = await stub.register_source("file:///docs/readme.md", content_hash="abc123")
    assert isinstance(source, CanonicalSource)
    assert source.uri == "file:///docs/readme.md"
    assert source.content_hash == "abc123"


async def test_canonical_source_get_missing():
    """get_source() returns None for unknown ids."""
    stub = StubCanonicalSourceIndex()
    assert await stub.get_source("nonexistent") is None


async def test_canonical_source_build_index():
    """build_index() returns a DerivedIndex."""
    stub = StubCanonicalSourceIndex()
    idx = await stub.build_index("vector", source_ids=["src-1"])
    assert isinstance(idx, DerivedIndex)
    assert idx.index_type == "vector"


async def test_canonical_source_invalidate():
    """invalidate_index() returns True."""
    stub = StubCanonicalSourceIndex()
    assert await stub.invalidate_index("idx-1") is True


async def test_canonical_source_provenance():
    """provenance() returns a list of ProvenanceRecord."""
    stub = StubCanonicalSourceIndex()
    records = await stub.provenance("derived-1")
    assert isinstance(records, list)


async def test_canonical_source_sync():
    """sync() returns a list of affected index ids."""
    stub = StubCanonicalSourceIndex()
    affected = await stub.sync("src-1")
    assert isinstance(affected, list)


async def test_context_compressor_compress():
    """compress() returns a CompressedProjection."""
    stub = StubContextCompressor()
    proj = await stub.compress("A long document...", content_type="text/plain")
    assert isinstance(proj, CompressedProjection)
    assert proj.id == "proj-1"


async def test_context_compressor_decompress():
    """decompress() returns a string."""
    stub = StubContextCompressor()
    text = await stub.decompress("proj-1")
    assert isinstance(text, str)


async def test_context_compressor_evaluate_quality():
    """evaluate_quality() returns a CompressionQuality."""
    stub = StubContextCompressor()
    quality = await stub.evaluate_quality("original text", "compressed")
    assert isinstance(quality, CompressionQuality)


async def test_context_compressor_supported_types():
    """supported_content_types() returns a non-empty list."""
    stub = StubContextCompressor()
    types = await stub.supported_content_types()
    assert "text/plain" in types


async def test_prompt_cache_discover():
    """discover_capabilities() returns a CacheCapability."""
    stub = StubPromptCacheOptimizer()
    cap = await stub.discover_capabilities("anthropic")
    assert isinstance(cap, CacheCapability)
    assert cap.provider == "anthropic"


async def test_prompt_cache_optimize():
    """optimize_messages() returns a list of dicts."""
    stub = StubPromptCacheOptimizer()
    msgs = [{"role": "system", "content": "You are helpful."}]
    result = await stub.optimize_messages(msgs, provider="openai")
    assert isinstance(result, list)
    assert len(result) == 1


async def test_prompt_cache_record_event():
    """record_event() accepts a CacheEvent without error."""
    stub = StubPromptCacheOptimizer()
    event = CacheEvent(provider="anthropic", event_type="hit", tokens_affected=100)
    await stub.record_event(event)


async def test_prompt_cache_metrics():
    """metrics() returns a dict."""
    stub = StubPromptCacheOptimizer()
    m = await stub.metrics(provider="anthropic")
    assert isinstance(m, dict)


async def test_agent_runtime_invoke():
    """invoke() returns an AgentResult with completed status."""
    stub = StubAgentRuntime()
    invocation = AgentInvocation(task="write tests")
    result = await stub.invoke(invocation)
    assert isinstance(result, AgentResult)
    assert result.status == "completed"


async def test_agent_runtime_cancel():
    """cancel() returns True."""
    stub = StubAgentRuntime()
    assert await stub.cancel("run-1") is True


async def test_agent_runtime_capabilities():
    """capabilities() returns a list of strings."""
    stub = StubAgentRuntime()
    caps = await stub.capabilities()
    assert "tool_calling" in caps


async def test_agent_runtime_health():
    """health() returns a dict with healthy status."""
    stub = StubAgentRuntime()
    h = await stub.health()
    assert h["healthy"] is True


async def test_context_engine_transform():
    """transform() returns a ContextTransformation."""
    stub = StubContextEngine()
    tx = await stub.transform("some content", content_type="text/plain")
    assert isinstance(tx, ContextTransformation)
    assert tx.transformation_type == "compress"


async def test_context_engine_allocate_budget():
    """allocate_budget() returns a ContextBudget with correct allocation."""
    stub = StubContextEngine()
    budget = await stub.allocate_budget(
        4096, system_tokens=512, retrieval_tokens=1024, history_tokens=256
    )
    assert isinstance(budget, ContextBudget)
    assert budget.total_tokens == 4096
    assert budget.remaining_tokens == 4096 - 512 - 1024 - 256


async def test_context_engine_retrieve_original():
    """retrieve_original() returns a string."""
    stub = StubContextEngine()
    text = await stub.retrieve_original("tx-1")
    assert isinstance(text, str)


async def test_context_engine_quality_score():
    """quality_score() returns a float."""
    stub = StubContextEngine()
    score = await stub.quality_score("tx-1")
    assert score == 1.0


async def test_capability_backend_discover():
    """discover() returns a list of CapabilityDescriptor."""
    stub = StubCapabilityBackend()
    descriptors = await stub.discover()
    assert isinstance(descriptors, list)


async def test_capability_backend_invoke():
    """invoke() returns a CapabilityResult."""
    stub = StubCapabilityBackend()
    result = await stub.invoke("search", {"query": "test"})
    assert isinstance(result, CapabilityResult)
    assert result.capability_name == "search"
    assert result.backend_type == "stub"


async def test_capability_backend_invoke_with_auth():
    """invoke() accepts an auth_token keyword argument."""
    stub = StubCapabilityBackend()
    result = await stub.invoke("search", {"query": "test"}, auth_token="secret")
    assert isinstance(result, CapabilityResult)


async def test_capability_backend_health():
    """health() returns a dict of capability health statuses."""
    stub = StubCapabilityBackend()
    h = await stub.health()
    assert isinstance(h, dict)
    assert h["stub"] is True


async def test_capability_backend_supports():
    """supports() returns a boolean."""
    stub = StubCapabilityBackend()
    assert await stub.supports("nonexistent") is False


async def test_evaluation_engine_register():
    """register_candidate() returns the candidate id."""
    stub = StubEvaluationEngine()
    candidate = EvaluationCandidate(
        id="cand-1", model="gpt-4o", output="hello", task="greet"
    )
    cid = await stub.register_candidate(candidate)
    assert cid == "cand-1"


async def test_evaluation_engine_score():
    """score() returns EvaluationEvidence."""
    stub = StubEvaluationEngine()
    evidence = await stub.score("cand-1", dimensions=["correctness"])
    assert isinstance(evidence, EvaluationEvidence)
    assert evidence.evaluation_id == "eval-1"


async def test_evaluation_engine_compare():
    """compare() returns EvaluationEvidence with candidates."""
    stub = StubEvaluationEngine()
    evidence = await stub.compare(["cand-1", "cand-2"], dimensions=["quality"])
    assert isinstance(evidence, EvaluationEvidence)
    assert evidence.candidates == ["cand-1", "cand-2"]


async def test_evaluation_engine_get_evidence_missing():
    """get_evidence() returns None for unknown ids."""
    stub = StubEvaluationEngine()
    assert await stub.get_evidence("nonexistent") is None


async def test_health_check_policy_health():
    """check_health() returns HealthCheckResult."""
    stub = StubHealthCheckPolicy()
    result = await stub.check_health()
    assert isinstance(result, HealthCheckResult)
    assert result.healthy is True
    assert result.authenticated is False


async def test_health_check_policy_health_authenticated():
    """check_health(authenticated=True) includes auth flag."""
    stub = StubHealthCheckPolicy()
    result = await stub.check_health(authenticated=True)
    assert result.authenticated is True


async def test_health_check_policy_readiness():
    """check_readiness() returns HealthCheckResult."""
    stub = StubHealthCheckPolicy()
    result = await stub.check_readiness()
    assert isinstance(result, HealthCheckResult)
    assert result.healthy is True


async def test_health_check_policy_requires_auth():
    """requires_auth() returns False for /health and /healthz."""
    stub = StubHealthCheckPolicy()
    assert stub.requires_auth("/health") is False
    assert stub.requires_auth("/healthz") is False
    assert stub.requires_auth("/admin/status") is True


async def test_request_validator_validate_request():
    """validate_request() returns a ValidationReport."""
    stub = StubRequestValidator()
    report = await stub.validate_request("/api/chat", {"message": "hello"})
    assert isinstance(report, ValidationReport)
    assert report.valid is True
    assert report.endpoint == "/api/chat"


async def test_request_validator_validate_response():
    """validate_response() returns a ValidationReport."""
    stub = StubRequestValidator()
    report = await stub.validate_response(
        "/api/chat", {"content": "hi"}, status_code=200
    )
    assert isinstance(report, ValidationReport)
    assert report.valid is True


async def test_request_validator_list_schemas():
    """list_schemas() returns a dict."""
    stub = StubRequestValidator()
    schemas = await stub.list_schemas()
    assert isinstance(schemas, dict)


async def test_request_validator_register_schema():
    """register_schema() accepts schema dicts without error."""
    stub = StubRequestValidator()
    await stub.register_schema(
        "/api/chat",
        request_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
        },
        response_schema={
            "type": "object",
            "properties": {"content": {"type": "string"}},
        },
    )


# ── Dataclass model tests ──────────────────────────────────────────────


class TestCapabilityProfile:
    def test_defaults(self):
        p = CapabilityProfile(model="test", provider="openai")
        assert p.context_length == 0
        assert p.supports_tool_calling is False
        assert p.supports_streaming is False
        assert p.metadata == {}

    def test_full_init(self):
        p = CapabilityProfile(
            model="nemotron",
            provider="nvidia",
            context_length=1_000_000,
            supports_tool_calling=True,
            supports_structured_output=True,
            supports_streaming=True,
            supports_agent_loops=True,
            cost_per_1k_input_tokens=0.01,
            cost_per_1k_output_tokens=0.03,
            metadata={"notes": "MoE"},
        )
        assert p.context_length == 1_000_000
        assert p.supports_agent_loops is True
        assert p.metadata["notes"] == "MoE"


class TestModelBenchmark:
    def test_defaults(self):
        b = ModelBenchmark(
            model="m", task_type="t", score=0.9, latency_ms=100, tokens_used=50
        )
        assert b.quality_notes == ""
        assert b.metadata == {}


class TestCanonicalSource:
    def test_defaults(self):
        s = CanonicalSource(id="s1", uri="file:///a.md", content_hash="abc")
        assert s.format == ""
        assert s.metadata == {}
        assert s.created_at == ""


class TestDerivedIndex:
    def test_defaults(self):
        d = DerivedIndex(id="i1", index_type="vector")
        assert d.source_ids == []
        assert d.status == "stale"
        assert d.built_at == ""


class TestProvenanceRecord:
    def test_required_fields(self):
        p = ProvenanceRecord(derived_id="d1", source_id="s1", source_uri="file:///a")
        assert p.transformation == ""


class TestCompressedProjection:
    def test_defaults(self):
        c = CompressedProjection(id="p1", original_id="o1", compressed_content="...")
        assert c.content_type == ""
        assert c.compression_ratio == 0.0
        assert c.reversible is True


class TestCompressionQuality:
    def test_defaults(self):
        q = CompressionQuality()
        assert q.semantic_preservation == 0.0
        assert q.token_reduction == 0.0
        assert q.information_loss == 0.0


class TestCacheCapability:
    def test_defaults(self):
        c = CacheCapability(provider="anthropic")
        assert c.supported is False
        assert c.max_ttl_seconds == 0
        assert c.prefix_based is False


class TestCacheEvent:
    def test_required_fields(self):
        e = CacheEvent(provider="openai", event_type="hit")
        assert e.tokens_affected == 0
        assert e.latency_saved_ms == 0.0
        assert e.cache_key == ""


class TestAgentInvocation:
    def test_defaults(self):
        inv = AgentInvocation(task="review code")
        assert inv.tools == []
        assert inv.context == {}
        assert inv.timeout_seconds == 0.0
        assert inv.permissions == []


class TestAgentResult:
    def test_defaults(self):
        r = AgentResult(id="r1", status="completed")
        assert r.output == ""
        assert r.structured_output == {}
        assert r.tool_calls_made == 0
        assert r.error is None


class TestContextTransformation:
    def test_defaults(self):
        t = ContextTransformation(id="t1", transformation_type="summarize")
        assert t.input_tokens == 0
        assert t.output_tokens == 0
        assert t.quality_score == 0.0


class TestContextBudget:
    def test_allocation(self):
        b = ContextBudget(total_tokens=4096, system_tokens=512, remaining_tokens=3584)
        assert b.total_tokens == 4096
        assert b.retrieval_tokens == 0
        assert b.history_tokens == 0
        assert b.tool_tokens == 0


class TestCapabilityDescriptor:
    def test_defaults(self):
        d = CapabilityDescriptor(name="search", description="Search the web")
        assert d.backend_type == ""
        assert d.input_schema == {"type": "object", "properties": {}}
        assert d.requires_auth is False
        assert d.rate_limit == 0


class TestCapabilityResult:
    def test_defaults(self):
        r = CapabilityResult(capability_name="search", backend_type="mcp")
        assert r.output is None
        assert r.error is None
        assert r.duration_ms == 0.0
        assert r.provenance == ""


class TestEvaluationCandidate:
    def test_required_fields(self):
        c = EvaluationCandidate(id="c1", model="gpt", output="hi", task="greet")
        assert c.metadata == {}


class TestEvaluationScore:
    def test_defaults(self):
        s = EvaluationScore(candidate_id="c1", dimension="quality", score=4.5)
        assert s.evaluator == ""
        assert s.confidence == 0.0
        assert s.reasoning == ""


class TestEvaluationEvidence:
    def test_defaults(self):
        e = EvaluationEvidence(evaluation_id="e1")
        assert e.candidates == []
        assert e.scores == []
        assert e.verdict == ""
        assert e.consensus_method == ""
        assert e.reproducible is False


class TestHealthDetail:
    def test_defaults(self):
        h = HealthDetail(component="db", healthy=True)
        assert h.message == ""
        assert h.latency_ms == 0.0
        assert h.metadata == {}


class TestHealthCheckResult:
    def test_defaults(self):
        r = HealthCheckResult(healthy=True)
        assert r.status == "ok"
        assert r.details == []
        assert r.authenticated is False
        assert r.checked_at == ""


class TestValidationError:
    def test_required_fields(self):
        e = ValidationError(field="name", message="required")
        assert e.code == ""
        assert e.value is None


class TestValidationReport:
    def test_valid_report(self):
        r = ValidationReport(valid=True)
        assert r.errors == []
        assert r.endpoint == ""
        assert r.http_status == 200

    def test_invalid_report(self):
        errs = [ValidationError(field="name", message="required", code="missing")]
        r = ValidationReport(
            valid=False, errors=errs, endpoint="/api/chat", http_status=422
        )
        assert len(r.errors) == 1
        assert r.http_status == 422
