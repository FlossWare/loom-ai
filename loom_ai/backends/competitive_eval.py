"""In-memory backends for Phase 8 (Competitive Evaluation) protocols.

Classes
-------
InMemoryEvalCapabilityRegistry   -- capability registry and discovery
InMemoryCapabilitySelector       -- capability health, fallback, and selection
InMemoryInteractionEvaluator     -- multi-agent interaction evaluation
InMemorySkillEstimator           -- Bayesian skill estimation with Beta posteriors
InMemoryEvaluationEnvironment    -- deterministic multi-agent evaluation environment
InMemoryTournamentRunner         -- multi-model competitive tournament
InMemoryInferenceOptimizer       -- adaptive inference parameter optimization
InMemoryOutputNormalizer         -- output normalization and semantic comparison
InMemoryConsensusStrategy        -- pluggable consensus/voting strategies
"""

from __future__ import annotations

import math
import random
import re
import uuid
from collections import Counter
from dataclasses import replace

from loom_ai.models_phase8 import (
    CapabilityHealthState,
    CapabilityProvider,
    ComparisonResult,
    ConsensusCandidate,
    ConsensusDecision,
    EnvironmentAction,
    EnvironmentConfig,
    EnvironmentState,
    EvalCapabilityDescriptor,
    EvalEnvironmentObservation,
    InferenceParameters,
    InteractionOutcome,
    InteractionTrajectory,
    JudgeVerdict,
    NormalizationStep,
    NormalizedOutput,
    PairwiseOutcome,
    ParticipantScore,
    SelectionCriteria,
    SkillEstimate,
    TournamentCandidate,
    TournamentResult,
)

# ══════════════════════════════════════════════════════════════════════════
# EvalCapabilityRegistry (#70)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryEvalCapabilityRegistry:
    """Dict-backed capability registry and provider store."""

    def __init__(self) -> None:
        self._capabilities: dict[str, EvalCapabilityDescriptor] = {}
        self._providers: dict[str, list[CapabilityProvider]] = {}

    async def register_capability(self, capability: EvalCapabilityDescriptor) -> None:
        self._capabilities[capability.id] = capability
        self._providers.setdefault(capability.id, [])

    async def deregister_capability(self, capability_id: str) -> bool:
        if capability_id in self._capabilities:
            del self._capabilities[capability_id]
            self._providers.pop(capability_id, None)
            return True
        return False

    async def discover(
        self, *, capability_type: str | None = None
    ) -> list[EvalCapabilityDescriptor]:
        caps = list(self._capabilities.values())
        if capability_type is not None:
            caps = [c for c in caps if c.capability_type == capability_type]
        return caps

    async def get_capability(
        self, capability_id: str
    ) -> EvalCapabilityDescriptor | None:
        return self._capabilities.get(capability_id)

    async def register_provider(
        self, capability_id: str, provider: CapabilityProvider
    ) -> None:
        self._providers.setdefault(capability_id, []).append(provider)

    async def list_providers(self, capability_id: str) -> list[CapabilityProvider]:
        return list(self._providers.get(capability_id, []))


# ══════════════════════════════════════════════════════════════════════════
# CapabilitySelector (#71)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryCapabilitySelector:
    """Selects providers using health tracking and criteria filtering."""

    def __init__(self, registry: InMemoryEvalCapabilityRegistry) -> None:
        self._registry = registry
        self._health: dict[tuple[str, str], CapabilityHealthState] = {}
        self._outcomes: dict[tuple[str, str], list[tuple[bool, float]]] = {}

    async def select_backend(
        self,
        capability_id: str,
        *,
        criteria: SelectionCriteria | None = None,
    ) -> CapabilityProvider:
        chain = await self.fallback_chain(capability_id)
        if criteria is not None:
            filtered: list[CapabilityProvider] = []
            for p in chain:
                if p.id in criteria.exclude_providers:
                    continue
                if (
                    criteria.max_latency_ms is not None
                    and p.avg_latency_ms > criteria.max_latency_ms
                ):
                    continue
                if (
                    criteria.max_cost_per_call is not None
                    and p.cost_per_call > criteria.max_cost_per_call
                ):
                    continue
                filtered.append(p)
            chain = filtered
        if not chain:
            raise RuntimeError(f"No provider available for capability {capability_id}")
        return chain[0]

    async def health_state(
        self, capability_id: str, provider_id: str
    ) -> CapabilityHealthState:
        key = (capability_id, provider_id)
        if key in self._health:
            return self._health[key]
        return CapabilityHealthState(
            provider_id=provider_id,
            capability_id=capability_id,
            state="healthy",
        )

    async def report_outcome(
        self,
        capability_id: str,
        provider_id: str,
        *,
        success: bool,
        latency_ms: float,
    ) -> None:
        key = (capability_id, provider_id)
        self._outcomes.setdefault(key, []).append((success, latency_ms))
        outcomes = self._outcomes[key]
        total = len(outcomes)
        failures = sum(1 for ok, _ in outcomes if not ok)
        avg_latency = sum(lat for _, lat in outcomes) / total
        error_rate = failures / total

        if error_rate > 0.5:
            state = "unavailable"
        elif error_rate > 0.2:
            state = "degraded"
        else:
            state = "healthy"

        self._health[key] = CapabilityHealthState(
            provider_id=provider_id,
            capability_id=capability_id,
            state=state,
            latency_ms=avg_latency,
            error_rate=error_rate,
        )

    async def fallback_chain(self, capability_id: str) -> list[CapabilityProvider]:
        providers = await self._registry.list_providers(capability_id)
        scored: list[tuple[int, CapabilityProvider]] = []
        for p in providers:
            key = (capability_id, p.id)
            health = self._health.get(key)
            if health and health.state == "unavailable":
                continue
            penalty = 1 if health and health.state == "degraded" else 0
            scored.append((p.priority - penalty, p))
        scored.sort(key=lambda x: -x[0])
        return [p for _, p in scored]


# ══════════════════════════════════════════════════════════════════════════
# InteractionEvaluator (#72)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryInteractionEvaluator:
    """Scores multi-agent trajectories by participant engagement."""

    async def evaluate_interaction(
        self, trajectory: InteractionTrajectory
    ) -> InteractionOutcome:
        scores = await self.compare_participants(trajectory)
        return InteractionOutcome(
            trajectory_id=trajectory.id,
            participant_scores=scores,
            behavioral_metrics={
                "total_steps": len(trajectory.steps),
                "participant_count": len(trajectory.participants),
            },
            summary=(
                f"Evaluated {len(trajectory.participants)} participants "
                f"over {len(trajectory.steps)} steps"
            ),
        )

    async def compare_participants(
        self, trajectory: InteractionTrajectory
    ) -> list[ParticipantScore]:
        participation: Counter[str] = Counter()
        for step in trajectory.steps:
            agent = step.get("agent_id", "")
            if agent:
                participation[agent] += 1

        total_steps = max(len(trajectory.steps), 1)
        scores: list[ParticipantScore] = []
        for p in trajectory.participants:
            count = participation.get(p.id, 0)
            engagement = count / total_steps
            scores.append(
                ParticipantScore(
                    participant_id=p.id,
                    scores={"engagement": engagement, "steps": count},
                    reasoning=f"Participated in {count}/{total_steps} steps",
                )
            )

        scores.sort(key=lambda s: s.scores.get("engagement", 0), reverse=True)
        return [replace(s, rank=i + 1) for i, s in enumerate(scores)]


# ══════════════════════════════════════════════════════════════════════════
# SkillEstimator (#73)
# ══════════════════════════════════════════════════════════════════════════


class InMemorySkillEstimator:
    """Beta-distribution posteriors updated on pairwise outcomes."""

    def __init__(self) -> None:
        self._posteriors: dict[tuple[str, str], tuple[float, float]] = {}

    def _key(self, agent_id: str, capability: str | None) -> tuple[str, str]:
        return (agent_id, capability or "_global")

    def _get_ab(self, agent_id: str, capability: str | None) -> tuple[float, float]:
        return self._posteriors.get(self._key(agent_id, capability), (1.0, 1.0))

    def _build_estimate(self, agent_id: str, capability: str | None) -> SkillEstimate:
        alpha, beta_param = self._get_ab(agent_id, capability)
        total = alpha + beta_param
        mean = alpha / total
        variance = (alpha * beta_param) / (total * total * (total + 1))
        sd = math.sqrt(variance)
        return SkillEstimate(
            agent_id=agent_id,
            capability=capability or "_global",
            mean=mean,
            variance=variance,
            lower_bound=max(0.0, mean - 2 * sd),
            upper_bound=min(1.0, mean + 2 * sd),
            n_observations=int(alpha + beta_param - 2),
            distribution_params={"alpha": alpha, "beta": beta_param},
        )

    async def estimate(
        self, agent_id: str, *, capability: str | None = None
    ) -> SkillEstimate:
        return self._build_estimate(agent_id, capability)

    async def record_outcome(self, outcome: PairwiseOutcome) -> None:
        cap = outcome.capability or None
        wk = self._key(outcome.winner_id, cap)
        lk = self._key(outcome.loser_id, cap)

        if wk == lk:
            return

        wa, wb = self._posteriors.get(wk, (1.0, 1.0))
        la, lb = self._posteriors.get(lk, (1.0, 1.0))

        if outcome.draw:
            wa += 0.5
            wb += 0.5
            la += 0.5
            lb += 0.5
        else:
            wa += 1.0
            lb += 1.0

        self._posteriors[wk] = (wa, wb)
        self._posteriors[lk] = (la, lb)

    async def rankings(
        self, *, capability: str | None = None, limit: int = 10
    ) -> list[SkillEstimate]:
        target_cap = capability or "_global"
        agents = {k[0] for k in self._posteriors if k[1] == target_cap}
        estimates = [self._build_estimate(a, capability) for a in agents]
        estimates.sort(key=lambda e: e.mean, reverse=True)
        return estimates[:limit]

    async def update_from_tournament(self, results: list[PairwiseOutcome]) -> None:
        for outcome in results:
            await self.record_outcome(outcome)


# ══════════════════════════════════════════════════════════════════════════
# EvaluationEnvironment (#74)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryEvaluationEnvironment:
    """State-machine environment with seed-based deterministic reset."""

    def __init__(self) -> None:
        self._state: EnvironmentState = EnvironmentState(environment_id="")
        self._trajectory: list[dict] = []
        self._rng: random.Random = random.Random()
        self._max_steps: int = 100

    async def reset(
        self,
        *,
        seed: int | None = None,
        config: EnvironmentConfig | None = None,
    ) -> EnvironmentState:
        self._rng = random.Random(seed)
        self._max_steps = (
            config.parameters.get("max_steps", 100)
            if config and config.parameters is not None
            else 100
        )
        self._trajectory = []
        self._state = EnvironmentState(
            environment_id=str(uuid.uuid4()),
            step_number=0,
            public_state={"seed": seed},
            available_actions=["act", "observe", "wait"],
            terminal=False,
        )
        return self._state

    async def step(
        self, agent_id: str, action: EnvironmentAction
    ) -> EvalEnvironmentObservation:
        next_step = self._state.step_number + 1
        reward = self._rng.uniform(-1.0, 1.0)
        new_public = dict(self._state.public_state)
        new_public[f"last_action_{agent_id}"] = action.action_type
        new_public["step"] = next_step
        terminal = next_step >= self._max_steps
        available = [] if terminal else list(self._state.available_actions)
        self._state = replace(
            self._state,
            step_number=next_step,
            public_state=new_public,
            terminal=terminal,
            available_actions=available,
        )

        self._trajectory.append(
            {
                "step": self._state.step_number,
                "agent_id": agent_id,
                "action_type": action.action_type,
                "parameters": action.parameters,
                "reward": reward,
            }
        )

        return EvalEnvironmentObservation(
            state=self._state,
            reward=reward,
            info={"agent_id": agent_id},
        )

    async def get_state(self, *, agent_id: str | None = None) -> EnvironmentState:
        if agent_id is not None:
            public = {
                k: v
                for k, v in self._state.public_state.items()
                if not k.startswith("last_action_") or k == f"last_action_{agent_id}"
            }
            filtered: EnvironmentState = replace(self._state, public_state=public)
            return filtered
        return self._state

    async def is_terminal(self) -> bool:
        return self._state.terminal

    async def export_trajectory(self) -> list[dict]:
        return list(self._trajectory)


# ══════════════════════════════════════════════════════════════════════════
# TournamentRunner (#75)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryTournamentRunner:
    """Fan-out tournament that generates candidates and judges by comparison."""

    def __init__(self) -> None:
        self._results: dict[str, TournamentResult] = {}

    async def run_tournament(
        self,
        task: str,
        *,
        models: list[str],
        rounds: int = 1,
    ) -> TournamentResult:
        candidates: list[TournamentCandidate] = []
        for model in models:
            for r in range(rounds):
                candidates.append(
                    TournamentCandidate(
                        id=str(uuid.uuid4()),
                        model=model,
                        content=f"[{model}] response to: {task} (round {r + 1})",
                    )
                )

        verdicts = await self.judge(candidates, task=task)
        winner_id = verdicts[0].candidate_id if verdicts else None

        result = TournamentResult(
            task=task,
            candidates=candidates,
            verdicts=verdicts,
            winner_id=winner_id,
            rounds_completed=rounds,
        )
        self._results[task] = result
        return result

    async def judge(
        self,
        candidates: list[TournamentCandidate],
        *,
        _task: str,
    ) -> list[JudgeVerdict]:
        if not candidates:
            return []

        verdicts: list[JudgeVerdict] = []
        max_len = max(len(c.content) for c in candidates)
        for c in candidates:
            score = len(c.content) / max_len if max_len else 0.0
            verdicts.append(
                JudgeVerdict(
                    candidate_id=c.id,
                    score=score,
                    reasoning="Scored by content length ratio",
                    judge_model="in-memory",
                )
            )

        verdicts.sort(key=lambda v: v.score, reverse=True)
        return [replace(v, rank=i + 1) for i, v in enumerate(verdicts)]


# ══════════════════════════════════════════════════════════════════════════
# InferenceOptimizer (#76)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryInferenceOptimizer:
    """Parameter-reward history; optimize returns highest average reward."""

    def __init__(self) -> None:
        self._history: dict[str, list[tuple[InferenceParameters, float]]] = {}
        self._model_params: dict[str, InferenceParameters] = {}

    async def optimize(
        self,
        task_context: str,
        *,
        model: str | None = None,
    ) -> InferenceParameters:
        history = self._history.get(task_context, [])
        if not history:
            return InferenceParameters(model=model or "")

        groups: dict[str, list[float]] = {}
        param_map: dict[str, InferenceParameters] = {}
        for params, reward in history:
            sig = (
                f"t={params.temperature},p={params.top_p},fp={params.frequency_penalty}"
            )
            groups.setdefault(sig, []).append(reward)
            param_map[sig] = params

        best_sig = max(groups, key=lambda s: sum(groups[s]) / len(groups[s]))
        best = param_map[best_sig]
        if model:
            best = replace(best, model=model)
        return best

    async def record_feedback(
        self,
        parameters: InferenceParameters,
        *,
        reward: float,
        task_context: str,
    ) -> None:
        self._history.setdefault(task_context, []).append((parameters, reward))
        if parameters.model:
            self._model_params[parameters.model] = parameters

    async def effective_parameters(self, model: str) -> InferenceParameters:
        return self._model_params.get(model, InferenceParameters(model=model))


# ══════════════════════════════════════════════════════════════════════════
# OutputNormalizer (#77)
# ══════════════════════════════════════════════════════════════════════════

_MARKDOWN_RE = re.compile(r"[#*_`>~\[\]()!|]")


class InMemoryOutputNormalizer:
    """Normalize by strip/lowercase/remove-markdown; compare by character overlap."""

    _STEPS: dict[str, object] = {
        "strip_whitespace": staticmethod(lambda t: " ".join(t.split())),
        "lowercase": staticmethod(lambda t: t.lower()),
        "remove_markdown": staticmethod(lambda t: _MARKDOWN_RE.sub("", t)),
    }

    async def normalize(
        self,
        output: str,
        *,
        steps: list[str] | None = None,
        model: str = "",
    ) -> NormalizedOutput:
        step_names = steps if steps is not None else list(self._STEPS)
        applied: list[NormalizationStep] = []
        text = output
        for name in step_names:
            fn = self._STEPS.get(name)
            if fn is not None:
                text = fn(text)  # type: ignore[operator]
                applied.append(NormalizationStep(name=name))
        return NormalizedOutput(
            original=output,
            normalized=text,
            steps_applied=applied,
            model=model,
        )

    async def compare(self, outputs: list[NormalizedOutput]) -> ComparisonResult:
        n = len(outputs)
        matrix: list[list[float]] = []
        for i in range(n):
            row: list[float] = []
            for j in range(n):
                if i == j:
                    row.append(1.0)
                else:
                    a_chars = set(outputs[i].normalized)
                    b_chars = set(outputs[j].normalized)
                    union = a_chars | b_chars
                    overlap = len(a_chars & b_chars) / len(union) if union else 1.0
                    row.append(round(overlap, 4))
            matrix.append(row)
        return ComparisonResult(
            similarity_matrix=matrix,
            summary=f"Compared {n} outputs by character overlap ratio",
        )

    async def list_steps(self) -> list[str]:
        return list(self._STEPS)


# ══════════════════════════════════════════════════════════════════════════
# ConsensusStrategy (#78)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryConsensusStrategy:
    """Majority vote, weighted vote, and judge consensus strategies."""

    _STRATEGIES = ["majority_vote", "weighted_vote", "judge"]

    async def combine(
        self,
        candidates: list[ConsensusCandidate],
        *,
        strategy: str = "majority_vote",
    ) -> ConsensusDecision:
        if not candidates:
            return ConsensusDecision(
                strategy=strategy,
                selected_content="",
                abstained=True,
                rationale="No candidates provided",
            )

        if strategy == "majority_vote":
            return self._majority_vote(candidates)
        if strategy == "weighted_vote":
            return self._weighted_vote(candidates)
        if strategy == "judge":
            return self._judge(candidates)

        return ConsensusDecision(
            strategy=strategy,
            selected_content="",
            abstained=True,
            rationale=f"Unknown strategy: {strategy}",
        )

    async def list_strategies(self) -> list[str]:
        return list(self._STRATEGIES)

    def _majority_vote(self, candidates: list[ConsensusCandidate]) -> ConsensusDecision:
        counts: Counter[str] = Counter()
        content_to_ids: dict[str, list[str]] = {}
        for c in candidates:
            counts[c.content] += 1
            content_to_ids.setdefault(c.content, []).append(c.id)

        winner_content, winner_count = counts.most_common(1)[0]
        confidence = winner_count / len(candidates)
        return ConsensusDecision(
            strategy="majority_vote",
            selected_content=winner_content,
            confidence=confidence,
            rationale=(f"Selected by majority vote ({winner_count}/{len(candidates)})"),
            candidate_ids=content_to_ids[winner_content],
        )

    def _weighted_vote(self, candidates: list[ConsensusCandidate]) -> ConsensusDecision:
        weighted: dict[str, float] = {}
        content_to_ids: dict[str, list[str]] = {}
        for c in candidates:
            weighted[c.content] = weighted.get(c.content, 0.0) + c.weight
            content_to_ids.setdefault(c.content, []).append(c.id)

        winner_content = max(weighted, key=weighted.__getitem__)
        total_weight = sum(c.weight for c in candidates)
        confidence = weighted[winner_content] / total_weight if total_weight else 0.0
        return ConsensusDecision(
            strategy="weighted_vote",
            selected_content=winner_content,
            confidence=confidence,
            rationale=(
                f"Selected by weighted vote "
                f"(weight {weighted[winner_content]:.2f}/{total_weight:.2f})"
            ),
            candidate_ids=content_to_ids[winner_content],
        )

    def _judge(self, candidates: list[ConsensusCandidate]) -> ConsensusDecision:
        best = max(candidates, key=lambda c: c.score)
        return ConsensusDecision(
            strategy="judge",
            selected_content=best.content,
            confidence=best.score,
            rationale=(f"Selected candidate with highest score ({best.score:.4f})"),
            candidate_ids=[best.id],
        )
