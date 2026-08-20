"""Phase 8 protocol contracts for loom-ai.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required.  All I/O methods
are async.  Nothing outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.

Phase 8 covers nine contract areas:

- **EvalCapabilityRegistry** -- agent capability registry and discovery (#70)
- **CapabilitySelector** -- capability health, fallback, and backend
  selection (#71)
- **InteractionEvaluator** -- multi-agent interaction evaluation (#72)
- **SkillEstimator** -- Bayesian agent capability and skill estimation (#73)
- **EvaluationEnvironment** -- dynamic multi-agent evaluation
  environment (#74)
- **TournamentRunner** -- multi-model competitive evaluation and
  tournament (#75)
- **InferenceOptimizer** -- adaptive inference parameter optimization (#76)
- **OutputNormalizer** -- model output normalization and semantic
  comparison (#77)
- **ConsensusStrategy** -- model tournament, ensemble, and consensus
  strategy (#78)

Design notes
~~~~~~~~~~~~

Phase 8 introduces capability-level abstractions that complement but do
not duplicate earlier phases:

- ``EvalCapabilityRegistry`` (#70) is a *capability-level* registry.
  ``WorkerRegistry`` (Phase 3) manages fleet worker nodes; this contract
  manages the *capabilities* those workers (and external services) expose.

- ``CapabilitySelector`` (#71) handles capability health and fallback at
  the *capability* level.  ``ResiliencePolicy`` (Phase 2) handles
  circuit-breaker and rate-limiting at the *provider* level.

- ``InteractionEvaluator`` (#72) evaluates multi-agent *trajectories*
  (cooperation, competition, negotiation).  ``EvaluationHarness``
  (Phase 3) evaluates a single output against a task.

- ``SkillEstimator`` (#73) maintains Bayesian posterior skill estimates
  with uncertainty.  ``StrategySelector`` (Phase 2) selects *strategies*
  via Thompson Sampling bandit state.

- ``ConsensusStrategy`` (#78) defines pluggable *combination* strategies
  (voting, ensemble, judge, debate).  The existing ``ConsensusEngine``
  provides one specific fan-out/merge pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.models_capability import (
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
        NormalizedOutput,
        PairwiseOutcome,
        ParticipantScore,
        SelectionCriteria,
        SkillEstimate,
        TournamentCandidate,
        TournamentResult,
    )


# -- Capability Registry (#70) ----------------------------------------------


@runtime_checkable
class EvalCapabilityRegistry(Protocol):
    """Provider-neutral registry for capabilities that agents can discover
    and consume without coupling to individual tools, models, or services.

    Capabilities have identity, version, schema, and lifecycle.  Each
    capability may have multiple provider implementations.
    """

    async def register_capability(self, capability: EvalCapabilityDescriptor) -> None:
        """Register a new capability descriptor."""
        ...

    async def deregister_capability(self, capability_id: str) -> bool:
        """Remove a capability.  Return ``True`` if it existed."""
        ...

    async def discover(
        self, *, capability_type: str | None = None
    ) -> list[EvalCapabilityDescriptor]:
        """Discover available capabilities, optionally filtered by type."""
        ...

    async def get_capability(
        self, capability_id: str
    ) -> EvalCapabilityDescriptor | None:
        """Return a capability by id, or ``None`` if not found."""
        ...

    async def register_provider(
        self, capability_id: str, provider: CapabilityProvider
    ) -> None:
        """Register an implementation/backend for a capability."""
        ...

    async def list_providers(self, capability_id: str) -> list[CapabilityProvider]:
        """Return all registered providers for a capability."""
        ...


# -- Capability Selector (#71) ----------------------------------------------


@runtime_checkable
class CapabilitySelector(Protocol):
    """Select among capability implementations using health, latency,
    cost, and policy constraints, with ordered fallback behaviour.

    Complements ``ResiliencePolicy`` (Phase 2) which operates at the
    provider level; this contract operates at the capability level.
    """

    async def select_backend(
        self,
        capability_id: str,
        *,
        criteria: SelectionCriteria | None = None,
    ) -> CapabilityProvider:
        """Choose the best available provider for *capability_id*.

        Raises if no provider is available after fallback exhaustion.
        """
        ...

    async def health_state(
        self, capability_id: str, provider_id: str
    ) -> CapabilityHealthState:
        """Return the health state of a specific provider."""
        ...

    async def report_outcome(
        self,
        capability_id: str,
        provider_id: str,
        *,
        success: bool,
        latency_ms: float,
    ) -> None:
        """Record the outcome of a request to a capability provider."""
        ...

    async def fallback_chain(self, capability_id: str) -> list[CapabilityProvider]:
        """Return the ordered fallback chain for a capability."""
        ...


# -- Multi-Agent Interaction Evaluation (#72) --------------------------------


@runtime_checkable
class InteractionEvaluator(Protocol):
    """Evaluate agents through dynamic multi-agent interactions rather
    than static question/answer benchmarks.

    Complements ``EvaluationHarness`` (Phase 3) which evaluates a single
    output; this contract evaluates multi-agent *trajectories* involving
    cooperation, competition, negotiation, and persuasion.
    """

    async def evaluate_interaction(
        self, trajectory: InteractionTrajectory
    ) -> InteractionOutcome:
        """Evaluate a complete multi-agent interaction trajectory.

        Returns per-participant scores and behavioural metrics.
        """
        ...

    async def compare_participants(
        self, trajectory: InteractionTrajectory
    ) -> list[ParticipantScore]:
        """Rank and score participants from a trajectory."""
        ...


# -- Bayesian Skill Estimation (#73) ----------------------------------------


@runtime_checkable
class SkillEstimator(Protocol):
    """Bayesian estimation of latent agent capabilities from repeated
    interactions, rankings, and pairwise outcomes.

    Preserves posterior distributions and uncertainty rather than
    collapsing to a single leaderboard score.  Complements
    ``StrategySelector`` (Phase 2) which uses Thompson Sampling for
    *strategy* selection; this contract estimates *agent skill*.
    """

    async def estimate(
        self, agent_id: str, *, capability: str | None = None
    ) -> SkillEstimate:
        """Return the current skill estimate for an agent."""
        ...

    async def record_outcome(self, outcome: PairwiseOutcome) -> None:
        """Record a pairwise comparison outcome and update posteriors."""
        ...

    async def rankings(
        self, *, capability: str | None = None, limit: int = 10
    ) -> list[SkillEstimate]:
        """Return ranked skill estimates, optionally filtered by capability."""
        ...

    async def update_from_tournament(self, results: list[PairwiseOutcome]) -> None:
        """Batch-update posteriors from tournament results."""
        ...


# -- Dynamic Evaluation Environment (#74) -----------------------------------


@runtime_checkable
class EvaluationEnvironment(Protocol):
    """Reusable environment interface for dynamic multi-agent tasks
    in which agent actions change state and future available actions.

    Supports deterministic replay via seeds and emits structured
    trajectories consumable by evaluation and training systems.
    """

    async def reset(
        self, *, seed: int | None = None, config: EnvironmentConfig | None = None
    ) -> EnvironmentState:
        """Reset the environment and return the initial state.

        *seed* enables deterministic replay.  *config* provides
        environment versioning and parameter overrides.
        """
        ...

    async def step(
        self, agent_id: str, action: EnvironmentAction
    ) -> EvalEnvironmentObservation:
        """Apply an agent action and return the resulting observation."""
        ...

    async def get_state(self, *, agent_id: str | None = None) -> EnvironmentState:
        """Return the current environment state.

        When *agent_id* is provided, return the agent-specific view
        (which may hide private state belonging to other agents).
        """
        ...

    async def is_terminal(self) -> bool:
        """Return ``True`` if the environment has reached a terminal state."""
        ...

    async def export_trajectory(self) -> list[dict]:
        """Export the full interaction trajectory as a list of dicts."""
        ...


# -- Multi-Model Tournament (#75) -------------------------------------------


@runtime_checkable
class TournamentRunner(Protocol):
    """Run multiple models against the same task, preserve candidate
    outputs, and produce comparable evaluation results.

    Supports independent judges, composite scoring, and partial-result
    handling when some models fail.
    """

    async def run_tournament(
        self,
        task: str,
        *,
        models: list[str],
        rounds: int = 1,
    ) -> TournamentResult:
        """Execute a tournament across *models* for *task*.

        Each model produces a candidate response which is then scored
        and ranked.
        """
        ...

    async def judge(
        self,
        candidates: list[TournamentCandidate],
        *,
        task: str,
    ) -> list[JudgeVerdict]:
        """Score and rank a set of candidate responses for *task*."""
        ...


# -- Adaptive Inference Parameter Optimization (#76) -------------------------


@runtime_checkable
class InferenceOptimizer(Protocol):
    """Adapt inference parameters (temperature, top-p, etc.) based on
    task context and observed outcomes.

    Records effective parameters for reproducibility and supports
    model/provider-specific constraints.
    """

    async def optimize(
        self,
        task_context: str,
        *,
        model: str | None = None,
    ) -> InferenceParameters:
        """Return optimized inference parameters for *task_context*."""
        ...

    async def record_feedback(
        self,
        parameters: InferenceParameters,
        *,
        reward: float,
        task_context: str,
    ) -> None:
        """Record a reward observation for a set of parameters."""
        ...

    async def effective_parameters(self, model: str) -> InferenceParameters:
        """Return the current effective parameters for *model*."""
        ...


# -- Output Normalization and Semantic Comparison (#77) ----------------------


@runtime_checkable
class OutputNormalizer(Protocol):
    """Normalize model outputs for fair comparison without distorting
    substantive content.

    Preserves the original output as immutable evidence and tracks
    normalization provenance so evaluation can reproduce what was
    compared.
    """

    async def normalize(
        self,
        output: str,
        *,
        steps: list[str] | None = None,
        model: str = "",
    ) -> NormalizedOutput:
        """Normalize *output* using the specified (or default) steps.

        The original text is preserved in the returned object.
        """
        ...

    async def compare(self, outputs: list[NormalizedOutput]) -> ComparisonResult:
        """Compare multiple normalized outputs for semantic similarity."""
        ...

    async def list_steps(self) -> list[str]:
        """Return the names of available normalization steps."""
        ...


# -- Consensus Strategy (#78) -----------------------------------------------


@runtime_checkable
class ConsensusStrategy(Protocol):
    """Pluggable strategies for combining multiple model candidates
    rather than assuming the highest single score is always correct.

    Supports winner-take-all, weighted/ranked voting, judge-based
    selection, ensemble, debate, verification, and progressive
    refinement.  Integrates Bayesian skill estimates and Thompson
    Sampling where appropriate.
    """

    async def combine(
        self,
        candidates: list[ConsensusCandidate],
        *,
        strategy: str = "majority_vote",
    ) -> ConsensusDecision:
        """Combine *candidates* using the named *strategy*.

        Returns a decision with rationale and evidence.  Sets
        ``abstained=True`` when evidence is insufficient.
        """
        ...

    async def list_strategies(self) -> list[str]:
        """Return the names of available combination strategies."""
        ...
