"""In-memory backends for Phase 6 agent architecture protocols.

All classes use structural subtyping (no Protocol inheritance) and store
data in plain dicts/lists.  Zero external dependencies -- stdlib only.

Classes
-------
InMemoryRecipeExecutor          -- dict-backed recipe storage and execution
InMemoryACPAdapter              -- session management with message passing
InMemoryContextAssembler        -- context construction with token budgeting
InMemoryTrajectoryStore         -- trajectory CRUD with search and export
InMemoryAgentEnvironment        -- environment lifecycle state machine
InMemoryAgentCapabilityRegistry -- capability/profile registry with matching
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from loom_ai.models_agent import (
    ACPEvent,
    ACPMessage,
    ACPSession,
    AgentCapabilityProfile,
    AgentEnvironmentObservation,
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
)

_CHARS_PER_TOKEN = 4


def _make_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


# ══════════════════════════════════════════════════════════════════════════
# RecipeExecutor (#60)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryRecipeExecutor:
    """Dict-backed recipe storage and execution."""

    def __init__(self) -> None:
        self._recipes: dict[str, RecipeDefinition] = {}

    async def execute(
        self,
        recipe: RecipeDefinition,
        *,
        inputs: dict | None = None,
    ) -> RecipeResult:
        errors = await self.validate(recipe)
        if errors:
            return RecipeResult(
                recipe_id=recipe.id,
                run_id=_make_id(),
                status="failed",
                outputs={"errors": errors},
            )

        self._recipes[recipe.id] = recipe
        start = time.monotonic()
        resolved_inputs = inputs or {}

        steps_completed: list[str] = []
        for step in recipe.steps:
            steps_completed.append(step)

        elapsed_ms = (time.monotonic() - start) * 1000

        return RecipeResult(
            recipe_id=recipe.id,
            run_id=_make_id(),
            status="completed",
            outputs={"inputs_received": resolved_inputs},
            steps_completed=steps_completed,
            duration_ms=elapsed_ms,
        )

    async def validate(self, recipe: RecipeDefinition) -> list[str]:
        errors: list[str] = []
        if not recipe.id:
            errors.append("recipe id is required")
        if not recipe.name:
            errors.append("recipe name is required")
        for param in recipe.parameters:
            if param.required and param.default is None and not param.name:
                errors.append("parameter missing name")
        return errors

    async def list_recipes(self) -> list[RecipeDefinition]:
        return list(self._recipes.values())

    async def get_recipe(self, recipe_id: str) -> RecipeDefinition | None:
        return self._recipes.get(recipe_id)


# ══════════════════════════════════════════════════════════════════════════
# ACPAdapter (#61)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryACPAdapter:
    """Session management with message passing and event tracking."""

    def __init__(self) -> None:
        self._sessions: dict[str, ACPSession] = {}
        self._events: dict[str, list[ACPEvent]] = {}
        self._messages: dict[str, list[ACPMessage]] = {}

    async def create_session(
        self,
        agent_id: str,
        *,
        capabilities: list[str] | None = None,
        metadata: dict | None = None,
    ) -> ACPSession:
        session_id = _make_id()
        session = ACPSession(
            session_id=session_id,
            agent_id=agent_id,
            status="active",
            capabilities=capabilities or [],
            created_at=_now_iso(),
            metadata=metadata or {},
        )
        self._sessions[session_id] = session
        self._events[session_id] = []
        self._messages[session_id] = []

        self._emit_event(session_id, "session_created")
        return session

    async def send_message(self, session_id: str, message: ACPMessage) -> ACPMessage:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"session {session_id} not found")
        if session.status != "active":
            raise ValueError(f"session {session_id} is {session.status}")

        self._messages[session_id].append(message)
        self._emit_event(session_id, "message_sent", {"message_id": message.message_id})

        response = ACPMessage(
            message_id=_make_id(),
            session_id=session_id,
            content=f"ack:{message.message_id}",
            message_type="ack",
        )
        self._messages[session_id].append(response)
        self._emit_event(
            session_id,
            "message_received",
            {"message_id": response.message_id},
        )
        return response

    async def cancel_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None or session.status != "active":
            return False
        session.status = "cancelled"
        self._emit_event(session_id, "session_cancelled")
        return True

    async def get_session(self, session_id: str) -> ACPSession | None:
        return self._sessions.get(session_id)

    async def list_events(
        self, session_id: str, *, since_sequence: int = 0
    ) -> list[ACPEvent]:
        events = self._events.get(session_id, [])
        return [e for e in events if e.sequence >= since_sequence]

    def _emit_event(
        self,
        session_id: str,
        event_type: str,
        data: dict | None = None,
    ) -> None:
        events = self._events.setdefault(session_id, [])
        seq = len(events)
        events.append(
            ACPEvent(
                event_type=event_type,
                session_id=session_id,
                data=data or {},
                sequence=seq,
            )
        )


# ══════════════════════════════════════════════════════════════════════════
# ContextAssembler (#62)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryContextAssembler:
    """Context construction with token budgeting (4 chars/token estimate)."""

    async def assemble(
        self,
        sources: list[ContextSource],
        *,
        max_tokens: int | None = None,
    ) -> ContextSnapshot:
        sorted_sources = sorted(sources, key=lambda s: s.priority, reverse=True)

        kept: list[ContextSource] = []
        total_tokens = 0

        for source in sorted_sources:
            tokens = source.token_count or _estimate_tokens(source.content)
            if max_tokens is not None and total_tokens + tokens > max_tokens:
                # Truncate content to fit remaining budget
                remaining = max_tokens - total_tokens
                if remaining > 0:
                    truncated_chars = remaining * _CHARS_PER_TOKEN
                    kept.append(
                        ContextSource(
                            source_type=source.source_type,
                            content=source.content[:truncated_chars],
                            priority=source.priority,
                            token_count=remaining,
                            provenance=source.provenance,
                            metadata=source.metadata,
                        )
                    )
                    total_tokens = max_tokens
                break
            kept.append(source)
            total_tokens += tokens

        budget = AssemblyContextBudget(
            total_tokens=max_tokens or total_tokens,
            used=total_tokens,
            remaining=(max_tokens - total_tokens) if max_tokens else 0,
        )

        return ContextSnapshot(
            sources=kept,
            budget=budget,
            total_tokens=total_tokens,
        )

    async def compact(
        self,
        snapshot: ContextSnapshot,
        *,
        target_tokens: int,
    ) -> ContextSnapshot:
        if snapshot.total_tokens <= target_tokens:
            return snapshot

        result = await self.assemble(snapshot.sources, max_tokens=target_tokens)
        result.compacted = True
        return result

    async def add_source(
        self, snapshot: ContextSnapshot, source: ContextSource
    ) -> ContextSnapshot:
        combined = list(snapshot.sources) + [source]
        max_tokens = snapshot.budget.total_tokens if snapshot.budget else None
        return await self.assemble(combined, max_tokens=max_tokens)

    async def replay(self, snapshot: ContextSnapshot) -> list[dict]:
        entries: list[dict] = []
        for i, source in enumerate(snapshot.sources):
            entries.append(
                {
                    "step": i,
                    "action": "include",
                    "source_type": source.source_type,
                    "priority": source.priority,
                    "token_count": source.token_count
                    or _estimate_tokens(source.content),
                    "provenance": source.provenance,
                }
            )
        if snapshot.compacted:
            entries.append({"step": len(entries), "action": "compact"})
        return entries


# ══════════════════════════════════════════════════════════════════════════
# TrajectoryStore (#63)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryTrajectoryStore:
    """Dict-backed trajectory CRUD with substring search and JSONL export."""

    def __init__(self) -> None:
        self._trajectories: dict[str, Trajectory] = {}

    async def record(self, trajectory: Trajectory) -> str:
        tid = trajectory.trajectory_id or _make_id()
        trajectory.trajectory_id = tid
        self._trajectories[tid] = trajectory
        return tid

    async def get(self, trajectory_id: str) -> Trajectory | None:
        return self._trajectories.get(trajectory_id)

    async def search(
        self, *, task: str | None = None, limit: int = 10
    ) -> list[Trajectory]:
        results = list(self._trajectories.values())
        if task is not None:
            task_lower = task.lower()
            results = [t for t in results if task_lower in t.task.lower()]
        return results[:limit]

    async def filter(self, criteria: TrajectoryFilter) -> list[Trajectory]:
        results: list[Trajectory] = []
        for t in self._trajectories.values():
            if criteria.min_reward is not None and t.total_reward < criteria.min_reward:
                continue
            if criteria.max_reward is not None and t.total_reward > criteria.max_reward:
                continue
            if criteria.outcome is not None and t.outcome != criteria.outcome:
                continue
            if criteria.model is not None and t.model != criteria.model:
                continue
            if (
                criteria.task_pattern is not None
                and criteria.task_pattern.lower() not in t.task.lower()
            ):
                continue
            results.append(t)
            if len(results) >= criteria.limit:
                break
        return results

    async def replay(self, trajectory_id: str) -> list[dict]:
        trajectory = self._trajectories.get(trajectory_id)
        if trajectory is None:
            return []
        return [
            {
                "step": i,
                "step_id": step.step_id,
                "action": step.action,
                "observation": step.observation,
                "reward": step.reward,
            }
            for i, step in enumerate(trajectory.steps)
        ]

    async def export(
        self,
        trajectory_ids: list[str],
        *,
        format: str = "jsonl",
    ) -> Any:
        records: list[dict] = []
        for tid in trajectory_ids:
            t = self._trajectories.get(tid)
            if t is None:
                continue
            records.append(
                {
                    "trajectory_id": t.trajectory_id,
                    "task": t.task,
                    "outcome": t.outcome,
                    "total_reward": t.total_reward,
                    "model": t.model,
                    "steps": [
                        {
                            "step_id": s.step_id,
                            "action": s.action,
                            "observation": s.observation,
                            "reward": s.reward,
                        }
                        for s in t.steps
                    ],
                }
            )

        if format == "jsonl":
            return "\n".join(json.dumps(r) for r in records)
        return records


# ══════════════════════════════════════════════════════════════════════════
# AgentEnvironment (#64)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryAgentEnvironment:
    """Environment lifecycle state machine."""

    def __init__(self) -> None:
        self._envs: dict[str, dict] = {}
        self._specs: dict[str, EnvironmentSpec] = {}
        self._snapshots: dict[str, list[EnvironmentSnapshot]] = {}

    async def create(self, spec: EnvironmentSpec) -> str:
        env_id = spec.env_id or _make_id()
        self._specs[env_id] = spec
        self._envs[env_id] = {
            "status": "created",
            "state": dict(spec.config),
            "created_at": _now_iso(),
        }
        self._snapshots[env_id] = []
        return env_id

    async def reset(self, env_id: str) -> None:
        if env_id not in self._envs:
            raise ValueError(f"environment {env_id} not found")
        spec = self._specs[env_id]
        self._envs[env_id] = {
            "status": "created",
            "state": dict(spec.config),
            "created_at": _now_iso(),
        }

    async def snapshot(self, env_id: str) -> EnvironmentSnapshot:
        env = self._envs.get(env_id)
        if env is None:
            raise ValueError(f"environment {env_id} not found")

        snap = EnvironmentSnapshot(
            snapshot_id=_make_id(),
            env_id=env_id,
            state=dict(env["state"]),
            created_at=_now_iso(),
        )
        self._snapshots[env_id].append(snap)
        return snap

    async def restore(self, snapshot: EnvironmentSnapshot) -> None:
        env = self._envs.get(snapshot.env_id)
        if env is None:
            raise ValueError(f"environment {snapshot.env_id} not found")
        env["state"] = dict(snapshot.state)
        env["status"] = "created"

    async def observe(self, env_id: str) -> AgentEnvironmentObservation:
        env = self._envs.get(env_id)
        if env is None:
            raise ValueError(f"environment {env_id} not found")
        return AgentEnvironmentObservation(
            env_id=env_id,
            observation_type="state",
            content=json.dumps(env["state"]),
            verifiable=True,
        )

    async def teardown(self, env_id: str) -> bool:
        if env_id not in self._envs:
            return False
        del self._envs[env_id]
        self._specs.pop(env_id, None)
        self._snapshots.pop(env_id, None)
        return True


# ══════════════════════════════════════════════════════════════════════════
# AgentCapabilityRegistry (#65)
# ══════════════════════════════════════════════════════════════════════════


class InMemoryAgentCapabilityRegistry:
    """Dict-backed capability/profile registry with requirement matching."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._profiles: dict[str, AgentCapabilityProfile] = {}

    async def register_capability(self, capability: Capability) -> None:
        self._capabilities[capability.capability_id] = capability

    async def get_capability(self, capability_id: str) -> Capability | None:
        return self._capabilities.get(capability_id)

    async def list_capabilities(
        self, *, category: str | None = None
    ) -> list[Capability]:
        caps = list(self._capabilities.values())
        if category is not None:
            caps = [c for c in caps if c.category == category]
        return caps

    async def register_profile(self, profile: AgentCapabilityProfile) -> None:
        self._profiles[profile.agent_or_model] = profile

    async def match(
        self, requirements: list[CapabilityRequirement]
    ) -> list[AgentCapabilityProfile]:
        required_ids = {r.capability_id for r in requirements}
        return [
            p
            for p in self._profiles.values()
            if required_ids.issubset(set(p.capabilities))
        ]

    async def get_profile(self, agent_or_model: str) -> AgentCapabilityProfile | None:
        return self._profiles.get(agent_or_model)
