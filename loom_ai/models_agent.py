"""Phase 6 data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  Phase 6 protocols reference these types for their method
signatures.

Phase 6 covers Agent Architecture:

- Agent loop state and checkpoint (#59)
- Portable agent recipe and workflow (#60)
- ACP agent interoperability (#61)
- Context construction and compaction (#62)
- Agentic training and trajectory learning (#63)
- Executable agent environment (#64)
- Agent capability and requirement taxonomy (#65)
"""

from __future__ import annotations

from dataclasses import dataclass, field

# -- Agent loop models (#59) -------------------------------------------------


@dataclass
class AgentState:
    """Snapshot of the agent loop state machine at a specific point."""

    agent_id: str
    phase: str
    step: int = 0
    context: dict = field(default_factory=dict)
    status: str = "idle"
    created_at: str = ""


@dataclass
class AgentCheckpoint:
    """Serialisable checkpoint for pause/resume of an agent loop."""

    agent_id: str
    state: AgentState | None = None
    pending_operations: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class AgentOperation:
    """An independently replaceable operation within the agent loop."""

    name: str
    operation_type: str
    config: dict = field(default_factory=dict)
    timeout_ms: float = 0.0


@dataclass
class AgentTurn:
    """Record of a single turn in the agent loop."""

    turn_id: str
    agent_id: str
    operations: list[str] = field(default_factory=list)
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    status: str = "pending"


# -- Recipe / workflow models (#60) ------------------------------------------


@dataclass
class RecipeParameter:
    """A typed input parameter for a recipe."""

    name: str
    param_type: str
    description: str = ""
    required: bool = True
    default: str | None = None


@dataclass
class RecipeDefinition:
    """Portable, declarative agent workflow specification."""

    id: str
    name: str
    description: str = ""
    version: str = "1.0"
    parameters: list[RecipeParameter] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    sub_recipes: list[str] = field(default_factory=list)
    policies: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class RecipeResult:
    """Outcome of executing a recipe."""

    recipe_id: str
    run_id: str
    status: str
    outputs: dict = field(default_factory=dict)
    steps_completed: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    metadata: dict = field(default_factory=dict)


# -- ACP interoperability models (#61) ---------------------------------------


@dataclass
class ACPSession:
    """Session state for an ACP-compatible agent connection."""

    session_id: str
    agent_id: str
    status: str = "active"
    capabilities: list[str] = field(default_factory=list)
    created_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ACPMessage:
    """A message exchanged over the ACP protocol."""

    message_id: str
    session_id: str
    content: str
    message_type: str = "text"
    metadata: dict = field(default_factory=dict)


@dataclass
class ACPEvent:
    """A streaming event emitted during an ACP session."""

    event_type: str
    session_id: str
    data: dict = field(default_factory=dict)
    sequence: int = 0


# -- Context construction models (#62) --------------------------------------


@dataclass
class ContextSource:
    """A single source contributing to the assembled context."""

    source_type: str
    content: str
    priority: int = 0
    token_count: int = 0
    provenance: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class AssemblyContextBudget:
    """Token-budget allocation for context assembly."""

    total_tokens: int
    allocated: dict = field(default_factory=dict)
    used: int = 0
    remaining: int = 0


@dataclass
class ContextSnapshot:
    """Assembled context ready for model submission."""

    sources: list[ContextSource] = field(default_factory=list)
    budget: AssemblyContextBudget | None = None
    total_tokens: int = 0
    compacted: bool = False
    metadata: dict = field(default_factory=dict)


# -- Trajectory learning models (#63) ---------------------------------------


@dataclass
class TrajectoryStep:
    """A single step within an agent trajectory."""

    step_id: str
    action: str
    observation: str = ""
    reward: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class Trajectory:
    """Complete record of an agent's task execution path."""

    trajectory_id: str
    task: str
    steps: list[TrajectoryStep] = field(default_factory=list)
    outcome: str = ""
    total_reward: float = 0.0
    model: str = ""
    environment: str = ""
    created_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class TrajectoryFilter:
    """Criteria for filtering and curating trajectories."""

    min_reward: float | None = None
    max_reward: float | None = None
    outcome: str | None = None
    model: str | None = None
    task_pattern: str | None = None
    limit: int = 100


# -- Environment models (#64) -----------------------------------------------


@dataclass
class EnvironmentSpec:
    """Specification for an executable agent environment."""

    env_id: str
    env_type: str
    config: dict = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    security: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class EnvironmentSnapshot:
    """Point-in-time snapshot of an environment's state."""

    snapshot_id: str
    env_id: str
    state: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class AgentEnvironmentObservation:
    """An observation captured from the environment during execution."""

    env_id: str
    observation_type: str
    content: str
    verifiable: bool = False
    metadata: dict = field(default_factory=dict)


# -- Capability taxonomy models (#65) ----------------------------------------


@dataclass
class Capability:
    """A discrete capability that an agent or model may possess."""

    capability_id: str
    name: str
    description: str = ""
    category: str = ""
    parent_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class CapabilityRequirement:
    """A requirement specifying a needed capability and its constraints."""

    requirement_id: str
    capability_id: str
    level: str = "required"
    constraints: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentCapabilityProfile:
    """A profile listing capabilities possessed by a model or agent."""

    profile_id: str
    agent_or_model: str
    capabilities: list[str] = field(default_factory=list)
    scores: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
