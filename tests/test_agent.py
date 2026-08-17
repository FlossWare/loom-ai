"""Tests for the in-memory agent loop backend with tool-use support.

Covers protocol conformance, agent lifecycle (step/pause/resume/cancel),
tool registration and dynamic selection, async tool execution via a
ToolProvider, result synthesis, operation binding, and edge cases.
"""

from __future__ import annotations

from loom_ai.backends.agent import InMemoryAgentLoop
from loom_ai.contracts_phase6 import AgentLoop
from loom_ai.models import ToolDefinition, ToolResult
from loom_ai.models_phase6 import (
    AgentCheckpoint,
    AgentOperation,
    AgentState,
    AgentTurn,
)
from loom_ai.protocols import ToolProvider

# ── Stub tool provider ────────────────────────────────────────────────────


class StubToolProvider:
    """In-memory tool provider that records calls and returns canned results."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._results: dict[str, ToolResult] = {}
        self._tools: list[ToolDefinition] = []

    def set_result(self, name: str, result: ToolResult) -> None:
        self._results[name] = result

    def add_tool(self, tool: ToolDefinition) -> None:
        self._tools.append(tool)

    async def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools)

    async def call_tool(self, name: str, arguments: dict) -> ToolResult:
        self.calls.append((name, arguments))
        if name in self._results:
            return self._results[name]
        return ToolResult(tool_name=name, output=f"result-{name}")


class ErrorToolProvider:
    """Tool provider that returns errors for every call."""

    async def list_tools(self) -> list[ToolDefinition]:
        return []

    async def call_tool(self, name: str, arguments: dict) -> ToolResult:
        _ = arguments
        return ToolResult(tool_name=name, error=f"{name} failed")


# ── Protocol conformance ──────────────────────────────────────────────────


def test_agent_loop_protocol_conformance():
    """InMemoryAgentLoop satisfies the AgentLoop protocol."""
    assert isinstance(InMemoryAgentLoop(), AgentLoop)


def test_agent_loop_with_tool_provider_conformance():
    """InMemoryAgentLoop with a ToolProvider still satisfies AgentLoop."""
    provider = StubToolProvider()
    assert isinstance(InMemoryAgentLoop(tool_provider=provider), AgentLoop)


def test_stub_tool_provider_conformance():
    """StubToolProvider satisfies the ToolProvider protocol."""
    assert isinstance(StubToolProvider(), ToolProvider)


# ── Agent lifecycle ───────────────────────────────────────────────────────


async def test_step_creates_idle_state():
    """First step on a new agent initialises state and returns a turn."""
    loop = InMemoryAgentLoop()
    turn = await loop.step("agent-1")

    assert isinstance(turn, AgentTurn)
    assert turn.agent_id == "agent-1"
    assert turn.status == "completed"

    state = await loop.state("agent-1")
    assert state.step == 1
    assert state.phase == "step-1"


async def test_multiple_steps_increment():
    """Each step increments the step counter."""
    loop = InMemoryAgentLoop()
    await loop.step("agent-1")
    await loop.step("agent-1")
    turn = await loop.step("agent-1")

    assert turn.agent_id == "agent-1"
    state = await loop.state("agent-1")
    assert state.step == 3


async def test_state_defaults_for_new_agent():
    """Querying state for an unknown agent creates initial state."""
    loop = InMemoryAgentLoop()
    state = await loop.state("new-agent")

    assert isinstance(state, AgentState)
    assert state.agent_id == "new-agent"
    assert state.phase == "init"
    assert state.step == 0
    assert state.status == "idle"


async def test_cancel_active_agent():
    """Cancelling an active agent returns True and sets status."""
    loop = InMemoryAgentLoop()
    await loop.step("agent-1")

    assert await loop.cancel("agent-1") is True
    state = await loop.state("agent-1")
    assert state.status == "cancelled"


async def test_cancel_unknown_agent():
    """Cancelling an unknown agent returns False."""
    loop = InMemoryAgentLoop()
    assert await loop.cancel("nonexistent") is False


async def test_cancel_already_cancelled():
    """Cancelling an already-cancelled agent returns False."""
    loop = InMemoryAgentLoop()
    await loop.step("agent-1")
    await loop.cancel("agent-1")
    assert await loop.cancel("agent-1") is False


async def test_step_after_cancel():
    """Stepping a cancelled agent returns a cancelled turn."""
    loop = InMemoryAgentLoop()
    await loop.step("agent-1")
    await loop.cancel("agent-1")

    turn = await loop.step("agent-1")
    assert turn.status == "cancelled"


async def test_max_steps_limit():
    """Agent moves to done status after reaching max_steps."""
    loop = InMemoryAgentLoop(max_steps=3)
    await loop.step("agent-1")
    await loop.step("agent-1")
    turn = await loop.step("agent-1")

    assert turn.status == "completed"
    state = await loop.state("agent-1")
    assert state.status == "done"

    done_turn = await loop.step("agent-1")
    assert done_turn.status == "done"


# ── Pause / Resume ────────────────────────────────────────────────────────


async def test_pause_and_resume():
    """Pause captures state; resume restores it."""
    loop = InMemoryAgentLoop()
    await loop.step("agent-1")
    await loop.step("agent-1")

    checkpoint = await loop.pause("agent-1")
    assert isinstance(checkpoint, AgentCheckpoint)
    assert checkpoint.agent_id == "agent-1"
    assert checkpoint.state is not None
    assert checkpoint.state.step == 2
    assert checkpoint.state.status == "paused"

    state = await loop.resume(checkpoint)
    assert isinstance(state, AgentState)
    assert state.agent_id == "agent-1"
    assert state.step == 2
    assert state.status == "idle"


async def test_resume_without_state():
    """Resuming a checkpoint with no state creates fresh initial state."""
    loop = InMemoryAgentLoop()
    checkpoint = AgentCheckpoint(agent_id="agent-fresh")

    state = await loop.resume(checkpoint)
    assert state.agent_id == "agent-fresh"
    assert state.step == 0
    assert state.status == "idle"


async def test_pause_records_pending_operations():
    """Pause includes names of registered operations."""
    loop = InMemoryAgentLoop()
    op = AgentOperation(name="model_call", operation_type="llm")
    loop.register_agent_operation("agent-1", op)
    await loop.step("agent-1")

    checkpoint = await loop.pause("agent-1")
    assert "model_call" in checkpoint.pending_operations


# ── Operations ────────────────────────────────────────────────────────────


async def test_register_and_list_operations():
    """Operations registered to an agent are returned by list_operations."""
    loop = InMemoryAgentLoop()
    op1 = AgentOperation(name="think", operation_type="reasoning")
    op2 = AgentOperation(name="search", operation_type="tool_call")
    loop.register_agent_operation("agent-1", op1)
    loop.register_agent_operation("agent-1", op2)

    ops = await loop.list_operations("agent-1")
    assert len(ops) == 2
    names = {o.name for o in ops}
    assert names == {"think", "search"}


async def test_replace_existing_operation():
    """Registering an operation with an existing name replaces it."""
    loop = InMemoryAgentLoop()
    op_v1 = AgentOperation(
        name="search", operation_type="tool_call", config={"v": 1}
    )
    op_v2 = AgentOperation(
        name="search", operation_type="tool_call", config={"v": 2}
    )
    loop.register_agent_operation("agent-1", op_v1)
    loop.register_agent_operation("agent-1", op_v2)

    ops = await loop.list_operations("agent-1")
    assert len(ops) == 1
    assert ops[0].config == {"v": 2}


async def test_list_operations_empty_for_unknown_agent():
    """list_operations returns empty list for unknown agent."""
    loop = InMemoryAgentLoop()
    ops = await loop.list_operations("unknown")
    assert ops == []


async def test_step_runs_registered_operations():
    """Step executes registered operations and records their names."""
    loop = InMemoryAgentLoop()
    op = AgentOperation(name="reason", operation_type="reasoning")
    loop.register_agent_operation("agent-1", op)

    turn = await loop.step("agent-1")
    assert "reason" in turn.operations


# ── Tool registration and selection ───────────────────────────────────────


def test_register_tool():
    """Registered tools are available via available_tools."""
    loop = InMemoryAgentLoop()
    tool = ToolDefinition(name="calculator", description="math operations")
    loop.register_tool(tool)

    tools = loop.available_tools()
    assert len(tools) == 1
    assert tools[0].name == "calculator"


def test_register_multiple_tools():
    """Multiple tools can be registered."""
    loop = InMemoryAgentLoop()
    loop.register_tool(ToolDefinition(name="calc", description="math"))
    loop.register_tool(ToolDefinition(name="search", description="web search"))

    assert len(loop.available_tools()) == 2


def test_register_tool_replaces_by_name():
    """Registering a tool with an existing name replaces the definition."""
    loop = InMemoryAgentLoop()
    loop.register_tool(ToolDefinition(name="calc", description="v1"))
    loop.register_tool(ToolDefinition(name="calc", description="v2"))

    tools = loop.available_tools()
    assert len(tools) == 1
    assert tools[0].description == "v2"


async def test_select_tools_by_name():
    """select_tools filters by name when names are provided."""
    loop = InMemoryAgentLoop()
    loop.register_tool(ToolDefinition(name="calc", description="math"))
    loop.register_tool(ToolDefinition(name="search", description="web"))
    loop.register_tool(ToolDefinition(name="code", description="run code"))

    selected = await loop.select_tools(names=["calc", "code"])
    assert len(selected) == 2
    names = {t.name for t in selected}
    assert names == {"calc", "code"}


async def test_select_tools_all():
    """select_tools returns all tools when names is None."""
    loop = InMemoryAgentLoop()
    loop.register_tool(ToolDefinition(name="calc", description="math"))
    loop.register_tool(ToolDefinition(name="search", description="web"))

    selected = await loop.select_tools()
    assert len(selected) == 2


async def test_select_tools_ignores_unknown_names():
    """select_tools silently skips names that are not registered."""
    loop = InMemoryAgentLoop()
    loop.register_tool(ToolDefinition(name="calc", description="math"))

    selected = await loop.select_tools(names=["calc", "nonexistent"])
    assert len(selected) == 1
    assert selected[0].name == "calc"


# ── Tool execution via ToolProvider ──────────────────────────────────────


async def test_execute_tool_dispatches_to_provider():
    """execute_tool delegates to the configured ToolProvider."""
    provider = StubToolProvider()
    provider.set_result(
        "calc", ToolResult(tool_name="calc", output=42)
    )
    loop = InMemoryAgentLoop(tool_provider=provider)

    result = await loop.execute_tool("calc", {"expr": "6*7"})
    assert result.tool_name == "calc"
    assert result.output == 42
    assert provider.calls == [("calc", {"expr": "6*7"})]


async def test_execute_tool_without_provider_raises():
    """execute_tool raises ValueError when no provider is configured."""
    loop = InMemoryAgentLoop()
    try:
        await loop.execute_tool("calc", {})
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "no tool provider" in str(exc)


async def test_step_executes_tool_call_operations():
    """Step with tool_call operations dispatches to the ToolProvider."""
    provider = StubToolProvider()
    provider.set_result(
        "search", ToolResult(tool_name="search", output={"results": ["a", "b"]})
    )
    loop = InMemoryAgentLoop(tool_provider=provider)

    op = AgentOperation(
        name="web_search",
        operation_type="tool_call",
        config={"tool_name": "search", "arguments": {"q": "loom-ai"}},
    )
    loop.register_agent_operation("agent-1", op)

    turn = await loop.step("agent-1")
    assert turn.status == "completed"
    assert "web_search" in turn.operations
    assert turn.output_data["web_search"]["output"] == {"results": ["a", "b"]}
    assert provider.calls == [("search", {"q": "loom-ai"})]


async def test_step_tool_call_uses_op_name_as_tool_name():
    """When config has no tool_name, the operation name is used."""
    provider = StubToolProvider()
    loop = InMemoryAgentLoop(tool_provider=provider)

    op = AgentOperation(
        name="calculator",
        operation_type="tool_call",
        config={"arguments": {"x": 1}},
    )
    loop.register_agent_operation("agent-1", op)

    await loop.step("agent-1")
    assert provider.calls[0][0] == "calculator"


async def test_step_tool_error_marks_turn_failed():
    """A tool error during step marks the turn as failed."""
    provider = ErrorToolProvider()
    loop = InMemoryAgentLoop(tool_provider=provider)

    op = AgentOperation(name="broken", operation_type="tool_call")
    loop.register_agent_operation("agent-1", op)

    turn = await loop.step("agent-1")
    assert turn.status == "failed"
    assert turn.output_data["broken"]["error"] == "broken failed"


async def test_step_without_tool_provider_skips_tool_calls():
    """Tool-call operations are skipped when no provider is configured."""
    loop = InMemoryAgentLoop()

    op = AgentOperation(name="search", operation_type="tool_call")
    loop.register_agent_operation("agent-1", op)

    turn = await loop.step("agent-1")
    assert turn.status == "completed"
    assert "search" in turn.operations
    assert "search" not in turn.output_data


async def test_step_multiple_tool_calls():
    """Multiple tool-call operations are executed in order."""
    provider = StubToolProvider()
    provider.set_result("a", ToolResult(tool_name="a", output="result-a"))
    provider.set_result("b", ToolResult(tool_name="b", output="result-b"))
    loop = InMemoryAgentLoop(tool_provider=provider)

    loop.register_agent_operation(
        "agent-1",
        AgentOperation(
            name="op_a", operation_type="tool_call",
            config={"tool_name": "a", "arguments": {}},
        ),
    )
    loop.register_agent_operation(
        "agent-1",
        AgentOperation(
            name="op_b", operation_type="tool_call",
            config={"tool_name": "b", "arguments": {}},
        ),
    )

    turn = await loop.step("agent-1")
    assert turn.status == "completed"
    assert turn.output_data["op_a"]["output"] == "result-a"
    assert turn.output_data["op_b"]["output"] == "result-b"
    assert len(provider.calls) == 2


# ── Turn history ──────────────────────────────────────────────────────────


async def test_get_turns_records_history():
    """get_turns returns the full turn history for an agent."""
    loop = InMemoryAgentLoop()
    await loop.step("agent-1")
    await loop.step("agent-1")

    turns = loop.get_turns("agent-1")
    assert len(turns) == 2
    assert all(t.agent_id == "agent-1" for t in turns)


async def test_get_turns_empty_for_unknown():
    """get_turns returns empty list for unknown agent."""
    loop = InMemoryAgentLoop()
    assert loop.get_turns("unknown") == []


async def test_turn_has_duration():
    """Each turn records a non-negative duration."""
    loop = InMemoryAgentLoop()
    turn = await loop.step("agent-1")
    assert turn.duration_ms >= 0.0


async def test_turn_ids_are_unique():
    """Each turn gets a unique id."""
    loop = InMemoryAgentLoop()
    t1 = await loop.step("agent-1")
    t2 = await loop.step("agent-1")
    assert t1.turn_id != t2.turn_id


# ── Edge cases ────────────────────────────────────────────────────────────


async def test_independent_agents():
    """State for different agents is independent."""
    loop = InMemoryAgentLoop()
    await loop.step("a")
    await loop.step("a")
    await loop.step("b")

    state_a = await loop.state("a")
    state_b = await loop.state("b")
    assert state_a.step == 2
    assert state_b.step == 1


async def test_cancel_does_not_affect_other_agents():
    """Cancelling one agent does not affect another."""
    loop = InMemoryAgentLoop()
    await loop.step("a")
    await loop.step("b")
    await loop.cancel("a")

    state_a = await loop.state("a")
    state_b = await loop.state("b")
    assert state_a.status == "cancelled"
    assert state_b.status == "idle"


async def test_resume_then_step():
    """After resuming from a checkpoint, stepping continues from the saved step."""
    loop = InMemoryAgentLoop()
    await loop.step("agent-1")
    await loop.step("agent-1")
    checkpoint = await loop.pause("agent-1")

    new_loop = InMemoryAgentLoop()
    state = await new_loop.resume(checkpoint)
    assert state.step == 2

    turn = await new_loop.step("agent-1")
    assert turn.status == "completed"
    new_state = await new_loop.state("agent-1")
    assert new_state.step == 3


async def test_pause_sets_created_at():
    """Checkpoint created_at is populated."""
    loop = InMemoryAgentLoop()
    await loop.step("agent-1")
    checkpoint = await loop.pause("agent-1")
    assert checkpoint.created_at != ""
