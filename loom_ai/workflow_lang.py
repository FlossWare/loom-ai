"""Declarative workflow model and compiler for Loom.

The workflow model is intentionally broader than a CI pipeline.  A workflow
expresses a goal, facts, constraints, participants, and an execution graph.
A graph may contain sequential or parallel work, verification gates, human
gates, and adaptive policy metadata.  The current compiler targets Loom's
existing :class:`ExecutionPlan` so this layer can be adopted without replacing
the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loom_ai.models import ExecutionPlan, Task


class WorkflowValidationError(ValueError):
    """Raised when a workflow definition cannot be compiled safely."""


@dataclass(frozen=True)
class WorkflowNode:
    """A unit in a workflow graph."""

    id: str
    task: str
    agent: str | None = None
    depends_on: tuple[str, ...] = ()
    condition: str | None = None
    retry: int = 0
    timeout_seconds: float = 0.0
    human_approval: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    """A declarative AI workflow.

    ``goal`` is the desired outcome rather than an instruction to execute a
    fixed sequence.  ``nodes`` describe known work and dependencies.  The
    policy dictionary is deliberately open so planning, arbitration, budget,
    and provider selection can evolve without changing the core model.
    """

    name: str
    goal: str
    nodes: list[WorkflowNode] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    policy: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise WorkflowValidationError("workflow node ids must be unique")
        known = set(ids)
        for node in self.nodes:
            unknown = set(node.depends_on) - known
            if unknown:
                raise WorkflowValidationError(
                    f"node {node.id!r} references unknown dependencies: "
                    + ", ".join(sorted(unknown))
                )
            if node.retry < 0:
                raise WorkflowValidationError(f"node {node.id!r} has negative retry count")
            if node.timeout_seconds < 0:
                raise WorkflowValidationError(f"node {node.id!r} has negative timeout")

        # Kahn-style cycle check.  We keep this local so validation works even
        # before a runtime/execution backend is configured.
        remaining = {node.id: set(node.depends_on) for node in self.nodes}
        while remaining:
            ready = {node_id for node_id, deps in remaining.items() if not deps}
            if not ready:
                raise WorkflowValidationError(
                    "workflow contains a dependency cycle: "
                    + ", ".join(sorted(remaining))
                )
            for node_id in ready:
                remaining.pop(node_id)
            for deps in remaining.values():
                deps.difference_update(ready)

    def to_execution_plan(self, plan_id: str | None = None) -> ExecutionPlan:
        """Compile the declarative graph to Loom's existing execution model."""
        self.validate()
        return ExecutionPlan(
            id=plan_id or self.name,
            tasks=[
                Task(
                    id=node.id,
                    name=node.task,
                    description=node.task,
                    dependencies=list(node.depends_on),
                    retries_remaining=node.retry,
                    timeout_seconds=node.timeout_seconds,
                    input_data={
                        "goal": self.goal,
                        "agent": node.agent,
                        "condition": node.condition,
                        "human_approval": node.human_approval,
                        "facts": self.facts,
                        "constraints": self.constraints,
                        "policy": self.policy,
                        "metadata": node.metadata,
                    },
                )
                for node in self.nodes
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a serialization-friendly workflow representation."""
        self.validate()
        return {
            "name": self.name,
            "goal": self.goal,
            "facts": self.facts,
            "constraints": self.constraints,
            "policy": self.policy,
            "metadata": self.metadata,
            "nodes": [
                {
                    "id": node.id,
                    "task": node.task,
                    "agent": node.agent,
                    "depends_on": list(node.depends_on),
                    "condition": node.condition,
                    "retry": node.retry,
                    "timeout_seconds": node.timeout_seconds,
                    "human_approval": node.human_approval,
                    "metadata": node.metadata,
                }
                for node in self.nodes
            ],
        }


class WorkflowBuilder:
    """Small Python API used by applications and language frontends."""

    def __init__(self, name: str, goal: str):
        self._workflow = WorkflowDefinition(name=name, goal=goal)

    def fact(self, name: str, value: Any) -> "WorkflowBuilder":
        self._workflow.facts[name] = value
        return self

    def constraint(self, expression: str) -> "WorkflowBuilder":
        self._workflow.constraints.append(expression)
        return self

    def policy(self, name: str, value: Any) -> "WorkflowBuilder":
        self._workflow.policy[name] = value
        return self

    def node(
        self,
        node_id: str,
        task: str,
        *,
        agent: str | None = None,
        depends_on: list[str] | tuple[str, ...] = (),
        condition: str | None = None,
        retry: int = 0,
        timeout_seconds: float = 0.0,
        human_approval: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> "WorkflowBuilder":
        self._workflow.nodes.append(
            WorkflowNode(
                id=node_id,
                task=task,
                agent=agent,
                depends_on=tuple(depends_on),
                condition=condition,
                retry=retry,
                timeout_seconds=timeout_seconds,
                human_approval=human_approval,
                metadata=metadata or {},
            )
        )
        return self

    def build(self) -> WorkflowDefinition:
        self._workflow.validate()
        return self._workflow
