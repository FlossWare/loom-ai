# loom-ai

**Loom is a runtime for turning declarative intent into verified changes in state.**

Loom is the canonical FlossWare execution and orchestration runtime. It is not a coding-agent product and does not require Crush, Claude Code, Codex, or Cursor. External clients consume Loom through MCP/API boundaries.

## Core model

```text
Intent
  ↓
Arbiter
  ↓
Workers
  ↓
Tools / Model Gateway / State
  ↓
Evidence + Evaluation
  ↓
complete
  or
revise / retry / replan / escalate
```

The fundamental executable abstraction is **Worker**. An **Arbiter is a Worker that coordinates other Workers**, so composition is recursive.

Intent describes **what** should be accomplished, not how execution must occur. Workers and Arbiters choose execution mechanisms through explicit contracts and strategies.

## Major contracts

- **Intent** - desired outcome, requirements, constraints, and acceptance criteria.
- **Worker** - executable unit of work.
- **Arbiter** - composable Worker that coordinates other Workers.
- **Strategy** - interchangeable decision/optimization implementation.
- **Model Gateway** - provider-neutral model invocation, resources, routing, and selection.
- **Evaluation** - determines how well an outcome satisfies its Intent.
- **Evidence** - records what actually happened.
- **Knowledge** - durable understanding derived from observations, evidence, evaluations, and interaction.
- **Checkpoint** - durable execution position for recovery/replay.

Hard constraints such as authorization, policy, safety, resource feasibility, and explicit budgets are authoritative. Learned strategies optimize only within the feasible set.

## External boundaries

```text
loom-setup
    └── installs/configures Loom

loom-client-setup
    └── configures Crush / Claude Code / Codex / Cursor to consume Loom

model-gateway
    └── providers / models / resources / invocation / selection

knowledge
    └── durable, version-controlled engineering knowledge
```

Loom does not absorb installation, client configuration, provider-specific implementations, or capability-library implementations merely because it can use them.

## Adaptive execution

Loom treats execution as a feedback loop:

```text
Intent → interpretation → execution → evidence → evaluation → interaction → knowledge
                                      ↑                                  │
                                      └──── retry/replan/adaptation ─────┘
```

Human interaction is an observable input to this loop. Explicit approval remains available for authoritative decisions, irreversible actions, and policy gates, but human participation is not required to be modeled as a mandatory workflow stage.

Strategies such as Thompson Sampling, UCB, genetic/evolutionary optimization, Bayesian optimization, and deterministic baselines are implementations of stable strategy contracts. They are not separate architectural primitives.

## Dogfooding

Loom is qualified by exercising the real system, not merely by passing unit tests. The repository contains the dogfood procedure under `docs/DOGFOOD.md` and the executable `scripts/dogfood.sh`.

```bash
./scripts/dogfood.sh
```

The first meaningful dogfood milestone is Loom modifying and verifying Loom through the same runtime used by external clients.

## Backends

Infrastructure is replaceable through stable contracts. Implementations may include in-memory, SQLite, PostgreSQL, Redis, OrientDB, and provider-specific model/embedding implementations. Optional implementations are not mandatory dependencies of the core contracts.

## Development

```bash
python -m ruff format --check .
python -m ruff check .
python -m pytest -q
python -m build --wheel --sdist
```

See `docs/` for contracts, architecture, dogfooding, and implementation details.

## License

Apache-2.0
