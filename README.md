# loom-ai

**Loom is the AI-first execution substrate for turning declarative intent into verified change.**

Loom is not a coding-agent product. Crush, Claude Code, Codex, Cursor, and other clients consume Loom through external interfaces. The runtime itself is deliberately small.

## Core execution model

```text
Intent
  -> Arbiter
      -> Worker
      -> Worker
      -> Arbiter
  -> evidence
  -> evaluation
  -> result
```

The fundamental executable abstraction is **Worker**. An **Arbiter is a Worker that coordinates Workers**, so nesting is ordinary composition.

## Architectural boundaries

Loom owns Intent, Worker and Arbiter execution, explicit execution state, evidence collection, task-level orchestration, and integration points for evaluation, Knowledge, strategies, and external capabilities.

Dedicated repositories own capability implementations:

- `model-gateway`: provider/model invocation, resources, routing, credentials, prompt caching
- `evaluation`: evaluation and reward implementations
- `strategy`: interchangeable decision and optimization strategies
- `knowledge`: durable versioned knowledge
- `storage`, `retrieval`, `rag`, `scraping`, `chunking`, `structured-output`: reusable capabilities
- `budget`, `cache`, `conversation`, `streaming`, `observability`, `resilience`, `security`: cross-cutting capabilities
- `loom-setup`: installation and runtime setup
- `loom-client-setup`: external client configuration

Loom must not grow parallel implementations of those systems merely because it can compose them.

## Hard constraints

Authorization, policy, safety, budget, quota, rate, availability, and capability constraints are authoritative. Learned strategies optimize only inside the feasible set.

```text
request -> candidates -> hard constraints -> feasible set
        -> selection strategy -> invocation -> outcome
        -> evaluation/reward -> strategy/Knowledge update
```

## Development

```bash
python -m ruff format --check .
python -m ruff check .
python -m pytest -q
python -m build --wheel --sdist
```

Run the core dogfood gate with `./scripts/dogfood.sh`.

## License

Apache-2.0
