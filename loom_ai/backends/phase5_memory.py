"""In-memory Phase 5 backend implementations for loom-ai.

All classes use only the standard library -- zero external dependencies.
Suitable for testing, local development, and the 'crush' deployment
profile.  All data is lost on process exit.

Classes
-------
InMemoryEvalSuite              -- dataset-driven evaluation and regression testing
InMemoryGenAITelemetry         -- GenAI-specific observability with semantic spans
InMemoryInferenceRouter        -- capability-aware model routing with adaptive selection
InMemoryAgentLifecycleRuntime  -- agent lifecycle, state, and durable execution
InMemoryAgentMemory            -- persistent, scoped, typed agent memory
InMemoryOutputValidator        -- schema-driven output validation and tool auth
InMemorySecurityGate           -- AI security, authorization, and trust boundaries
InMemoryProgramOptimizer       -- evaluation-driven prompt/model/strategy optimization
"""

from __future__ import annotations

import time
import uuid
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from loom_ai.models_phase5 import (
    AgentEvent,
    AgentLifecycleState,
    AgentMemoryEntry,
    CapabilityPolicy,
    Checkpoint,
    ContentScanResult,
    EvalDataset,
    EvalRunResult,
    ExperimentRun,
    GenAISpanAttributes,
    Handoff,
    InferenceEndpoint,
    MemoryQuery,
    MemoryScope,
    MetricScore,
    ModelCapabilities,
    OptimizationResult,
    OptimizationTarget,
    RedactionPolicy,
    RegressionComparison,
    RoutingDecision,
    SchemaDefinition,
    SecurityEvent,
    TelemetrySummary,
    ToolExecutionResult,
    ToolIntent,
    ValidationResult,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════════
# EvalSuite (#51)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryEvalSuite:
    """Dict-backed dataset-driven evaluation and regression testing."""

    def __init__(self) -> None:
        self._runs: dict[str, EvalRunResult] = {}
        self._datasets: dict[str, EvalDataset] = {}

    async def run(
        self,
        dataset: EvalDataset,
        *,
        model: str | None = None,
        evaluators: list[str] | None = None,
        config: dict | None = None,
    ) -> EvalRunResult:
        self._datasets[dataset.id] = dataset
        run_id = str(uuid.uuid4())
        start = time.monotonic()

        matches = sum(
            1 for case in dataset.cases if case.input == case.expected
        )
        total = len(dataset.cases) or 1
        accuracy = matches / total

        scores = [
            MetricScore(metric="accuracy", value=accuracy),
            MetricScore(metric="case_count", value=float(len(dataset.cases))),
        ]

        result = EvalRunResult(
            run_id=run_id,
            dataset_id=dataset.id,
            scores=scores,
            model=model or "",
            config_version=(config or {}).get("version", ""),
            passed=accuracy >= 0.5,
            duration_ms=(time.monotonic() - start) * 1000,
            created_at=_now_iso(),
        )
        self._runs[run_id] = result
        return result

    async def compare(
        self,
        baseline_run_id: str,
        candidate_run_id: str,
    ) -> RegressionComparison:
        baseline = self._runs.get(baseline_run_id)
        if baseline is None:
            raise ValueError(f"baseline run not found: {baseline_run_id}")
        candidate = self._runs.get(candidate_run_id)
        if candidate is None:
            raise ValueError(f"candidate run not found: {candidate_run_id}")

        regressions: list[str] = []
        improvements: list[str] = []
        unchanged: list[str] = []

        if baseline and candidate:
            base_scores = {s.metric: s.value for s in baseline.scores}
            cand_scores = {s.metric: s.value for s in candidate.scores}
            for metric in sorted(set(base_scores) | set(cand_scores)):
                bv = base_scores.get(metric, 0.0)
                cv = cand_scores.get(metric, 0.0)
                if cv < bv:
                    regressions.append(metric)
                elif cv > bv:
                    improvements.append(metric)
                else:
                    unchanged.append(metric)

        return RegressionComparison(
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
            regressions=regressions,
            improvements=improvements,
            unchanged=unchanged,
            verdict="regression" if regressions else "pass",
        )

    async def get_run(self, run_id: str) -> EvalRunResult | None:
        return self._runs.get(run_id)

    async def list_datasets(self) -> list[EvalDataset]:
        return list(self._datasets.values())


# ══════════════════════════════════════════════════════════════════════════
# GenAITelemetry (#52)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryGenAITelemetry:
    """Dict-backed GenAI-specific observability with semantic spans."""

    def __init__(self) -> None:
        self._spans: dict[str, tuple[float, GenAISpanAttributes]] = {}
        self._redaction_policy: RedactionPolicy | None = None

    async def record_span(
        self,
        span_id: str,
        attributes: GenAISpanAttributes,
    ) -> None:
        self._spans[span_id] = (time.time(), attributes)

    async def set_redaction_policy(self, policy: RedactionPolicy) -> None:
        self._redaction_policy = policy

    async def summarize(
        self,
        *,
        window_minutes: int = 60,
    ) -> TelemetrySummary:
        cutoff = time.time() - (window_minutes * 60)
        window_spans = [
            attrs for ts, attrs in self._spans.values() if ts >= cutoff
        ]

        if not window_spans:
            return TelemetrySummary()

        total_tokens = sum(s.total_tokens for s in window_spans)
        total_cost = sum(s.cost_usd for s in window_spans)
        latencies = [s.latency_ms for s in window_spans]
        error_count = sum(1 for s in window_spans if s.error)

        by_model: dict[str, int] = {}
        by_operation: dict[str, int] = {}
        for s in window_spans:
            by_model[s.model] = by_model.get(s.model, 0) + 1
            by_operation[s.operation] = by_operation.get(s.operation, 0) + 1

        return TelemetrySummary(
            total_spans=len(window_spans),
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
            avg_latency_ms=sum(latencies) / len(latencies),
            error_count=error_count,
            by_model=by_model,
            by_operation=by_operation,
        )

    async def export_spans(
        self,
        *,
        limit: int = 100,
        operation: str | None = None,
    ) -> list[dict]:
        entries = sorted(
            self._spans.items(), key=lambda x: x[1][0], reverse=True,
        )
        results: list[dict] = []
        for span_id, (ts, attrs) in entries:
            if operation and attrs.operation != operation:
                continue
            d = asdict(attrs)
            d["span_id"] = span_id
            d["recorded_at"] = datetime.fromtimestamp(
                ts, tz=timezone.utc,
            ).isoformat()
            results.append(d)
            if len(results) >= limit:
                break
        return results


# ══════════════════════════════════════════════════════════════════════════
# InferenceRouter (#53)
# ══════════════════════════════════════════════════════════════════════════


_CAPABILITY_BOOL_FIELDS = (
    "streaming",
    "structured_output",
    "tool_calling",
    "vision",
    "embeddings",
)


class InMemoryInferenceRouter:
    """Dict-backed capability-aware model routing with adaptive selection."""

    def __init__(self) -> None:
        self._endpoints: dict[str, InferenceEndpoint] = {}
        self._capabilities: dict[str, ModelCapabilities] = {}
        self._decisions: list[RoutingDecision] = []
        self._outcomes: dict[str, list[tuple[bool, float]]] = {}

    async def select(
        self,
        *,
        capabilities: ModelCapabilities | None = None,
        preferred_model: str | None = None,
        budget_usd: float | None = None,
    ) -> InferenceEndpoint:
        _ = budget_usd
        candidates = [ep for ep in self._endpoints.values() if ep.healthy]

        if preferred_model:
            preferred = [
                ep for ep in candidates if ep.model_id == preferred_model
            ]
            if preferred:
                candidates = preferred

        if capabilities:
            filtered = []
            for ep in candidates:
                caps = self._capabilities.get(ep.id)
                if caps is None:
                    filtered.append(ep)
                    continue
                match = True
                for f in _CAPABILITY_BOOL_FIELDS:
                    required = getattr(capabilities, f, None)
                    if not required:
                        continue
                    actual = getattr(caps, f, None)
                    if actual is None or actual < required:
                        match = False
                        break
                if match:
                    filtered.append(ep)
            candidates = filtered

        if not candidates:
            raise ValueError("no matching endpoint available")

        selected = min(candidates, key=lambda ep: ep.latency_ms)

        self._decisions.append(
            RoutingDecision(
                selected_endpoint=selected.id,
                model=selected.model_id,
                reason="lowest latency among matching candidates",
                fallback_used=False,
                candidates_considered=len(candidates),
                latency_ms=selected.latency_ms,
            ),
        )
        return selected

    async def register_endpoint(self, endpoint: InferenceEndpoint) -> None:
        self._endpoints[endpoint.id] = endpoint
        caps_data = endpoint.metadata.get("capabilities")
        if isinstance(caps_data, ModelCapabilities):
            self._capabilities[endpoint.id] = caps_data
        elif isinstance(caps_data, dict):
            self._capabilities[endpoint.id] = ModelCapabilities(**caps_data)

    async def record_outcome(
        self,
        endpoint_id: str,
        *,
        success: bool,
        latency_ms: float,
        tokens_used: int = 0,
    ) -> None:
        self._outcomes.setdefault(endpoint_id, []).append(
            (success, latency_ms),
        )
        ep = self._endpoints.get(endpoint_id)
        if ep:
            outcomes = self._outcomes[endpoint_id]
            ep.latency_ms = sum(lat for _, lat in outcomes) / len(outcomes)
            # Mark unhealthy after 5+ failures in the last 10 outcomes
            recent_failures = sum(
                1 for ok, _ in outcomes[-10:] if not ok
            )
            ep.healthy = recent_failures < 5

    async def get_decision_log(
        self, *, limit: int = 20,
    ) -> list[RoutingDecision]:
        return list(reversed(self._decisions[-limit:]))

    async def list_endpoints(
        self, *, healthy_only: bool = False,
    ) -> list[InferenceEndpoint]:
        endpoints = list(self._endpoints.values())
        if healthy_only:
            endpoints = [ep for ep in endpoints if ep.healthy]
        return endpoints


# ══════════════════════════════════════════════════════════════════════════
# AgentLifecycleRuntime (#54)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryAgentLifecycleRuntime:
    """Dict-backed agent lifecycle with durable execution semantics."""

    def __init__(self) -> None:
        self._states: dict[str, AgentLifecycleState] = {}
        self._checkpoints: dict[str, Checkpoint] = {}
        self._events: dict[str, list[AgentEvent]] = {}
        self._configs: dict[str, dict] = {}

    def _emit(self, run_id: str, event_type: str, detail: str = "") -> None:
        state = self._states.get(run_id)
        event = AgentEvent(
            event_type=event_type,
            agent_id=state.agent_id if state else "",
            step=state.step if state else "",
            detail=detail,
            created_at=_now_iso(),
        )
        self._events.setdefault(run_id, []).append(event)

    async def start(
        self,
        agent_id: str,
        *,
        initial_state: AgentLifecycleState | None = None,
        config: dict | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        if initial_state is not None:
            state = deepcopy(initial_state)
        else:
            state = AgentLifecycleState(
                agent_id=agent_id,
                step="init",
            )
        state.status = "running"
        if not state.created_at:
            state.created_at = _now_iso()
        self._states[run_id] = state
        if config:
            self._configs[run_id] = config
        self._emit(run_id, "started")
        return run_id

    async def checkpoint(self, run_id: str) -> Checkpoint:
        state = self._states.get(run_id)
        if state is None:
            raise ValueError(f"unknown run: {run_id}")
        cp = Checkpoint(
            id=str(uuid.uuid4()),
            agent_id=state.agent_id,
            state=deepcopy(state),
            step=state.step,
            created_at=_now_iso(),
            metadata=dict(self._configs.get(run_id, {})),
        )
        self._checkpoints[cp.id] = cp
        self._emit(run_id, "checkpointed", f"checkpoint={cp.id}")
        return cp

    async def resume(self, checkpoint_id: str) -> str:
        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            raise ValueError(f"unknown checkpoint: {checkpoint_id}")
        run_id = str(uuid.uuid4())
        state = deepcopy(cp.state) if cp.state else AgentLifecycleState(
            agent_id=cp.agent_id, step=cp.step,
        )
        state.status = "running"
        self._states[run_id] = state
        if cp.metadata:
            self._configs[run_id] = dict(cp.metadata)
        self._emit(run_id, "resumed", f"from checkpoint={checkpoint_id}")
        return run_id

    async def handoff(
        self,
        run_id: str,
        to_agent: str,
        *,
        reason: str = "",
        context: dict | None = None,
    ) -> Handoff:
        state = self._states.get(run_id)
        if state is None:
            raise ValueError(f"unknown run: {run_id}")
        state.status = "handed_off"
        handoff = Handoff(
            id=str(uuid.uuid4()),
            from_agent=state.agent_id,
            to_agent=to_agent,
            reason=reason,
            context=context or {},
            created_at=_now_iso(),
        )
        self._emit(run_id, "handoff", f"to={to_agent} reason={reason}")
        return handoff

    async def interrupt(self, run_id: str, *, reason: str = "") -> None:
        state = self._states.get(run_id)
        if state is None:
            raise ValueError(f"unknown run: {run_id}")
        state.status = "interrupted"
        self._emit(run_id, "interrupted", reason)

    async def get_state(self, run_id: str) -> AgentLifecycleState | None:
        return self._states.get(run_id)

    async def get_events(
        self, run_id: str, *, limit: int = 50,
    ) -> list[AgentEvent]:
        events = self._events.get(run_id, [])
        return events[-limit:]


# ══════════════════════════════════════════════════════════════════════════
# AgentMemory (#55)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryAgentMemory:
    """Dict-backed persistent, scoped, typed agent memory."""

    def __init__(self) -> None:
        self._entries: dict[str, AgentMemoryEntry] = {}
        self._scopes: dict[str, MemoryScope] = {}

    async def store(self, entry: AgentMemoryEntry) -> str:
        stored = deepcopy(entry)
        entry_id = stored.id or str(uuid.uuid4())
        stored.id = entry_id
        if not stored.created_at:
            stored.created_at = _now_iso()
        self._entries[entry_id] = stored

        if entry.scope not in self._scopes:
            self._scopes[entry.scope] = MemoryScope(
                scope=entry.scope, agent_id=entry.agent_id,
            )
        return entry_id

    @staticmethod
    def _matches_query(
        entry: AgentMemoryEntry, query: MemoryQuery,
    ) -> bool:
        if entry.superseded_by is not None:
            return False
        if query.agent_id and entry.agent_id != query.agent_id:
            return False
        if query.scope and entry.scope != query.scope:
            return False
        if query.memory_type and entry.memory_type != query.memory_type:
            return False
        if entry.confidence < query.min_confidence:
            return False
        if query.query and query.query.lower() not in entry.content.lower():
            return False
        return True

    async def recall(self, query: MemoryQuery) -> list[AgentMemoryEntry]:
        results: list[AgentMemoryEntry] = []
        for entry in self._entries.values():
            if not self._matches_query(entry, query):
                continue
            results.append(entry)
            if len(results) >= query.limit:
                break
        return results

    async def supersede(
        self,
        entry_id: str,
        replacement: AgentMemoryEntry,
    ) -> str:
        old = self._entries.get(entry_id)
        if old:
            old.superseded_by = replacement.id or str(uuid.uuid4())
            old.updated_at = _now_iso()
        new_id = await self.store(replacement)
        return new_id

    async def forget(self, entry_id: str) -> bool:
        return self._entries.pop(entry_id, None) is not None

    async def list_scopes(self) -> list[MemoryScope]:
        return list(self._scopes.values())

    async def count(
        self,
        *,
        scope: str | None = None,
        memory_type: str | None = None,
    ) -> int:
        total = 0
        for entry in self._entries.values():
            if scope and entry.scope != scope:
                continue
            if memory_type and entry.memory_type != memory_type:
                continue
            total += 1
        return total


# ══════════════════════════════════════════════════════════════════════════
# OutputValidator (#56)
# ══════════════════════════════════════════════════════════════════════════


_JSON_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}

_TYPE_DEFAULTS: dict[str, Any] = {
    "string": "",
    "integer": 0,
    "number": 0.0,
    "boolean": False,
    "array": [],
    "object": {},
}


class InMemoryOutputValidator:
    """Schema-driven output validation with repair and tool authorization."""

    def __init__(self) -> None:
        self._schemas: dict[str, SchemaDefinition] = {}

    @staticmethod
    def _check_schema(output: Any, schema: dict) -> list[str]:
        """Basic JSON Schema validation: required fields and property types."""
        errors: list[str] = []

        if not isinstance(output, dict):
            if schema.get("type") == "object":
                errors.append(
                    f"expected object, got {type(output).__name__}",
                )
            return errors

        for field_name in schema.get("required", []):
            if field_name not in output:
                errors.append(f"missing required field: {field_name}")

        for prop_name, prop_schema in schema.get("properties", {}).items():
            if prop_name not in output:
                continue
            expected_type = prop_schema.get("type")
            if expected_type and expected_type in _JSON_TYPE_MAP:
                py_type = _JSON_TYPE_MAP[expected_type]
                if not isinstance(output[prop_name], py_type):
                    errors.append(
                        f"field '{prop_name}': expected {expected_type}, "
                        f"got {type(output[prop_name]).__name__}",
                    )
        return errors

    async def validate(
        self,
        output: Any,
        schema: SchemaDefinition,
    ) -> ValidationResult:
        self._schemas.setdefault(schema.id, schema)
        errors = self._check_schema(output, schema.schema)
        return ValidationResult(valid=not errors, errors=errors)

    async def repair(
        self,
        output: Any,
        schema: SchemaDefinition,
        *,
        max_attempts: int = 3,
    ) -> tuple[Any, ValidationResult]:
        self._schemas.setdefault(schema.id, schema)

        for attempt in range(max_attempts):
            errors = self._check_schema(output, schema.schema)
            if not errors:
                return output, ValidationResult(
                    valid=True,
                    repaired=attempt > 0,
                    repair_detail=(
                        f"repaired after {attempt} attempts"
                        if attempt > 0
                        else ""
                    ),
                )

            if not isinstance(output, dict):
                output = {}

            for field_name in schema.schema.get("required", []):
                if field_name not in output:
                    prop_type = (
                        schema.schema
                        .get("properties", {})
                        .get(field_name, {})
                        .get("type", "string")
                    )
                    output[field_name] = _TYPE_DEFAULTS.get(prop_type, "")

        errors = self._check_schema(output, schema.schema)
        return output, ValidationResult(
            valid=not errors,
            errors=errors,
            repaired=True,
            repair_detail=f"repair attempted {max_attempts} times",
        )

    async def authorize_tool(
        self,
        intent: ToolIntent,
        policy: CapabilityPolicy,
    ) -> ToolExecutionResult:
        if intent.tool_name in policy.denied_tools:
            return ToolExecutionResult(
                request_id=intent.request_id,
                tool_name=intent.tool_name,
                authorized=False,
                error=f"tool '{intent.tool_name}' is denied by policy",
            )
        if policy.allowed_tools and intent.tool_name not in policy.allowed_tools:
            return ToolExecutionResult(
                request_id=intent.request_id,
                tool_name=intent.tool_name,
                authorized=False,
                error=f"tool '{intent.tool_name}' is not in allowed list",
            )
        return ToolExecutionResult(
            request_id=intent.request_id,
            tool_name=intent.tool_name,
            output={"status": "executed", "arguments": intent.arguments},
            authorized=True,
        )

    async def list_schemas(self) -> list[SchemaDefinition]:
        return list(self._schemas.values())


# ══════════════════════════════════════════════════════════════════════════
# SecurityGate (#57)
# ══════════════════════════════════════════════════════════════════════════


_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard your instructions",
    "system prompt:",
    "you are now",
)


class InMemorySecurityGate:
    """Dict-backed security enforcement for AI operations."""

    def __init__(self) -> None:
        self._policies: dict[str, CapabilityPolicy] = {}
        self._events: list[SecurityEvent] = []

    async def check_policy(
        self,
        agent_id: str,
        action: str,
        *,
        resource: str | None = None,
    ) -> bool:
        policy = self._policies.get(agent_id)
        if policy is None:
            return True

        if action in policy.denied_tools:
            return False
        if policy.allowed_tools and action not in policy.allowed_tools:
            return False
        if resource and policy.allowed_resources:
            if resource not in policy.allowed_resources:
                return False
        return True

    async def scan_content(
        self,
        content: str,
        *,
        context: str = "",
    ) -> ContentScanResult:
        threats: list[str] = []
        lower = content.lower()
        for pattern in _INJECTION_PATTERNS:
            if pattern in lower:
                threats.append(f"potential prompt injection: '{pattern}'")

        return ContentScanResult(
            safe=not threats,
            threats=threats,
            detail=f"scanned {len(content)} chars",
            scanned_at=_now_iso(),
        )

    async def set_policy(self, policy: CapabilityPolicy) -> None:
        self._policies[policy.agent_id] = policy

    async def get_policy(self, agent_id: str) -> CapabilityPolicy | None:
        return self._policies.get(agent_id)

    async def record_event(self, event: SecurityEvent) -> None:
        if not event.created_at:
            event.created_at = _now_iso()
        self._events.append(event)

    async def get_events(
        self,
        *,
        agent_id: str | None = None,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[SecurityEvent]:
        results: list[SecurityEvent] = []
        for event in reversed(self._events):
            if agent_id and event.agent_id != agent_id:
                continue
            if severity and event.severity != severity:
                continue
            results.append(event)
            if len(results) >= limit:
                break
        return results


# ══════════════════════════════════════════════════════════════════════════
# ProgramOptimizer (#58)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryProgramOptimizer:
    """Dict-backed evaluation-driven prompt/model/strategy optimization."""

    def __init__(self) -> None:
        self._targets: dict[str, OptimizationTarget] = {}
        self._experiments: dict[str, list[ExperimentRun]] = {}

    async def register_target(self, target: OptimizationTarget) -> None:
        self._targets[target.id] = target
        self._experiments.setdefault(target.id, [])

    async def run_experiment(
        self,
        target_id: str,
        variant: str,
        *,
        eval_dataset_id: str | None = None,
        config: dict | None = None,
    ) -> ExperimentRun:
        # Deterministic-ish score so different variants produce different results
        score = 0.5 + (hash(variant) % 50) / 100.0
        exp = ExperimentRun(
            id=str(uuid.uuid4()),
            target_id=target_id,
            variant=variant,
            objective_scores={"quality": score},
            eval_run_id=eval_dataset_id or "",
            created_at=_now_iso(),
            metadata=config or {},
        )
        self._experiments.setdefault(target_id, []).append(exp)
        return exp

    async def optimize(
        self,
        target_id: str,
        *,
        max_iterations: int = 10,
        objective: str = "quality",
    ) -> OptimizationResult:
        target = self._targets.get(target_id)
        if target is None:
            raise ValueError(f"unknown target: {target_id}")

        best_variant = target.current_value
        best_score = 0.0

        for i in range(max_iterations):
            variant = f"{target.current_value}_v{i}"
            exp = await self.run_experiment(target_id, variant)
            score = exp.objective_scores.get(objective, 0.0)
            if score > best_score:
                best_score = score
                best_variant = variant

        baseline = 0.5
        improvement = (best_score - baseline) / baseline * 100.0

        return OptimizationResult(
            target_id=target_id,
            best_variant=best_variant,
            best_scores={objective: best_score},
            total_experiments=max_iterations,
            improvement_pct=improvement,
            converged=True,
        )

    async def get_experiments(
        self,
        target_id: str,
        *,
        limit: int = 20,
    ) -> list[ExperimentRun]:
        exps = self._experiments.get(target_id, [])
        return exps[-limit:]
