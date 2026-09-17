# loom-ai

**`loom-ai` is an AI-oriented implementation and ecosystem built on the language-neutral Loom protocol.**

The canonical Loom protocol and semantic specification live in [`FlossWare/loom`](https://github.com/FlossWare/loom). This repository provides concrete AI-oriented implementations such as Workers, Arbiters, model capabilities, and AI-specific execution machinery. Its Python classes are implementations of Loom concepts, not the definition of Loom itself.

`loom-ai` is not required to define Loom's transport, registry technology, serialization format, or programming-language model. Future implementations such as `loom-java` are peers that should conform to the same Loom semantics.

## AI execution model

```text
Loom Contract
     |
 loom-ai implementation
     |
   Intent
     -> Arbiter
         -> Worker
         -> Worker
         -> Arbiter
     -> evidence
     -> evaluation
     -> result
```

The fundamental AI executable abstraction is **Worker**. An **Arbiter is a Worker that coordinates Workers**, so nesting is ordinary composition within the `loom-ai` ecosystem.

## Server binding

`loom-ai` currently provides an HTTP binding around a configured Arbiter. HTTP is a binding implementation here, not the definition of Loom. The server translates requests into declarative Intents and returns structured execution results.

```text
HTTP client
    -> loom-ai HTTP binding
        -> Intent
        -> Arbiter
            -> Workers
        -> result
```

For a transport smoke test:

```bash
loom-server --host 127.0.0.1 --port 8000
```

Then `GET /health` checks server availability and `POST /intents` submits an Intent JSON document. The command-line server uses a no-op Worker solely for transport verification. Applications should configure the server with their own Arbiter and Workers.

## Stage 3 server task dogfood

Stage 3 proves that the `loom-ai` server binding can carry a real multi-worker task, not merely a health check. The dogfood fixture creates a temporary task file and submits an Intent over HTTP. The configured Arbiter then composes three Workers:

```text
POST /intents
    -> Intent
    -> Inspect Worker
    -> Implementation Worker
    -> Verification Worker
    -> successful result
```

The implementation changes the temporary fixture and the verification Worker confirms the acceptance condition. The task path is carried as Intent provenance, keeping the transport unaware of filesystem-specific behavior.

Run it with:

```bash
./scripts/dogfood-stage3.sh
```

This is intentionally deterministic and does not require Crush, an LLM, model routing, or local inference.

## Architectural boundaries

Loom itself owns the language-neutral protocol semantics. `loom-ai` owns AI-oriented realizations of those semantics.

Dedicated repositories own capability implementations:

- `model-gateway`: provider/model invocation, resources, routing, credentials, prompt caching
- `evaluation`: evaluation and reward implementations
- `strategy`: interchangeable decision and optimization strategies
- `knowledge`: durable versioned knowledge
- `storage`, `retrieval`, `rag`, `scraping`, `chunking`, `structured-output`: reusable capabilities
- `budget`, `cache`, `conversation`, `streaming`, `observability`, `resilience`, `security`: cross-cutting capabilities
- `loom-setup`: installation and runtime setup
- `loom-client-setup`: external client configuration

`loom-ai` must not grow parallel implementations merely because it can compose them. AI-specific behavior belongs here; generic protocol semantics belong in `FlossWare/loom`.

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

Run the core dogfood gate with `./scripts/dogfood.sh`, the server transport gate with `./scripts/dogfood-stage2.sh`, and the real-task server gate with `./scripts/dogfood-stage3.sh`.

## License

Apache-2.0
