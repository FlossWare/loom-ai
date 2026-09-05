# loom-ai

**Loom is the orchestration runtime for FlossWare's multi-agent AI stack.**

It provides the execution substrate between the control plane and the work being performed by agents and workers. Loom owns orchestration, execution, consensus/arbiter coordination, sessions, transcripts, persistence contracts, and the API/TUI surfaces needed to operate the system.

Loom is deliberately **provider-neutral**. Model selection and account/provider policy belong upstream in `agent-setup` and `model-router`; Loom consumes those decisions rather than becoming another competing model-routing system.

## Architecture

The intended FlossWare flow is:

```text
                    agent-setup
                        |
                  model-router
                        |
                       Loom
                        |
              +---------+---------+
              |                   |
           Workers             Arbiter
              |                   |
              +---------+---------+
                        |
              knowledge / services
             scraping / chunking / KB
                        |
                 persistence
                        |
                    API / TUI
```

### Responsibilities

| Component | Responsibility |
|---|---|
| `agent-setup` | Configure the agent environment, available identities, capabilities, and policy. |
| `model-router` | Discover/select models and providers and enforce routing/account policy. |
| `loom-ai` | Orchestrate execution, workers, arbiter/consensus, sessions, evidence, persistence contracts, and service interfaces. |
| `chunking` | Turn acquired documents into deterministic canonical chunks. |
| `scraping` | Acquire source material and produce canonical acquisition records. |
| Knowledge services | Embedding, search, graph, and downstream knowledge processing. |

Loom should define **contracts and orchestration boundaries**, not absorb the implementation of neighboring projects. External projects are interoperability targets and implementations, not architectural dependencies.

## Current status

The current development line has completed the canonical chunk-contract P0 work. Loom now preserves canonical chunk identity and metadata through its model, REST boundary, and persistence path rather than silently inventing or renumbering upstream chunk identifiers.

The next architectural priorities are deliberately separate from that P0 implementation:

1. P1 control-plane/model-router integration.
2. Worker isolation and execution hardening.
3. Prompt/arbiter security boundaries.
4. P2 performance and operational hardening.

Do not fold those concerns back into the canonical chunk implementation. Each architectural boundary gets its own implementation, review, tests, and dogfood qualification.

## Dogfooding and qualification

Loom is qualified by **dogfooding the usable system**, not by declaring victory because CI is green. The qualification procedure is documented in [`docs/DOGFOOD.md`](docs/DOGFOOD.md).

There are two levels.

### Baseline qualification

This requires no live model provider or infrastructure:

```bash
./scripts/dogfood.sh
```

Or from a clean machine:

```bash
curl -fsSL https://raw.githubusercontent.com/FlossWare/loom-ai/main/scripts/dogfood.sh | bash
```

The script creates an isolated `.venv`, installs the development/qualification dependencies, runs Ruff, the full pytest suite, and builds the wheel and source distribution.

### Full live dogfood

When the environment has the configured model provider, embedding backend, and required infrastructure:

```bash
LOOM_DOGFOOD_LIVE=1 ./scripts/dogfood.sh
```

Or directly from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/FlossWare/loom-ai/main/scripts/dogfood.sh | LOOM_DOGFOOD_LIVE=1 bash
```

Live mode adds the host/configuration doctor and the executable Loom acceptance harness. It is intentionally stricter than a normal development setup. The script does not create credentials or production infrastructure for you.

To qualify another branch, tag, or commit ref:

```bash
LOOM_DOGFOOD_REF=0.3 ./scripts/dogfood.sh
```

For a remote run, `LOOM_DOGFOOD_KEEP=1` retains the temporary checkout for inspection.

### What live dogfood means

The live path should exercise the actual architectural flow rather than isolated mocks:

```text
agent-setup
    -> model-router
        -> Loom
            -> workers
                -> arbiter
                    -> knowledge/chunking
                        -> persistence
                            -> API/TUI
```

For the canonical chunk contract, verify that `id`, `document_id`, sequence/chunk index, content, token count, offsets, metadata, provenance, and supplied content hashes survive the complete path. Multiple chunks must not be silently renumbered, and Unicode offsets must retain their documented character-offset semantics.

For API qualification, exercise the round trip:

```text
producer
  -> POST /knowledge/chunks/store
  -> persistence
  -> read
  -> producer-visible response
```

The API must not manufacture replacement IDs or sequence numbers when canonical values were supplied upstream.

### Qualification rule

A P0 implementation is not considered ready to advance until the **live dogfood gate passes**. Record the commit, environment, test/build results, enabled backends, provider/model, first failure, and P0/P1/P2/P3 classification for every qualification run.

## Install

Core Loom has no required third-party runtime dependencies:

```bash
pip install flossware-loom-ai
```

Optional capability groups are available through the package extras, including CLI, server, PostgreSQL, Redis, and the complete development setup. See [`pyproject.toml`](pyproject.toml) for the authoritative list.

For development and qualification:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

## Quick start

Loom can operate with in-memory/default backends for local development. A typical application obtains a configuration and uses its contracts rather than coupling directly to a particular backend:

```python
import asyncio
from loom_ai import Document, LoomConfig


async def main() -> None:
    cfg = await LoomConfig.from_env()
    await cfg.storage.store_document(
        Document(id="doc-1", title="Example", content="Hello world")
    )


asyncio.run(main())
```

Live model execution requires the environment to be configured through the appropriate control-plane/model-routing path and provider credentials. Loom should not be treated as a place to hard-code model or account selection.

## Core capabilities

Loom currently provides contracts and implementations for areas including:

- DAG/workflow execution and lifecycle management
- Worker fan-out and arbiter/consensus coordination
- Sessions, transcripts, evidence, and provenance
- Storage, queues, search, graph, embeddings, and task-runner interfaces
- REST/API contracts and server integration
- CLI and TUI operation surfaces
- Health, preflight, quality, and qualification support
- Pluggable backends behind provider-neutral interfaces

See [`docs/architecture.md`](docs/architecture.md) for the detailed architecture and [`docs/contracts.md`](docs/contracts.md) for the contract inventory.

## Repository layout

```text
loom-ai/
├── loom_ai/           # Runtime, contracts, models, backends, API, CLI/TUI
├── tests/             # Unit, integration, and contract tests
├── docs/              # Architecture, contracts, qualification, and design docs
├── scripts/            # Development, diagnostics, and dogfood entry points
├── examples/           # Small runnable examples
└── pyproject.toml      # Package, tooling, and test configuration
```

## Engineering principles

- **Contracts before implementations.** Stable interfaces define integration boundaries.
- **Provider neutrality.** Model/account selection is routed outside Loom.
- **Determinism where data crosses boundaries.** Canonical IDs, ordering, offsets, and provenance must survive intact.
- **Isolation.** Worker and backend implementations should remain independently replaceable.
- **Evidence over optimism.** Tests, dogfood runs, and qualification evidence decide whether a change is ready.
- **Small architectural steps.** P0 fixes are qualified before unrelated P1/P2 work is mixed in.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) - architecture and implementation boundaries
- [`docs/contracts.md`](docs/contracts.md) - provider-neutral protocol contracts
- [`docs/DOGFOOD.md`](docs/DOGFOOD.md) - baseline and live qualification procedure

## License

Apache 2.0
