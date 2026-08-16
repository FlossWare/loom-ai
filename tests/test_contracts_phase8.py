"""Conformance tests for Phase 8 protocol contracts.

Each test section verifies that a minimal stub class satisfies the
corresponding ``@runtime_checkable`` protocol via ``isinstance`` and
that the stub methods return the expected model types.
"""

from __future__ import annotations

from loom_ai.contracts_phase8 import (
    CapabilitySelector,
    ConsensusStrategy,
    EvalCapabilityRegistry,
    EvaluationEnvironment,
    InferenceOptimizer,
    InteractionEvaluator,
    OutputNormalizer,
    SkillEstimator,
    TournamentRunner,
)
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
    InteractionParticipant,
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

# ── Helpers ────────────────────────────────────────────────────────────────


def _cap(cap_id: str = "cap-1") -> EvalCapabilityDescriptor:
    """Shorthand factory for a test capability descriptor."""
    return EvalCapabilityDescriptor(
        id=cap_id,
        name="text-embedding",
        version="1.0",
        capability_type="embedding",
    )


def _provider(prov_id: str = "prov-1", cap_id: str = "cap-1") -> CapabilityProvider:
    """Shorthand factory for a test capability provider."""
    return CapabilityProvider(id=prov_id, capability_id=cap_id, name="openai")


def _trajectory(traj_id: str = "traj-1") -> InteractionTrajectory:
    """Shorthand factory for a test interaction trajectory."""
    return InteractionTrajectory(
        id=traj_id,
        participants=[
            InteractionParticipant(id="a1", model="opus"),
            InteractionParticipant(id="a2", model="sonnet"),
        ],
        steps=[
            {"agent": "a1", "action": "propose"},
            {"agent": "a2", "action": "accept"},
        ],
    )


def _candidate(cid: str = "c-1", model: str = "opus") -> TournamentCandidate:
    """Shorthand factory for a test tournament candidate."""
    return TournamentCandidate(id=cid, model=model, content="answer text")


def _consensus_candidate(cid: str = "cc-1", model: str = "opus") -> ConsensusCandidate:
    """Shorthand factory for a test consensus candidate."""
    return ConsensusCandidate(id=cid, model=model, content="answer text")


# ── Stub implementations ──────────────────────────────────────────────────


class StubEvalCapabilityRegistry:
    """Minimal stub satisfying the EvalCapabilityRegistry protocol."""

    def __init__(self) -> None:
        self._caps: dict[str, EvalCapabilityDescriptor] = {}
        self._providers: dict[str, list[CapabilityProvider]] = {}

    async def register_capability(self, capability: EvalCapabilityDescriptor) -> None:
        self._caps[capability.id] = capability

    async def deregister_capability(self, capability_id: str) -> bool:
        return self._caps.pop(capability_id, None) is not None

    async def discover(
        self, *, capability_type: str | None = None
    ) -> list[EvalCapabilityDescriptor]:
        caps = list(self._caps.values())
        if capability_type is not None:
            caps = [c for c in caps if c.capability_type == capability_type]
        return caps

    async def get_capability(
        self, capability_id: str
    ) -> EvalCapabilityDescriptor | None:
        return self._caps.get(capability_id)

    async def register_provider(
        self, capability_id: str, provider: CapabilityProvider
    ) -> None:
        self._providers.setdefault(capability_id, []).append(provider)

    async def list_providers(self, capability_id: str) -> list[CapabilityProvider]:
        return self._providers.get(capability_id, [])


class StubCapabilitySelector:
    """Minimal stub satisfying the CapabilitySelector protocol."""

    async def select_backend(
        self,
        capability_id: str,
        *,
        criteria: SelectionCriteria | None = None,
    ) -> CapabilityProvider:
        return _provider(cap_id=capability_id)

    async def health_state(
        self, capability_id: str, provider_id: str
    ) -> CapabilityHealthState:
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
        pass

    async def fallback_chain(self, capability_id: str) -> list[CapabilityProvider]:
        return [_provider(cap_id=capability_id)]


class StubInteractionEvaluator:
    """Minimal stub satisfying the InteractionEvaluator protocol."""

    async def evaluate_interaction(
        self, trajectory: InteractionTrajectory
    ) -> InteractionOutcome:
        return InteractionOutcome(trajectory_id=trajectory.id)

    async def compare_participants(
        self, trajectory: InteractionTrajectory
    ) -> list[ParticipantScore]:
        return [
            ParticipantScore(participant_id=p.id, rank=i + 1)
            for i, p in enumerate(trajectory.participants)
        ]


class StubSkillEstimator:
    """Minimal stub satisfying the SkillEstimator protocol."""

    def __init__(self) -> None:
        self._estimates: dict[str, SkillEstimate] = {}

    async def estimate(
        self, agent_id: str, *, capability: str | None = None
    ) -> SkillEstimate:
        key = f"{agent_id}:{capability or 'general'}"
        return self._estimates.get(
            key,
            SkillEstimate(
                agent_id=agent_id,
                capability=capability or "general",
            ),
        )

    async def record_outcome(self, outcome: PairwiseOutcome) -> None:
        for aid in (outcome.winner_id, outcome.loser_id):
            key = f"{aid}:{outcome.capability}"
            if key not in self._estimates:
                self._estimates[key] = SkillEstimate(
                    agent_id=aid, capability=outcome.capability
                )
        winner_key = f"{outcome.winner_id}:{outcome.capability}"
        self._estimates[winner_key].n_observations += 1

    async def rankings(
        self, *, capability: str | None = None, limit: int = 10
    ) -> list[SkillEstimate]:
        estimates = list(self._estimates.values())
        if capability is not None:
            estimates = [e for e in estimates if e.capability == capability]
        return sorted(estimates, key=lambda e: e.mean, reverse=True)[:limit]

    async def update_from_tournament(self, results: list[PairwiseOutcome]) -> None:
        for outcome in results:
            await self.record_outcome(outcome)


class StubEvaluationEnvironment:
    """Minimal stub satisfying the EvaluationEnvironment protocol."""

    def __init__(self) -> None:
        self._step = 0
        self._terminal = False
        self._trajectory: list[dict] = []

    async def reset(
        self, *, seed: int | None = None, config: EnvironmentConfig | None = None
    ) -> EnvironmentState:
        self._step = 0
        self._terminal = False
        self._trajectory = []
        return EnvironmentState(environment_id="env-1")

    async def step(
        self, agent_id: str, action: EnvironmentAction
    ) -> EvalEnvironmentObservation:
        self._step += 1
        self._trajectory.append(
            {"agent": agent_id, "action": action.action_type, "step": self._step}
        )
        state = EnvironmentState(
            environment_id="env-1",
            step_number=self._step,
        )
        return EvalEnvironmentObservation(state=state)

    async def get_state(self, *, agent_id: str | None = None) -> EnvironmentState:
        return EnvironmentState(
            environment_id="env-1",
            step_number=self._step,
            terminal=self._terminal,
        )

    async def is_terminal(self) -> bool:
        return self._terminal

    async def export_trajectory(self) -> list[dict]:
        return list(self._trajectory)


class StubTournamentRunner:
    """Minimal stub satisfying the TournamentRunner protocol."""

    async def run_tournament(
        self,
        task: str,
        *,
        models: list[str],
        rounds: int = 1,
    ) -> TournamentResult:
        candidates = [
            TournamentCandidate(id=f"c-{i}", model=m, content=f"response from {m}")
            for i, m in enumerate(models)
        ]
        verdicts = [
            JudgeVerdict(candidate_id=c.id, score=float(len(models) - i), rank=i + 1)
            for i, c in enumerate(candidates)
        ]
        return TournamentResult(
            task=task,
            candidates=candidates,
            verdicts=verdicts,
            winner_id=candidates[0].id if candidates else None,
            rounds_completed=rounds,
        )

    async def judge(
        self,
        candidates: list[TournamentCandidate],
        *,
        task: str,
    ) -> list[JudgeVerdict]:
        return [
            JudgeVerdict(candidate_id=c.id, score=1.0, rank=i + 1)
            for i, c in enumerate(candidates)
        ]


class StubInferenceOptimizer:
    """Minimal stub satisfying the InferenceOptimizer protocol."""

    async def optimize(
        self,
        task_context: str,
        *,
        model: str | None = None,
    ) -> InferenceParameters:
        return InferenceParameters(model=model or "", temperature=0.5)

    async def record_feedback(
        self,
        parameters: InferenceParameters,
        *,
        reward: float,
        task_context: str,
    ) -> None:
        pass

    async def effective_parameters(self, model: str) -> InferenceParameters:
        return InferenceParameters(model=model)


class StubOutputNormalizer:
    """Minimal stub satisfying the OutputNormalizer protocol."""

    async def normalize(
        self,
        output: str,
        *,
        steps: list[str] | None = None,
        model: str = "",
    ) -> NormalizedOutput:
        normalized = output.strip().lower()
        applied = [NormalizationStep(name=s) for s in (steps or ["strip", "lowercase"])]
        return NormalizedOutput(
            original=output,
            normalized=normalized,
            steps_applied=applied,
            model=model,
        )

    async def compare(self, outputs: list[NormalizedOutput]) -> ComparisonResult:
        n = len(outputs)
        matrix = [[1.0 if i == j else 0.5 for j in range(n)] for i in range(n)]
        return ComparisonResult(similarity_matrix=matrix)

    async def list_steps(self) -> list[str]:
        return ["strip", "lowercase", "remove_punctuation"]


class StubConsensusStrategy:
    """Minimal stub satisfying the ConsensusStrategy protocol."""

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
                rationale="No candidates provided.",
            )
        best = max(candidates, key=lambda c: c.score)
        return ConsensusDecision(
            strategy=strategy,
            selected_content=best.content,
            confidence=best.score,
            candidate_ids=[c.id for c in candidates],
            rationale=f"Selected by {strategy}.",
        )

    async def list_strategies(self) -> list[str]:
        return [
            "majority_vote",
            "weighted_vote",
            "ranked_vote",
            "judge",
            "ensemble",
            "debate",
        ]


# ── Protocol conformance tests ────────────────────────────────────────────


class TestEvalCapabilityRegistryProtocol:
    """EvalCapabilityRegistry protocol conformance."""

    def test_isinstance(self) -> None:
        assert isinstance(StubEvalCapabilityRegistry(), EvalCapabilityRegistry)

    async def test_register_and_discover(self) -> None:
        reg = StubEvalCapabilityRegistry()
        cap = _cap()
        await reg.register_capability(cap)
        found = await reg.discover()
        assert len(found) == 1
        assert found[0].id == "cap-1"

    async def test_discover_by_type(self) -> None:
        reg = StubEvalCapabilityRegistry()
        await reg.register_capability(_cap("c1"))
        await reg.register_capability(
            EvalCapabilityDescriptor(
                id="c2", name="chat", version="1.0", capability_type="chat"
            )
        )
        embedding_caps = await reg.discover(capability_type="embedding")
        assert len(embedding_caps) == 1
        assert embedding_caps[0].id == "c1"

    async def test_deregister(self) -> None:
        reg = StubEvalCapabilityRegistry()
        await reg.register_capability(_cap())
        assert await reg.deregister_capability("cap-1") is True
        assert await reg.deregister_capability("cap-1") is False

    async def test_get_capability(self) -> None:
        reg = StubEvalCapabilityRegistry()
        await reg.register_capability(_cap())
        result = await reg.get_capability("cap-1")
        assert result is not None
        assert result.name == "text-embedding"

    async def test_get_capability_not_found(self) -> None:
        reg = StubEvalCapabilityRegistry()
        assert await reg.get_capability("missing") is None

    async def test_register_and_list_providers(self) -> None:
        reg = StubEvalCapabilityRegistry()
        await reg.register_capability(_cap())
        await reg.register_provider("cap-1", _provider("p1"))
        await reg.register_provider("cap-1", _provider("p2"))
        providers = await reg.list_providers("cap-1")
        assert len(providers) == 2

    async def test_list_providers_empty(self) -> None:
        reg = StubEvalCapabilityRegistry()
        assert await reg.list_providers("missing") == []


class TestCapabilitySelectorProtocol:
    """CapabilitySelector protocol conformance."""

    def test_isinstance(self) -> None:
        assert isinstance(StubCapabilitySelector(), CapabilitySelector)

    async def test_select_backend(self) -> None:
        sel = StubCapabilitySelector()
        provider = await sel.select_backend("cap-1")
        assert isinstance(provider, CapabilityProvider)
        assert provider.capability_id == "cap-1"

    async def test_select_backend_with_criteria(self) -> None:
        sel = StubCapabilitySelector()
        criteria = SelectionCriteria(prefer_low_latency=True)
        provider = await sel.select_backend("cap-1", criteria=criteria)
        assert isinstance(provider, CapabilityProvider)

    async def test_health_state(self) -> None:
        sel = StubCapabilitySelector()
        hs = await sel.health_state("cap-1", "prov-1")
        assert isinstance(hs, CapabilityHealthState)
        assert hs.state == "healthy"

    async def test_report_outcome(self) -> None:
        sel = StubCapabilitySelector()
        await sel.report_outcome("cap-1", "prov-1", success=True, latency_ms=42.0)

    async def test_fallback_chain(self) -> None:
        sel = StubCapabilitySelector()
        chain = await sel.fallback_chain("cap-1")
        assert len(chain) >= 1
        assert all(isinstance(p, CapabilityProvider) for p in chain)


class TestInteractionEvaluatorProtocol:
    """InteractionEvaluator protocol conformance."""

    def test_isinstance(self) -> None:
        assert isinstance(StubInteractionEvaluator(), InteractionEvaluator)

    async def test_evaluate_interaction(self) -> None:
        ev = StubInteractionEvaluator()
        outcome = await ev.evaluate_interaction(_trajectory())
        assert isinstance(outcome, InteractionOutcome)
        assert outcome.trajectory_id == "traj-1"

    async def test_compare_participants(self) -> None:
        ev = StubInteractionEvaluator()
        scores = await ev.compare_participants(_trajectory())
        assert len(scores) == 2
        assert all(isinstance(s, ParticipantScore) for s in scores)
        assert scores[0].rank == 1
        assert scores[1].rank == 2


class TestSkillEstimatorProtocol:
    """SkillEstimator protocol conformance."""

    def test_isinstance(self) -> None:
        assert isinstance(StubSkillEstimator(), SkillEstimator)

    async def test_estimate_new_agent(self) -> None:
        est = StubSkillEstimator()
        skill = await est.estimate("agent-1")
        assert isinstance(skill, SkillEstimate)
        assert skill.agent_id == "agent-1"
        assert skill.capability == "general"

    async def test_estimate_with_capability(self) -> None:
        est = StubSkillEstimator()
        skill = await est.estimate("agent-1", capability="coding")
        assert skill.capability == "coding"

    async def test_record_outcome_updates_observations(self) -> None:
        est = StubSkillEstimator()
        outcome = PairwiseOutcome(winner_id="a1", loser_id="a2", capability="coding")
        await est.record_outcome(outcome)
        skill = await est.estimate("a1", capability="coding")
        assert skill.n_observations == 1

    async def test_rankings_empty(self) -> None:
        est = StubSkillEstimator()
        rankings = await est.rankings()
        assert rankings == []

    async def test_rankings_after_outcomes(self) -> None:
        est = StubSkillEstimator()
        await est.record_outcome(
            PairwiseOutcome(winner_id="a1", loser_id="a2", capability="coding")
        )
        rankings = await est.rankings(capability="coding")
        assert len(rankings) == 2

    async def test_update_from_tournament(self) -> None:
        est = StubSkillEstimator()
        outcomes = [
            PairwiseOutcome(winner_id="a1", loser_id="a2", capability="chat"),
            PairwiseOutcome(winner_id="a1", loser_id="a3", capability="chat"),
        ]
        await est.update_from_tournament(outcomes)
        skill = await est.estimate("a1", capability="chat")
        assert skill.n_observations == 2


class TestEvaluationEnvironmentProtocol:
    """EvaluationEnvironment protocol conformance."""

    def test_isinstance(self) -> None:
        assert isinstance(StubEvaluationEnvironment(), EvaluationEnvironment)

    async def test_reset(self) -> None:
        env = StubEvaluationEnvironment()
        state = await env.reset()
        assert isinstance(state, EnvironmentState)
        assert state.step_number == 0

    async def test_reset_with_seed(self) -> None:
        env = StubEvaluationEnvironment()
        state = await env.reset(seed=42)
        assert isinstance(state, EnvironmentState)

    async def test_reset_with_config(self) -> None:
        env = StubEvaluationEnvironment()
        cfg = EnvironmentConfig(environment_type="game", version="1.0", seed=42)
        state = await env.reset(config=cfg)
        assert isinstance(state, EnvironmentState)

    async def test_step(self) -> None:
        env = StubEvaluationEnvironment()
        await env.reset()
        action = EnvironmentAction(action_type="move", agent_id="a1")
        obs = await env.step("a1", action)
        assert isinstance(obs, EvalEnvironmentObservation)
        assert obs.state.step_number == 1

    async def test_multiple_steps(self) -> None:
        env = StubEvaluationEnvironment()
        await env.reset()
        for i in range(3):
            action = EnvironmentAction(action_type="act", agent_id=f"a{i}")
            obs = await env.step(f"a{i}", action)
        assert obs.state.step_number == 3

    async def test_get_state(self) -> None:
        env = StubEvaluationEnvironment()
        await env.reset()
        state = await env.get_state()
        assert isinstance(state, EnvironmentState)

    async def test_get_state_for_agent(self) -> None:
        env = StubEvaluationEnvironment()
        await env.reset()
        state = await env.get_state(agent_id="a1")
        assert isinstance(state, EnvironmentState)

    async def test_is_terminal(self) -> None:
        env = StubEvaluationEnvironment()
        await env.reset()
        assert await env.is_terminal() is False

    async def test_export_trajectory(self) -> None:
        env = StubEvaluationEnvironment()
        await env.reset()
        await env.step("a1", EnvironmentAction(action_type="act"))
        await env.step("a2", EnvironmentAction(action_type="respond"))
        traj = await env.export_trajectory()
        assert len(traj) == 2
        assert traj[0]["agent"] == "a1"
        assert traj[1]["agent"] == "a2"

    async def test_export_trajectory_empty(self) -> None:
        env = StubEvaluationEnvironment()
        await env.reset()
        assert await env.export_trajectory() == []


class TestTournamentRunnerProtocol:
    """TournamentRunner protocol conformance."""

    def test_isinstance(self) -> None:
        assert isinstance(StubTournamentRunner(), TournamentRunner)

    async def test_run_tournament(self) -> None:
        runner = StubTournamentRunner()
        result = await runner.run_tournament(
            "write a haiku", models=["opus", "sonnet", "haiku"]
        )
        assert isinstance(result, TournamentResult)
        assert result.task == "write a haiku"
        assert len(result.candidates) == 3
        assert len(result.verdicts) == 3
        assert result.winner_id is not None
        assert result.rounds_completed == 1

    async def test_run_tournament_multiple_rounds(self) -> None:
        runner = StubTournamentRunner()
        result = await runner.run_tournament("task", models=["a", "b"], rounds=3)
        assert result.rounds_completed == 3

    async def test_run_tournament_empty_models(self) -> None:
        runner = StubTournamentRunner()
        result = await runner.run_tournament("task", models=[])
        assert result.candidates == []
        assert result.winner_id is None

    async def test_judge(self) -> None:
        runner = StubTournamentRunner()
        candidates = [_candidate("c1", "opus"), _candidate("c2", "sonnet")]
        verdicts = await runner.judge(candidates, task="evaluate this")
        assert len(verdicts) == 2
        assert all(isinstance(v, JudgeVerdict) for v in verdicts)
        assert verdicts[0].rank == 1
        assert verdicts[1].rank == 2


class TestInferenceOptimizerProtocol:
    """InferenceOptimizer protocol conformance."""

    def test_isinstance(self) -> None:
        assert isinstance(StubInferenceOptimizer(), InferenceOptimizer)

    async def test_optimize(self) -> None:
        opt = StubInferenceOptimizer()
        params = await opt.optimize("write code")
        assert isinstance(params, InferenceParameters)
        assert params.temperature == 0.5

    async def test_optimize_with_model(self) -> None:
        opt = StubInferenceOptimizer()
        params = await opt.optimize("write code", model="opus")
        assert params.model == "opus"

    async def test_record_feedback(self) -> None:
        opt = StubInferenceOptimizer()
        params = InferenceParameters(temperature=0.3, model="opus")
        await opt.record_feedback(params, reward=0.9, task_context="coding")

    async def test_effective_parameters(self) -> None:
        opt = StubInferenceOptimizer()
        params = await opt.effective_parameters("opus")
        assert isinstance(params, InferenceParameters)
        assert params.model == "opus"


class TestOutputNormalizerProtocol:
    """OutputNormalizer protocol conformance."""

    def test_isinstance(self) -> None:
        assert isinstance(StubOutputNormalizer(), OutputNormalizer)

    async def test_normalize_preserves_original(self) -> None:
        norm = StubOutputNormalizer()
        result = await norm.normalize("  Hello World  ")
        assert isinstance(result, NormalizedOutput)
        assert result.original == "  Hello World  "
        assert result.normalized == "hello world"

    async def test_normalize_with_steps(self) -> None:
        norm = StubOutputNormalizer()
        result = await norm.normalize("text", steps=["custom_step"])
        assert len(result.steps_applied) == 1
        assert result.steps_applied[0].name == "custom_step"

    async def test_normalize_with_model(self) -> None:
        norm = StubOutputNormalizer()
        result = await norm.normalize("text", model="opus")
        assert result.model == "opus"

    async def test_compare(self) -> None:
        norm = StubOutputNormalizer()
        o1 = await norm.normalize("hello")
        o2 = await norm.normalize("world")
        result = await norm.compare([o1, o2])
        assert isinstance(result, ComparisonResult)
        assert len(result.similarity_matrix) == 2
        assert result.similarity_matrix[0][0] == 1.0
        assert result.similarity_matrix[0][1] == 0.5

    async def test_list_steps(self) -> None:
        norm = StubOutputNormalizer()
        steps = await norm.list_steps()
        assert isinstance(steps, list)
        assert len(steps) >= 1
        assert "strip" in steps


class TestConsensusStrategyProtocol:
    """ConsensusStrategy protocol conformance."""

    def test_isinstance(self) -> None:
        assert isinstance(StubConsensusStrategy(), ConsensusStrategy)

    async def test_combine(self) -> None:
        cs = StubConsensusStrategy()
        candidates = [
            _consensus_candidate("c1", "opus"),
            _consensus_candidate("c2", "sonnet"),
        ]
        candidates[0].score = 0.9
        candidates[1].score = 0.7
        decision = await cs.combine(candidates)
        assert isinstance(decision, ConsensusDecision)
        assert decision.strategy == "majority_vote"
        assert decision.selected_content == "answer text"
        assert decision.abstained is False
        assert len(decision.candidate_ids) == 2

    async def test_combine_with_strategy(self) -> None:
        cs = StubConsensusStrategy()
        candidates = [_consensus_candidate()]
        candidates[0].score = 1.0
        decision = await cs.combine(candidates, strategy="weighted_vote")
        assert decision.strategy == "weighted_vote"

    async def test_combine_empty_candidates_abstains(self) -> None:
        cs = StubConsensusStrategy()
        decision = await cs.combine([])
        assert decision.abstained is True
        assert decision.selected_content == ""

    async def test_list_strategies(self) -> None:
        cs = StubConsensusStrategy()
        strategies = await cs.list_strategies()
        assert isinstance(strategies, list)
        assert "majority_vote" in strategies
        assert len(strategies) >= 2


# ── Model dataclass tests ────────────────────────────────────────────────


class TestModelsPhase8:
    """Verify Phase 8 model dataclasses instantiate correctly."""

    def test_capability_descriptor_defaults(self) -> None:
        cap = EvalCapabilityDescriptor(
            id="c1", name="embed", version="1.0", capability_type="embedding"
        )
        assert cap.schema == {}
        assert cap.permissions == []
        assert cap.dependencies == []

    def test_capability_provider_defaults(self) -> None:
        prov = CapabilityProvider(id="p1", capability_id="c1", name="openai")
        assert prov.priority == 0
        assert prov.cost_per_call == 0.0

    def test_capability_health_state(self) -> None:
        hs = CapabilityHealthState(
            provider_id="p1", capability_id="c1", state="degraded"
        )
        assert hs.error is None
        assert hs.error_rate == 0.0

    def test_selection_criteria_defaults(self) -> None:
        sc = SelectionCriteria()
        assert sc.prefer_low_latency is False
        assert sc.max_latency_ms is None
        assert sc.exclude_providers == []

    def test_interaction_participant(self) -> None:
        p = InteractionParticipant(id="a1", model="opus")
        assert p.role == ""
        assert p.config == {}

    def test_interaction_trajectory(self) -> None:
        t = InteractionTrajectory(id="t1")
        assert t.participants == []
        assert t.steps == []
        assert t.seed is None

    def test_participant_score(self) -> None:
        ps = ParticipantScore(participant_id="a1")
        assert ps.scores == {}
        assert ps.rank == 0

    def test_interaction_outcome(self) -> None:
        io = InteractionOutcome(trajectory_id="t1")
        assert io.participant_scores == []
        assert io.summary == ""

    def test_skill_estimate(self) -> None:
        se = SkillEstimate(agent_id="a1", capability="coding")
        assert se.mean == 0.0
        assert se.variance == 1.0
        assert se.n_observations == 0

    def test_pairwise_outcome(self) -> None:
        po = PairwiseOutcome(winner_id="a1", loser_id="a2", capability="chat")
        assert po.draw is False
        assert po.margin == 0.0

    def test_environment_state(self) -> None:
        es = EnvironmentState(environment_id="e1")
        assert es.step_number == 0
        assert es.terminal is False
        assert es.available_actions == []

    def test_environment_action(self) -> None:
        ea = EnvironmentAction(action_type="move")
        assert ea.parameters == {}
        assert ea.agent_id == ""

    def test_environment_observation(self) -> None:
        state = EnvironmentState(environment_id="e1")
        eo = EvalEnvironmentObservation(state=state)
        assert eo.reward == 0.0
        assert eo.info == {}

    def test_environment_config(self) -> None:
        ec = EnvironmentConfig(environment_type="game", version="1.0")
        assert ec.seed is None
        assert ec.parameters == {}

    def test_tournament_candidate(self) -> None:
        tc = TournamentCandidate(id="c1", model="opus", content="text")
        assert tc.latency_ms == 0.0
        assert tc.tokens_used == 0

    def test_judge_verdict(self) -> None:
        jv = JudgeVerdict(candidate_id="c1")
        assert jv.score == 0.0
        assert jv.rank == 0
        assert jv.judge_model == ""

    def test_tournament_result(self) -> None:
        tr = TournamentResult(task="test")
        assert tr.candidates == []
        assert tr.winner_id is None
        assert tr.rounds_completed == 0

    def test_inference_parameters_defaults(self) -> None:
        ip = InferenceParameters()
        assert ip.temperature == 0.7
        assert ip.top_p == 1.0
        assert ip.top_k is None
        assert ip.max_tokens is None
        assert ip.stop_sequences == []

    def test_normalization_step(self) -> None:
        ns = NormalizationStep(name="strip")
        assert ns.description == ""
        assert ns.parameters == {}

    def test_normalized_output(self) -> None:
        no = NormalizedOutput(original="Hello", normalized="hello")
        assert no.steps_applied == []
        assert no.model == ""

    def test_comparison_result(self) -> None:
        cr = ComparisonResult()
        assert cr.similarity_matrix == []
        assert cr.clusters == []

    def test_consensus_candidate(self) -> None:
        cc = ConsensusCandidate(id="c1", model="opus", content="text")
        assert cc.weight == 1.0
        assert cc.skill_estimate is None

    def test_consensus_candidate_with_skill(self) -> None:
        se = SkillEstimate(agent_id="a1", capability="chat", mean=1500.0)
        cc = ConsensusCandidate(
            id="c1", model="opus", content="text", skill_estimate=se
        )
        assert cc.skill_estimate is not None
        assert cc.skill_estimate.mean == 1500.0

    def test_consensus_decision(self) -> None:
        cd = ConsensusDecision(strategy="vote", selected_content="answer")
        assert cd.confidence == 0.0
        assert cd.abstained is False
        assert cd.candidate_ids == []
