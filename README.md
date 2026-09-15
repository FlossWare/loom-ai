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

## Server boundary

Loom provides a minimal HTTP transport around a configured Arbiter. The server translates requests into declarative Intents and returns structured execution results. It does not select models, invoke providers, persist state, or implement other capabilities.

```text
HTTP client
    -> Loom Server
        -> Intent
        -> Arbiter
            -> Workers
        -> result
```

The deployed `loom.service` is the Stage 3 dogfood target. It runs the smallest real-worker pipeline:

```text
POST /intents
    -> Intent
    -> Arbiter
        -> ArtifactWriter
        -> ArtifactVerifier
    -> structured result + evidence
```

The pipeline performs a bounded deterministic filesystem change and verifies the exact result. The artifact location defaults to `/tmp/loom-stage3-artifact.txt` and can be overridden with `LOOM_STAGE3_ARTIFACT`. No model gateway or Crush dependency is involved.

For a local health check:

```bash
curl http://127.0.0.1:18000/health
```

Applications should configure the server with their own Arbiter and Workers when using Loom as a library. The Stage 3 CLI configuration exists specifically to provide a concrete deployed dogfood path.

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

Run the core dogfood gate with `./scripts/dogfood.sh`. Run the deployed Stage 3 gate with `./scripts/dogfood-stage3.sh`; it tests the systemd-managed `loom.service`, real worker execution, verification evidence, and service restart/recovery.

## License

Apache-2.0
