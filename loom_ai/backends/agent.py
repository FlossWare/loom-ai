"""In-memory agent loop backend with tool-use support for loom-ai.

Implements the :class:`~loom_ai.contracts_phase6.AgentLoop` protocol via
structural subtyping.  An optional :class:`~loom_ai.protocols.ToolProvider`
enables dynamic tool registration, selection, and async execution with
result synthesis.

All data is stored in-process dictionaries and is lost on exit.
Zero external dependencies -- stdlib only.

Classes
-------
InMemoryAgentLoop  -- dict-backed agent loop with tool-use support
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from loom_ai.models import ToolDefinition, ToolResult
from loom_ai.models_phase6 import (
    AgentCheckpoint,
    AgentOperation,
    AgentState,
    AgentTurn,
)

if TYPE_CHECKING:
    from loom_ai.protocols import ToolProvider


class InMemoryAgentLoop:
    """Dict-backed agent loop with tool registration and execution.

    Satisfies :class:`~loom_ai.contracts_phase6.AgentLoop` via structural
    subtyping.  When a :class:`~loom_ai.protocols.ToolProvider` is
    supplied, ``tool_call`` operations are dispatched to it during
    :meth:`step`.

    Parameters
    ----------
    tool_provider:
        Optional tool backend for executing tool-call operations.
    max_steps:
        Safety limit on the number of steps per agent before the loop
        moves to ``"done"`` status.  Prevents runaway loops.
    """

    def __init__(
        self,
        *,
        tool_provider: ToolProvider | None = None,
        max_steps: int = 100,
    ) -> None:
        self._tool_provider = tool_provider
        self._max_steps = max_steps

        self._states: dict[str, AgentState] = {}
        self._operations: dict[str, list[AgentOperation]] = {}
        self._turns: dict[str, list[AgentTurn]] = {}

        self._registered_tools: dict[str, ToolDefinition] = {}

    # -- AgentLoop protocol ----------------------------------------------------

    async def step(self, agent_id: str) -> AgentTurn:
        state = self._ensure_state(agent_id)

        if state.status == "done":
            return AgentTurn(
                turn_id=self._make_id(),
                agent_id=agent_id,
                status="done",
            )

        if state.status == "cancelled":
            return AgentTurn(
                turn_id=self._make_id(),
                agent_id=agent_id,
                status="cancelled",
            )

        state.status = "running"
        state.step += 1

        start = time.monotonic()
        operations_run: list[str] = []
        output_data: dict[str, Any] = {}
        turn_status = "completed"

        agent_ops = self._operations.get(agent_id, [])
        for op in agent_ops:
            if op.operation_type == "tool_call" and self._tool_provider is not None:
                tool_name = op.config.get("tool_name", op.name)
                tool_args = op.config.get("arguments", {})
                result = await self._tool_provider.call_tool(tool_name, tool_args)
                output_data[op.name] = {
                    "tool_name": result.tool_name,
                    "output": result.output,
                    "error": result.error,
                }
                if result.error:
                    turn_status = "failed"
            operations_run.append(op.name)

        elapsed_ms = (time.monotonic() - start) * 1000

        if state.step >= self._max_steps:
            state.status = "done"
        elif not agent_ops:
            state.status = "idle"
        else:
            state.status = "idle"

        state.phase = f"step-{state.step}"

        turn = AgentTurn(
            turn_id=self._make_id(),
            agent_id=agent_id,
            operations=operations_run,
            output_data=output_data,
            duration_ms=elapsed_ms,
            status=turn_status,
        )

        self._turns.setdefault(agent_id, []).append(turn)
        return turn

    async def pause(self, agent_id: str) -> AgentCheckpoint:
        state = self._ensure_state(agent_id)
        state.status = "paused"

        pending = [op.name for op in self._operations.get(agent_id, [])]
        return AgentCheckpoint(
            agent_id=agent_id,
            state=AgentState(
                agent_id=state.agent_id,
                phase=state.phase,
                step=state.step,
                context=dict(state.context),
                status=state.status,
                created_at=state.created_at,
            ),
            pending_operations=pending,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    async def resume(self, checkpoint: AgentCheckpoint) -> AgentState:
        agent_id = checkpoint.agent_id
        if checkpoint.state is not None:
            restored = AgentState(
                agent_id=agent_id,
                phase=checkpoint.state.phase,
                step=checkpoint.state.step,
                context=dict(checkpoint.state.context),
                status="idle",
                created_at=checkpoint.state.created_at,
            )
        else:
            restored = self._make_initial_state(agent_id)

        self._states[agent_id] = restored
        return restored

    async def cancel(self, agent_id: str) -> bool:
        if agent_id not in self._states:
            return False
        state = self._states[agent_id]
        if state.status in ("done", "cancelled"):
            return False
        state.status = "cancelled"
        return True

    async def state(self, agent_id: str) -> AgentState:
        return self._ensure_state(agent_id)

    async def register_operation(self, operation: AgentOperation) -> None:
        for agent_id, ops in self._operations.items():
            for i, existing in enumerate(ops):
                if existing.name == operation.name:
                    ops[i] = operation
                    return
        self._global_operations.append(operation)

    async def list_operations(self, agent_id: str) -> list[AgentOperation]:
        _ = agent_id
        return list(self._operations.get(agent_id, []))

    # -- Tool management (not part of AgentLoop protocol) ----------------------

    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a tool definition for dynamic selection."""
        self._registered_tools[tool.name] = tool

    def available_tools(self) -> list[ToolDefinition]:
        """Return all registered tool definitions."""
        return list(self._registered_tools.values())

    async def select_tools(
        self, *, names: list[str] | None = None
    ) -> list[ToolDefinition]:
        """Select tools by name, or return all if *names* is ``None``."""
        if names is None:
            return self.available_tools()
        return [
            self._registered_tools[n]
            for n in names
            if n in self._registered_tools
        ]

    async def execute_tool(self, name: str, arguments: dict) -> ToolResult:
        """Execute a tool through the tool provider.

        Raises ``ValueError`` when no tool provider is configured.
        """
        if self._tool_provider is None:
            raise ValueError("no tool provider configured")
        return await self._tool_provider.call_tool(name, arguments)

    def register_agent_operation(
        self, agent_id: str, operation: AgentOperation
    ) -> None:
        """Bind an operation to a specific agent."""
        ops = self._operations.setdefault(agent_id, [])
        for i, existing in enumerate(ops):
            if existing.name == operation.name:
                ops[i] = operation
                return
        ops.append(operation)

    def get_turns(self, agent_id: str) -> list[AgentTurn]:
        """Return recorded turns for *agent_id*."""
        return list(self._turns.get(agent_id, []))

    # -- internal helpers ------------------------------------------------------

    @property
    def _global_operations(self) -> list[AgentOperation]:
        """Lazy-init list for operations registered without an agent id."""
        if not hasattr(self, "_global_ops"):
            self._global_ops: list[AgentOperation] = []
        return self._global_ops

    def _ensure_state(self, agent_id: str) -> AgentState:
        if agent_id not in self._states:
            self._states[agent_id] = self._make_initial_state(agent_id)
        return self._states[agent_id]

    @staticmethod
    def _make_initial_state(agent_id: str) -> AgentState:
        return AgentState(
            agent_id=agent_id,
            phase="init",
            step=0,
            status="idle",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _make_id() -> str:
        return str(uuid.uuid4())
