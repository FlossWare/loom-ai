"""Conformance tests for Phase 6 Agent Architecture protocol contracts.

Each test creates a minimal stub that structurally satisfies one of the
Phase 6 protocols and verifies that ``isinstance`` passes with the
``@runtime_checkable`` protocol.  Async method stubs are exercised to
confirm correct signatures.
"""

from __future__ import annotations

from typing import Any

from loom_ai.contracts_agent import (
    ACPAdapter,
    AgentCapabilityRegistry,
    AgentEnvironment,
    AgentLoop,
    ContextAssembler,
    RecipeExecutor,
    TrajectoryStore,
)
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
    AssemblyContextBudget,
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
    TrajectoryStep,
)

# ── Stub implementations ─────────────────────────────────────────────────


class StubAgentLoop:
    """Minimal stub satisfying the AgentLoop protocol."""

    async def step(self, agent_id: str) -> AgentTurn:
        return AgentTurn(turn_id="t-1", agent_id=agent_id, status="done")

    async def pause(self, agent_id: str) -> AgentCheckpoint:
        return AgentCheckpoint(agent_id=agent_id)

    async def resume(self, checkpoint: AgentCheckpoint) -> AgentState:
        return AgentState(agent_id=checkpoint.agent_id, phase="resumed")

    async def cancel(self, agent_id: str) -> bool:
        return True

    async def state(self, agent_id: str) -> AgentState:
        return AgentState(agent_id=agent_id, phase="idle")

    async def register_operation(self, operation: AgentOperation) -> None:
        pass

    async def list_operations(self, agent_id: str) -> list[AgentOperation]:
        return []


class StubRecipeExecutor:
    """Minimal stub satisfying the RecipeExecutor protocol."""

    async def execute(
        self,
        recipe: RecipeDefinition,
        *,
        inputs: dict | None = None,
    ) -> RecipeResult:
        return RecipeResult(recipe_id=recipe.id, run_id="run-1", status="success")

    async def validate(self, recipe: RecipeDefinition) -> list[str]:
        return []

    async def list_recipes(self) -> list[RecipeDefinition]:
        return []

    async def get_recipe(self, recipe_id: str) -> RecipeDefinition | None:
        return None


class StubACPAdapter:
    """Minimal stub satisfying the ACPAdapter protocol."""

    async def create_session(
        self,
        agent_id: str,
        *,
        capabilities: list[str] | None = None,
        metadata: dict | None = None,
    ) -> ACPSession:
        return ACPSession(session_id="s-1", agent_id=agent_id)

    async def send_message(self, session_id: str, message: ACPMessage) -> ACPMessage:
        return ACPMessage(message_id="m-resp", session_id=session_id, content="ack")

    async def cancel_session(self, session_id: str) -> bool:
        return True

    async def get_session(self, session_id: str) -> ACPSession | None:
        return None

    async def list_events(
        self, session_id: str, *, since_sequence: int = 0
    ) -> list[ACPEvent]:
        return []


class StubContextAssembler:
    """Minimal stub satisfying the ContextAssembler protocol."""

    async def assemble(
        self,
        sources: list[ContextSource],
        *,
        max_tokens: int | None = None,
    ) -> ContextSnapshot:
        return ContextSnapshot(sources=sources, total_tokens=0)

    async def compact(
        self,
        snapshot: ContextSnapshot,
        *,
        target_tokens: int,
    ) -> ContextSnapshot:
        return ContextSnapshot(
            sources=snapshot.sources,
            total_tokens=target_tokens,
            compacted=True,
        )

    async def add_source(
        self, snapshot: ContextSnapshot, source: ContextSource
    ) -> ContextSnapshot:
        return ContextSnapshot(
            sources=[*snapshot.sources, source],
            total_tokens=snapshot.total_tokens + source.token_count,
        )

    async def replay(self, snapshot: ContextSnapshot) -> list[dict]:
        return [{"step": "assemble", "sources": len(snapshot.sources)}]


class StubTrajectoryStore:
    """Minimal stub satisfying the TrajectoryStore protocol."""

    async def record(self, trajectory: Trajectory) -> str:
        return trajectory.trajectory_id

    async def get(self, trajectory_id: str) -> Trajectory | None:
        return None

    async def search(
        self, *, task: str | None = None, limit: int = 10
    ) -> list[Trajectory]:
        return []

    async def filter(self, criteria: TrajectoryFilter) -> list[Trajectory]:
        return []

    async def replay(self, trajectory_id: str) -> list[dict]:
        return []

    async def export(
        self,
        trajectory_ids: list[str],
        *,
        format: str = "jsonl",
    ) -> Any:
        return ""


class StubAgentEnvironment:
    """Minimal stub satisfying the AgentEnvironment protocol."""

    async def create(self, spec: EnvironmentSpec) -> str:
        return spec.env_id

    async def reset(self, env_id: str) -> None:
        pass

    async def snapshot(self, env_id: str) -> EnvironmentSnapshot:
        return EnvironmentSnapshot(snapshot_id="snap-1", env_id=env_id)

    async def restore(self, snapshot: EnvironmentSnapshot) -> None:
        pass

    async def observe(self, env_id: str) -> AgentEnvironmentObservation:
        return AgentEnvironmentObservation(
            env_id=env_id, observation_type="state", content=""
        )

    async def teardown(self, env_id: str) -> bool:
        return True


class StubAgentCapabilityRegistry:
    """Minimal stub satisfying the AgentCapabilityRegistry protocol."""

    async def register_capability(self, capability: Capability) -> None:
        pass

    async def get_capability(self, capability_id: str) -> Capability | None:
        return None

    async def list_capabilities(
        self, *, category: str | None = None
    ) -> list[Capability]:
        return []

    async def register_profile(self, profile: AgentCapabilityProfile) -> None:
        pass

    async def match(
        self, requirements: list[CapabilityRequirement]
    ) -> list[AgentCapabilityProfile]:
        return []

    async def get_profile(self, agent_or_model: str) -> AgentCapabilityProfile | None:
        return None


# ── Protocol conformance tests ───────────────────────────────────────────


def test_agent_loop_conformance():
    """StubAgentLoop satisfies the AgentLoop protocol."""
    assert isinstance(StubAgentLoop(), AgentLoop)


def test_recipe_executor_conformance():
    """StubRecipeExecutor satisfies the RecipeExecutor protocol."""
    assert isinstance(StubRecipeExecutor(), RecipeExecutor)


def test_acp_adapter_conformance():
    """StubACPAdapter satisfies the ACPAdapter protocol."""
    assert isinstance(StubACPAdapter(), ACPAdapter)


def test_context_assembler_conformance():
    """StubContextAssembler satisfies the ContextAssembler protocol."""
    assert isinstance(StubContextAssembler(), ContextAssembler)


def test_trajectory_store_conformance():
    """StubTrajectoryStore satisfies the TrajectoryStore protocol."""
    assert isinstance(StubTrajectoryStore(), TrajectoryStore)


def test_agent_environment_conformance():
    """StubAgentEnvironment satisfies the AgentEnvironment protocol."""
    assert isinstance(StubAgentEnvironment(), AgentEnvironment)


def test_capability_registry_conformance():
    """StubAgentCapabilityRegistry satisfies the AgentCapabilityRegistry protocol."""
    assert isinstance(StubAgentCapabilityRegistry(), AgentCapabilityRegistry)


# ── Non-conformance tests (negative) ─────────────────────────────────────


class _Empty:
    """An empty class that should not satisfy any protocol."""

    pass


def test_empty_does_not_satisfy_agent_loop():
    assert not isinstance(_Empty(), AgentLoop)


def test_empty_does_not_satisfy_recipe_executor():
    assert not isinstance(_Empty(), RecipeExecutor)


def test_empty_does_not_satisfy_acp_adapter():
    assert not isinstance(_Empty(), ACPAdapter)


def test_empty_does_not_satisfy_context_assembler():
    assert not isinstance(_Empty(), ContextAssembler)


def test_empty_does_not_satisfy_trajectory_store():
    assert not isinstance(_Empty(), TrajectoryStore)


def test_empty_does_not_satisfy_agent_environment():
    assert not isinstance(_Empty(), AgentEnvironment)


def test_empty_does_not_satisfy_capability_registry():
    assert not isinstance(_Empty(), AgentCapabilityRegistry)


# ── Async method exercise tests ──────────────────────────────────────────


async def test_agent_loop_step():
    """AgentLoop.step returns an AgentTurn with correct agent_id."""
    loop = StubAgentLoop()
    turn = await loop.step("agent-42")
    assert isinstance(turn, AgentTurn)
    assert turn.agent_id == "agent-42"


async def test_agent_loop_pause_resume():
    """AgentLoop pause/resume round-trip preserves agent_id."""
    loop = StubAgentLoop()
    checkpoint = await loop.pause("agent-42")
    assert isinstance(checkpoint, AgentCheckpoint)
    assert checkpoint.agent_id == "agent-42"

    state = await loop.resume(checkpoint)
    assert isinstance(state, AgentState)
    assert state.agent_id == "agent-42"
    assert state.phase == "resumed"


async def test_agent_loop_cancel():
    """AgentLoop.cancel returns True for an active agent."""
    loop = StubAgentLoop()
    assert await loop.cancel("agent-42") is True


async def test_agent_loop_state():
    """AgentLoop.state returns current AgentState."""
    loop = StubAgentLoop()
    s = await loop.state("agent-42")
    assert isinstance(s, AgentState)
    assert s.agent_id == "agent-42"


async def test_agent_loop_operations():
    """AgentLoop register/list operations round-trip."""
    loop = StubAgentLoop()
    op = AgentOperation(name="model_call", operation_type="llm")
    await loop.register_operation(op)
    ops = await loop.list_operations("agent-42")
    assert isinstance(ops, list)


async def test_recipe_executor_execute():
    """RecipeExecutor.execute returns a RecipeResult."""
    executor = StubRecipeExecutor()
    recipe = RecipeDefinition(id="r-1", name="test-recipe")
    result = await executor.execute(recipe, inputs={"key": "value"})
    assert isinstance(result, RecipeResult)
    assert result.recipe_id == "r-1"
    assert result.status == "success"


async def test_recipe_executor_validate():
    """RecipeExecutor.validate returns an empty list for a valid recipe."""
    executor = StubRecipeExecutor()
    recipe = RecipeDefinition(id="r-1", name="test-recipe")
    errors = await executor.validate(recipe)
    assert errors == []


async def test_recipe_executor_list_and_get():
    """RecipeExecutor list/get return expected types."""
    executor = StubRecipeExecutor()
    recipes = await executor.list_recipes()
    assert isinstance(recipes, list)
    assert await executor.get_recipe("nonexistent") is None


async def test_acp_adapter_session_lifecycle():
    """ACPAdapter create/get/cancel session lifecycle."""
    adapter = StubACPAdapter()
    session = await adapter.create_session(
        "agent-1", capabilities=["chat"], metadata={"k": "v"}
    )
    assert isinstance(session, ACPSession)
    assert session.agent_id == "agent-1"

    assert await adapter.get_session("s-1") is None
    assert await adapter.cancel_session("s-1") is True


async def test_acp_adapter_send_message():
    """ACPAdapter.send_message returns a response message."""
    adapter = StubACPAdapter()
    msg = ACPMessage(message_id="m-1", session_id="s-1", content="hello")
    resp = await adapter.send_message("s-1", msg)
    assert isinstance(resp, ACPMessage)
    assert resp.content == "ack"


async def test_acp_adapter_list_events():
    """ACPAdapter.list_events returns a list of events."""
    adapter = StubACPAdapter()
    events = await adapter.list_events("s-1", since_sequence=0)
    assert isinstance(events, list)


async def test_context_assembler_assemble():
    """ContextAssembler.assemble returns a ContextSnapshot."""
    assembler = StubContextAssembler()
    sources = [
        ContextSource(source_type="system", content="You are helpful."),
        ContextSource(source_type="memory", content="User prefers dark mode."),
    ]
    snapshot = await assembler.assemble(sources, max_tokens=4096)
    assert isinstance(snapshot, ContextSnapshot)
    assert len(snapshot.sources) == 2


async def test_context_assembler_compact():
    """ContextAssembler.compact marks snapshot as compacted."""
    assembler = StubContextAssembler()
    original = ContextSnapshot(
        sources=[ContextSource(source_type="system", content="test")],
        total_tokens=1000,
    )
    compacted = await assembler.compact(original, target_tokens=500)
    assert isinstance(compacted, ContextSnapshot)
    assert compacted.compacted is True
    assert compacted.total_tokens == 500


async def test_context_assembler_add_source():
    """ContextAssembler.add_source appends to snapshot sources."""
    assembler = StubContextAssembler()
    snapshot = ContextSnapshot(
        sources=[ContextSource(source_type="system", content="base")],
        total_tokens=100,
    )
    new_source = ContextSource(
        source_type="retrieval", content="retrieved", token_count=50
    )
    updated = await assembler.add_source(snapshot, new_source)
    assert len(updated.sources) == 2
    assert updated.total_tokens == 150


async def test_context_assembler_replay():
    """ContextAssembler.replay returns a debug trace."""
    assembler = StubContextAssembler()
    snapshot = ContextSnapshot(
        sources=[ContextSource(source_type="system", content="test")]
    )
    trace = await assembler.replay(snapshot)
    assert isinstance(trace, list)
    assert len(trace) > 0


async def test_trajectory_store_record_and_get():
    """TrajectoryStore record/get round-trip."""
    store = StubTrajectoryStore()
    traj = Trajectory(
        trajectory_id="traj-1",
        task="solve puzzle",
        steps=[TrajectoryStep(step_id="s-1", action="think")],
        outcome="success",
        total_reward=1.0,
    )
    tid = await store.record(traj)
    assert tid == "traj-1"
    assert await store.get("traj-1") is None  # stub returns None


async def test_trajectory_store_search():
    """TrajectoryStore.search returns a list."""
    store = StubTrajectoryStore()
    results = await store.search(task="puzzle", limit=5)
    assert isinstance(results, list)


async def test_trajectory_store_filter():
    """TrajectoryStore.filter accepts TrajectoryFilter."""
    store = StubTrajectoryStore()
    criteria = TrajectoryFilter(min_reward=0.5, outcome="success")
    results = await store.filter(criteria)
    assert isinstance(results, list)


async def test_trajectory_store_replay():
    """TrajectoryStore.replay returns step-by-step data."""
    store = StubTrajectoryStore()
    steps = await store.replay("traj-1")
    assert isinstance(steps, list)


async def test_trajectory_store_export():
    """TrajectoryStore.export accepts format parameter."""
    store = StubTrajectoryStore()
    data = await store.export(["traj-1", "traj-2"], format="jsonl")
    assert data is not None


async def test_agent_environment_lifecycle():
    """AgentEnvironment create/reset/teardown lifecycle."""
    env = StubAgentEnvironment()
    spec = EnvironmentSpec(env_id="env-1", env_type="terminal")
    eid = await env.create(spec)
    assert eid == "env-1"

    await env.reset("env-1")
    assert await env.teardown("env-1") is True


async def test_agent_environment_snapshot_restore():
    """AgentEnvironment snapshot/restore round-trip."""
    env = StubAgentEnvironment()
    snap = await env.snapshot("env-1")
    assert isinstance(snap, EnvironmentSnapshot)
    assert snap.env_id == "env-1"
    await env.restore(snap)  # should not raise


async def test_agent_environment_observe():
    """AgentEnvironment.observe returns an observation."""
    env = StubAgentEnvironment()
    obs = await env.observe("env-1")
    assert isinstance(obs, AgentEnvironmentObservation)
    assert obs.env_id == "env-1"


async def test_capability_registry_register_and_get():
    """AgentCapabilityRegistry register/get capability round-trip."""
    registry = StubAgentCapabilityRegistry()
    cap = Capability(capability_id="cap-1", name="code-generation", category="coding")
    await registry.register_capability(cap)
    assert await registry.get_capability("cap-1") is None  # stub returns None


async def test_capability_registry_list():
    """AgentCapabilityRegistry.list_capabilities accepts category filter."""
    registry = StubAgentCapabilityRegistry()
    caps = await registry.list_capabilities(category="coding")
    assert isinstance(caps, list)


async def test_capability_registry_profile_and_match():
    """AgentCapabilityRegistry profile registration and matching."""
    registry = StubAgentCapabilityRegistry()
    profile = AgentCapabilityProfile(
        profile_id="p-1",
        agent_or_model="opus",
        capabilities=["cap-1", "cap-2"],
        scores={"cap-1": 0.95, "cap-2": 0.80},
    )
    await registry.register_profile(profile)

    req = CapabilityRequirement(
        requirement_id="req-1", capability_id="cap-1", level="required"
    )
    matches = await registry.match([req])
    assert isinstance(matches, list)


async def test_capability_registry_get_profile():
    """AgentCapabilityRegistry.get_profile returns None for unknown model."""
    registry = StubAgentCapabilityRegistry()
    assert await registry.get_profile("unknown-model") is None


# ── Model dataclass tests ───────────────────────────────────────────────


def test_agent_state_defaults():
    """AgentState has sensible defaults."""
    s = AgentState(agent_id="a-1", phase="init")
    assert s.step == 0
    assert s.status == "idle"
    assert s.context == {}


def test_agent_checkpoint_defaults():
    """AgentCheckpoint defaults are empty."""
    c = AgentCheckpoint(agent_id="a-1")
    assert c.state is None
    assert c.pending_operations == []


def test_recipe_definition_defaults():
    """RecipeDefinition has expected defaults."""
    r = RecipeDefinition(id="r-1", name="test")
    assert r.version == "1.0"
    assert r.steps == []
    assert r.tools == []
    assert r.sub_recipes == []


def test_acp_session_defaults():
    """ACPSession defaults to active status."""
    s = ACPSession(session_id="s-1", agent_id="a-1")
    assert s.status == "active"
    assert s.capabilities == []


def test_context_source_defaults():
    """ContextSource has zero-value defaults."""
    cs = ContextSource(source_type="system", content="test")
    assert cs.priority == 0
    assert cs.token_count == 0
    assert cs.provenance == ""


def test_context_budget_fields():
    """AssemblyContextBudget stores token allocation."""
    b = AssemblyContextBudget(total_tokens=4096, used=1000, remaining=3096)
    assert b.total_tokens == 4096
    assert b.remaining == 3096


def test_trajectory_step_defaults():
    """TrajectoryStep has zero reward by default."""
    ts = TrajectoryStep(step_id="s-1", action="think")
    assert ts.reward == 0.0
    assert ts.observation == ""


def test_trajectory_defaults():
    """Trajectory has empty defaults."""
    t = Trajectory(trajectory_id="t-1", task="test")
    assert t.steps == []
    assert t.total_reward == 0.0
    assert t.model == ""


def test_trajectory_filter_defaults():
    """TrajectoryFilter defaults allow open-ended filtering."""
    f = TrajectoryFilter()
    assert f.min_reward is None
    assert f.limit == 100


def test_environment_spec_defaults():
    """EnvironmentSpec has empty collections by default."""
    e = EnvironmentSpec(env_id="e-1", env_type="terminal")
    assert e.tools == []
    assert e.dependencies == []
    assert e.security == {}


def test_environment_snapshot_defaults():
    """EnvironmentSnapshot has empty state by default."""
    s = EnvironmentSnapshot(snapshot_id="snap-1", env_id="e-1")
    assert s.state == {}
    assert s.created_at == ""


def test_environment_observation_defaults():
    """AgentEnvironmentObservation defaults to not verifiable."""
    o = AgentEnvironmentObservation(
        env_id="e-1", observation_type="state", content="ok"
    )
    assert o.verifiable is False


def test_capability_defaults():
    """Capability has optional parent_id."""
    c = Capability(capability_id="c-1", name="reasoning")
    assert c.parent_id is None
    assert c.category == ""


def test_capability_requirement_defaults():
    """CapabilityRequirement defaults to required level."""
    r = CapabilityRequirement(requirement_id="r-1", capability_id="c-1")
    assert r.level == "required"
    assert r.constraints == {}


def test_capability_profile_defaults():
    """AgentCapabilityProfile has empty capabilities and scores."""
    p = AgentCapabilityProfile(profile_id="p-1", agent_or_model="opus")
    assert p.capabilities == []
    assert p.scores == {}
