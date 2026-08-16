"""Phase 8 data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  Phase 8 protocols reference these types for their method
signatures.

Phase 8 covers capability registry, health/fallback, multi-agent
interaction evaluation, Bayesian skill estimation, dynamic evaluation
environments, multi-model tournaments, inference parameter optimization,
output normalization, and consensus strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# -- Capability registry models (#70) ---------------------------------------


@dataclass
class EvalCapabilityDescriptor:
    """Identity and metadata for a registered capability.

    A capability represents a unit of functionality (e.g. "text-embedding",
    "code-generation") that may be provided by multiple backends.
    """

    id: str
    name: str
    version: str
    capability_type: str
    schema: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class CapabilityProvider:
    """An implementation/backend behind a registered capability."""

    id: str
    capability_id: str
    name: str
    priority: int = 0
    cost_per_call: float = 0.0
    avg_latency_ms: float = 0.0
    metadata: dict = field(default_factory=dict)


# -- Capability health and selection models (#71) ---------------------------


@dataclass
class CapabilityHealthState:
    """Health state of a capability backend implementation."""

    provider_id: str
    capability_id: str
    state: str  # "healthy", "degraded", "unavailable"
    latency_ms: float = 0.0
    error_rate: float = 0.0
    last_check: str = ""
    error: str | None = None


@dataclass
class SelectionCriteria:
    """Criteria for selecting among capability backend implementations."""

    prefer_low_latency: bool = False
    prefer_low_cost: bool = False
    max_latency_ms: float | None = None
    max_cost_per_call: float | None = None
    required_metadata: dict = field(default_factory=dict)
    exclude_providers: list[str] = field(default_factory=list)


# -- Multi-agent interaction evaluation models (#72) -------------------------


@dataclass
class InteractionParticipant:
    """An agent participating in a multi-agent evaluation."""

    id: str
    model: str
    role: str = ""
    config: dict = field(default_factory=dict)


@dataclass
class InteractionTrajectory:
    """Sequence of actions and messages from a multi-agent interaction."""

    id: str
    participants: list[InteractionParticipant] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    environment: str = ""
    seed: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ParticipantScore:
    """Evaluation score for a single participant in an interaction."""

    participant_id: str
    scores: dict = field(default_factory=dict)
    rank: int = 0
    reasoning: str = ""


@dataclass
class InteractionOutcome:
    """Outcome of a multi-agent interaction evaluation."""

    trajectory_id: str
    participant_scores: list[ParticipantScore] = field(default_factory=list)
    behavioral_metrics: dict = field(default_factory=dict)
    summary: str = ""


# -- Bayesian skill estimation models (#73) ----------------------------------


@dataclass
class SkillEstimate:
    """Latent skill estimate for an agent with uncertainty bounds."""

    agent_id: str
    capability: str
    mean: float = 0.0
    variance: float = 1.0
    lower_bound: float = 0.0
    upper_bound: float = 0.0
    n_observations: int = 0
    distribution_params: dict = field(default_factory=dict)


@dataclass
class PairwiseOutcome:
    """Result of a pairwise comparison between two agents."""

    winner_id: str
    loser_id: str
    capability: str
    draw: bool = False
    margin: float = 0.0
    context: dict = field(default_factory=dict)


# -- Dynamic evaluation environment models (#74) ----------------------------


@dataclass
class EnvironmentState:
    """Current state of an evaluation environment."""

    environment_id: str
    step_number: int = 0
    public_state: dict = field(default_factory=dict)
    available_actions: list[str] = field(default_factory=list)
    terminal: bool = False


@dataclass
class EnvironmentAction:
    """An action to be taken in an evaluation environment."""

    action_type: str
    parameters: dict = field(default_factory=dict)
    agent_id: str = ""


@dataclass
class EvalEnvironmentObservation:
    """Observation returned after an action in the evaluation environment."""

    state: EnvironmentState
    reward: float = 0.0
    info: dict = field(default_factory=dict)


@dataclass
class EnvironmentConfig:
    """Configuration and provenance for an evaluation environment."""

    environment_type: str
    version: str
    seed: int | None = None
    parameters: dict = field(default_factory=dict)


# -- Multi-model tournament models (#75) ------------------------------------


@dataclass
class TournamentCandidate:
    """A candidate response submitted to a tournament."""

    id: str
    model: str
    content: str
    latency_ms: float = 0.0
    tokens_used: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class JudgeVerdict:
    """Verdict from a judge evaluating tournament candidates."""

    candidate_id: str
    score: float = 0.0
    rank: int = 0
    reasoning: str = ""
    judge_model: str = ""


@dataclass
class TournamentResult:
    """Result of a multi-model competitive evaluation tournament."""

    task: str
    candidates: list[TournamentCandidate] = field(default_factory=list)
    verdicts: list[JudgeVerdict] = field(default_factory=list)
    winner_id: str | None = None
    rounds_completed: int = 0
    metadata: dict = field(default_factory=dict)


# -- Adaptive inference parameter optimization models (#76) -----------------


@dataclass
class InferenceParameters:
    """Tunable inference parameters for model invocation."""

    temperature: float = 0.7
    top_p: float = 1.0
    top_k: int | None = None
    max_tokens: int | None = None
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop_sequences: list[str] = field(default_factory=list)
    model: str = ""
    metadata: dict = field(default_factory=dict)


# -- Output normalization and semantic comparison models (#77) ---------------


@dataclass
class NormalizationStep:
    """A single normalization operation applied to model output."""

    name: str
    description: str = ""
    parameters: dict = field(default_factory=dict)


@dataclass
class NormalizedOutput:
    """Normalized model output with original preserved as evidence."""

    original: str
    normalized: str
    steps_applied: list[NormalizationStep] = field(default_factory=list)
    model: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ComparisonResult:
    """Result of comparing multiple normalized model outputs."""

    similarity_matrix: list[list[float]] = field(default_factory=list)
    clusters: list[list[int]] = field(default_factory=list)
    summary: str = ""
    metadata: dict = field(default_factory=dict)


# -- Consensus strategy models (#78) ----------------------------------------


@dataclass
class ConsensusCandidate:
    """A candidate for consensus combination."""

    id: str
    model: str
    content: str
    score: float = 0.0
    weight: float = 1.0
    skill_estimate: SkillEstimate | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ConsensusDecision:
    """Final decision produced by a consensus strategy."""

    strategy: str
    selected_content: str
    confidence: float = 0.0
    rationale: str = ""
    candidate_ids: list[str] = field(default_factory=list)
    abstained: bool = False
    metadata: dict = field(default_factory=dict)
