# Loom core dogfood

The qualification target is the canonical runtime, not the retired client/server/backend stack.

## Baseline

Run:

```bash
./scripts/dogfood.sh
```

The script creates an isolated virtual environment, installs the small development dependency set, checks formatting and linting, runs the core tests, builds the package, and executes an Intent -> Arbiter -> Worker smoke path.

No provider credentials, PostgreSQL, Redis, OrientDB, Podman, or local model server are required for the core qualification gate.

## What this proves

The baseline gate proves that:

1. `Intent` can represent a declarative goal.
2. `Worker` can execute against explicit `WorkerContext` state.
3. `Arbiter` can compose Workers using the same Worker contract.
4. Evidence survives the Worker result boundary.
5. Evaluation can drive completion without introducing another orchestration abstraction.
6. The package builds independently of provider and infrastructure implementations.

Provider/model dogfood belongs behind `model-gateway` and should be added only after the core substrate is stable.
