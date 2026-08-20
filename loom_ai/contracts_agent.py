"""Phase 6 protocol definitions for loom-ai.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required.  All methods are
async (except where synchronous semantics are appropriate).  Nothing
outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.

Phase 6 covers seven Agent Architecture contract areas:

- **AgentLoop** -- agent turn/state-machine with pause/resume/cancel (#59)
- **RecipeExecutor** -- portable, declarative agent recipe execution (#60)
- **ACPAdapter** -- ACP agent interoperability and session management (#61)
- **ContextAssembler** -- context construction, budgeting, and compaction (#62)
- **TrajectoryStore** -- trajectory capture, replay, and curation (#63)
- **AgentEnvironment** -- executable environment lifecycle and observation (#64)
- **AgentCapabilityRegistry** -- agent/model capability taxonomy and matching (#65)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.models_agent import (
        ACPEvent,
        ACPMessage,
        ACPSession,
        AgentCapabilityProfile,
        AgentCheckpoint,
        AgentEnvironmentObservation,
        AgentOperation,
        AgentState,
        AgentTurn,
        Capability,
        CapabilityRequirement,
        ContextSnapshot,
        ContextSource,
        EnvironmentSnapshot,
        EnvironmentSpec,
        RecipeDefinition,
        RecipeResult,
        Trajectory,
        TrajectoryFilter,
    )


# -- Agent Loop (#59) -------------------------------------------------------


@runtime_checkable
class AgentLoop(Protocol):
    """Re-entrant agent loop with independently replaceable operations.

    The agent loop models a turn-based state machine supporting
    pause/resume/cancel semantics and application-specific operation
    substitution.
    """

    async def step(self, agent_id: str) -> AgentTurn:
        """Execute the next operation in the agent loop and return the turn."""
        ...

    async def pause(self, agent_id: str) -> AgentCheckpoint:
        """Pause the agent loop and return a serialisable checkpoint."""
        ...

    async def resume(self, checkpoint: AgentCheckpoint) -> AgentState:
        """Resume the agent loop from a checkpoint."""
        ...

    async def cancel(self, agent_id: str) -> bool:
        """Cancel a running agent loop.  Return ``True`` if it was active."""
        ...

    async def state(self, agent_id: str) -> AgentState:
        """Return the current state of the agent loop."""
        ...

    async def register_operation(self, operation: AgentOperation) -> None:
        """Register or replace an operation in the agent loop."""
        ...

    async def list_operations(self, agent_id: str) -> list[AgentOperation]:
        """Return the operations registered for the agent loop."""
        ...


# -- Recipe Executor (#60) --------------------------------------------------


@runtime_checkable
class RecipeExecutor(Protocol):
    """Execute portable, declarative agent recipes.

    Recipes specify inputs, instructions, models, tools, sub-recipes,
    policies, and outputs in a version-controlled format.
    """

    async def execute(
        self,
        recipe: RecipeDefinition,
        *,
        inputs: dict | None = None,
    ) -> RecipeResult:
        """Run *recipe* with the given *inputs* and return the result."""
        ...

    async def validate(self, recipe: RecipeDefinition) -> list[str]:
        """Validate a recipe and return a list of errors (empty if valid)."""
        ...

    async def list_recipes(self) -> list[RecipeDefinition]:
        """Return all available recipe definitions."""
        ...

    async def get_recipe(self, recipe_id: str) -> RecipeDefinition | None:
        """Return a recipe by id, or ``None`` if not found."""
        ...


# -- ACP Adapter (#61) ------------------------------------------------------


@runtime_checkable
class ACPAdapter(Protocol):
    """Agent Client Protocol adapter for cross-runtime interoperability.

    Manages ACP sessions with streaming, cancellation, and permission
    semantics while keeping MCP as the extension/tool protocol.
    """

    async def create_session(
        self,
        agent_id: str,
        *,
        capabilities: list[str] | None = None,
        metadata: dict | None = None,
    ) -> ACPSession:
        """Create a new ACP session for the given agent."""
        ...

    async def send_message(self, session_id: str, message: ACPMessage) -> ACPMessage:
        """Send a message within an ACP session and return the response."""
        ...

    async def cancel_session(self, session_id: str) -> bool:
        """Cancel an active ACP session.  Return ``True`` if it was active."""
        ...

    async def get_session(self, session_id: str) -> ACPSession | None:
        """Return session state, or ``None`` if not found."""
        ...

    async def list_events(
        self, session_id: str, *, since_sequence: int = 0
    ) -> list[ACPEvent]:
        """Return streaming events for a session since *since_sequence*."""
        ...


# -- Context Assembler (#62) ------------------------------------------------


@runtime_checkable
class ContextAssembler(Protocol):
    """Construct, prioritise, compact, and debug model context.

    Handles system instructions, conversation state, memory, retrieved
    knowledge, tool results, and generated artefacts with token-budget
    awareness and provenance tracking.
    """

    async def assemble(
        self,
        sources: list[ContextSource],
        *,
        max_tokens: int | None = None,
    ) -> ContextSnapshot:
        """Assemble *sources* into a context snapshot within the token budget."""
        ...

    async def compact(
        self,
        snapshot: ContextSnapshot,
        *,
        target_tokens: int,
    ) -> ContextSnapshot:
        """Compact *snapshot* to fit within *target_tokens*."""
        ...

    async def add_source(
        self, snapshot: ContextSnapshot, source: ContextSource
    ) -> ContextSnapshot:
        """Add a source to an existing snapshot, re-budgeting as needed."""
        ...

    async def replay(self, snapshot: ContextSnapshot) -> list[dict]:
        """Return a debug-friendly replay of how context was assembled."""
        ...


# -- Trajectory Store (#63) -------------------------------------------------


@runtime_checkable
class TrajectoryStore(Protocol):
    """Capture, store, replay, and curate agent trajectories.

    Trajectories link actions, observations, and rewards to models,
    tools, prompts, knowledge, and environment versions for
    post-training and improvement.
    """

    async def record(self, trajectory: Trajectory) -> str:
        """Persist a trajectory and return its id."""
        ...

    async def get(self, trajectory_id: str) -> Trajectory | None:
        """Return a trajectory by id, or ``None`` if not found."""
        ...

    async def search(
        self, *, task: str | None = None, limit: int = 10
    ) -> list[Trajectory]:
        """Search trajectories by task description."""
        ...

    async def filter(self, criteria: TrajectoryFilter) -> list[Trajectory]:
        """Return trajectories matching *criteria*."""
        ...

    async def replay(self, trajectory_id: str) -> list[dict]:
        """Return a step-by-step replay of the trajectory."""
        ...

    async def export(
        self,
        trajectory_ids: list[str],
        *,
        format: str = "jsonl",
    ) -> Any:
        """Export trajectories in a training-data format."""
        ...


# -- Agent Environment (#64) ------------------------------------------------


@runtime_checkable
class AgentEnvironment(Protocol):
    """Provider-neutral executable environment for agent tasks.

    Manages environment lifecycle, isolation, snapshots, and verifiable
    observations across terminal, code, research, and other domains.
    """

    async def create(self, spec: EnvironmentSpec) -> str:
        """Create an environment from *spec* and return its id."""
        ...

    async def reset(self, env_id: str) -> None:
        """Reset the environment to its initial state."""
        ...

    async def snapshot(self, env_id: str) -> EnvironmentSnapshot:
        """Capture a point-in-time snapshot of the environment."""
        ...

    async def restore(self, snapshot: EnvironmentSnapshot) -> None:
        """Restore the environment to a previous snapshot."""
        ...

    async def observe(self, env_id: str) -> AgentEnvironmentObservation:
        """Capture the current observation from the environment."""
        ...

    async def teardown(self, env_id: str) -> bool:
        """Destroy the environment.  Return ``True`` if it existed."""
        ...


# -- Capability Registry (#65) -----------------------------------------------


@runtime_checkable
class AgentCapabilityRegistry(Protocol):
    """Capability-oriented taxonomy for agent and model selection.

    Separates desired capabilities from implementation substrate,
    enabling capability composition, hierarchical taxonomies,
    and routing based on capability profiles.
    """

    async def register_capability(self, capability: Capability) -> None:
        """Register a capability in the taxonomy."""
        ...

    async def get_capability(self, capability_id: str) -> Capability | None:
        """Return a capability by id, or ``None`` if not found."""
        ...

    async def list_capabilities(
        self, *, category: str | None = None
    ) -> list[Capability]:
        """Return capabilities, optionally filtered by category."""
        ...

    async def register_profile(self, profile: AgentCapabilityProfile) -> None:
        """Register a capability profile for a model or agent."""
        ...

    async def match(
        self, requirements: list[CapabilityRequirement]
    ) -> list[AgentCapabilityProfile]:
        """Return profiles satisfying all *requirements*."""
        ...

    async def get_profile(self, agent_or_model: str) -> AgentCapabilityProfile | None:
        """Return the capability profile for a model or agent."""
        ...
