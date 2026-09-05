# loom-ai

![loom-ai](docs/assets/banner.svg)

**Loom is the orchestration runtime for the FlossWare AI system.** It provides the execution substrate, worker/arbiter coordination, provider-neutral contracts, session and evidence handling, persistence boundaries, and API/CLI/TUI surfaces needed to run multi-step AI work reliably.

Loom is deliberately modular. Model selection belongs to `model-router`; environment and identity setup belongs to `agent-setup`; acquisition and document transformation belong to the knowledge-pipeline projects. Loom consumes those capabilities through explicit contracts instead of absorbing their implementations.

## Architecture

The intended FlossWare control/data flow is:

```text
                         agent-setup
                              |
                        model-router
                              |
                           +-----+
                           | Loom|
                           +-----+
                              |
                    +---------+---------+
                    |                   |
                 Workers             Arbiter
                    |                   |
                    +---------+---------+
                              |
                    Knowledge / Services
                 scraping / chunking / KB
                              |
                 persistence / API / TUI
```

### Responsibility boundaries

| Component | Responsibility |
|-----------|----------------|
| `agent-setup` | Configure the control plane, identities, profiles, and supported agent integrations. |
| `model-router` | Discover/select eligible models and providers and route work according to policy. |
| `loom-ai` | Execute workflows, coordinate workers, collect results, run arbitration/consensus, preserve state/evidence, and expose runtime interfaces. |
| `scraping` | Acquire source material and normalize acquisition metadata. |
| `chunking` | Convert documents into deterministic canonical chunks. |
| Knowledge services | Store, search, embed, and graph acquired knowledge. |

These boundaries are intentional. Loom may integrate with another project, but an integration should not silently turn that project into a Loom implementation dependency.

## What Loom provides

- **Execution engine** for dependency-aware work and orchestration.
- **Worker fan-out and arbiter synthesis** for multi-worker tasks.
- **Provider-neutral contracts** using structural interfaces rather than hard-coded implementations.
- **Session lifecycle and transcript/state persistence.**
- **Evidence and provenance boundaries** for qualification and verification.
- **Storage, queue, search, embedding, graph, secrets, and task-runner interfaces** with replaceable backends.
- **REST/API, CLI, TUI, SDK, and MCP integration surfaces** where enabled.
- **Deterministic canonical chunk handling** so upstream chunk identity and ordering survive the Loom boundary.

## What Loom does not own

Loom is not the model-discovery service, not the agent setup application, and not the scraping or chunking implementation. In particular:

- Do not bypass `model-router` with ad-hoc provider selection in Loom integrations.
- Do not duplicate `agent-setup` configuration logic inside Loom.
- Do not reimplement document acquisition in Loom.
- Do not silently renumber or replace canonical chunks supplied by `chunking`.
- Do not make an external project a required dependency merely because Loom can interoperate with it.

The goal is a set of replaceable systems with stable contracts, not one enormous Python blob that eventually becomes everybody's problem.

## Installation

For development:

```bash
git clone https://github.com/FlossWare/loom-ai.git
cd loom-ai
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

For the core library:

```bash
pip install flossware-loom-ai
```

Optional extras are available for the supported CLI, server, PostgreSQL, Redis, OrientDB, model-provider, and development integrations. See `pyproject.toml` for the authoritative list.

## Dogfooding and release qualification

Loom uses **dogfooding as a qualification gate**, not as a synonym for “the unit tests passed.” The purpose is to exercise the actual usable system after a significant architectural change and catch integration failures before the next implementation phase begins.

The complete procedure is documented in [`docs/DOGFOOD.md`](docs/DOGFOOD.md).

### Fast baseline qualification

From an existing checkout:

```bash
./scripts/dogfood.sh
```

Or from a clean machine without first cloning the repository:

```bash
curl -fsSL https://raw.githubusercontent.com/FlossWare/loom-ai/main/scripts/dogfood.sh | bash
```

The baseline script:

1. verifies Git/Python requirements and records the commit/environment;
2. creates an isolated `.venv`;
3. installs the project and development dependencies;
4. runs Ruff formatting and lint checks;
5. runs the complete pytest suite; and
6. builds both a wheel and source distribution.

Baseline qualification does **not** require a live LLM, embedding service, PostgreSQL, Redis, OrientDB, or Podman.

### Full live dogfood

When the live provider and infrastructure are configured:

```bash
LOOM_DOGFOOD_LIVE=1 ./scripts/dogfood.sh
```

Or directly from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/FlossWare/loom-ai/main/scripts/dogfood.sh | LOOM_DOGFOOD_LIVE=1 bash
```

Live mode adds the environment doctor/preflight gate and the acceptance harness. It verifies that the configured environment can actually run Loom rather than merely import it.

The live path is conceptually:

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

### Qualifying another revision

The script can qualify a branch or release ref:

```bash
LOOM_DOGFOOD_REF=0.3 ./scripts/dogfood.sh
```

For remote runs, use the same variable with the curl form. To retain the temporary checkout created by a remote run:

```bash
LOOM_DOGFOOD_KEEP=1 LOOM_DOGFOOD_LIVE=1 ./scripts/dogfood.sh
```

### What must pass

The live qualification gate checks more than CI:

- automated tests, formatting, linting, and package builds;
- supported runtime/environment prerequisites;
- configured model/provider connectivity;
- a non-noop embedding path;
- configured persistence where selected;
- canonical chunk identity, ordering, metadata, provenance, token counts, and offsets;
- REST storage round trips without replacement IDs or sequence numbers; and
- CLI/TUI diagnostic startup and health paths.

A green CI run by itself is **not** release qualification.

### Failure classification

When dogfood fails, record the first meaningful failure before changing code:

| Priority | Meaning | Effect |
|----------|---------|--------|
| **P0** | Contract, data-loss, or catastrophic failure | Blocks qualification and release. |
| **P1** | Architectural or security blocker | Blocks dogfood. |
| **P2** | Significant hardening/performance issue | Track and schedule. |
| **P3** | Cleanup/documentation/non-blocking issue | Track separately. |

Do not mix unrelated P1/P2/P3 work into a P0 qualification fix.

## Canonical chunk contract

Loom preserves canonical chunks supplied by the upstream `chunking` system. A chunk crossing the Loom API/storage boundary retains, where supplied:

- `id`
- `document_id`
- `sequence` / `chunk_index`
- `content`
- `token_count`
- `start_offset` / `end_offset`
- metadata
- provenance
- content hash

Multiple chunks must not be silently renumbered, and Unicode offsets retain their documented character-offset semantics.

The important round trip is:

```text
producer
  -> POST /knowledge/chunks/store
  -> Loom persistence
  -> read
  -> producer-visible response
```

The storage layer must not manufacture replacement IDs or sequence numbers when canonical values were supplied upstream.

## Configuration and backends

Loom keeps infrastructure replaceable through backend contracts. The default development configuration can run without external services, while production-like deployments can select persistent or remote backends.

Typical backend areas include:

- storage
- queues
- secrets
- embeddings
- search
- knowledge graph
- task execution
- model/runtime integration

Configuration is environment- and deployment-specific. Do not commit credentials, provider keys, or production configuration to the repository.

## Runtime interfaces

Depending on installed extras and deployment configuration, Loom exposes:

- Python API and SDK
- REST API
- CLI
- TUI
- MCP integration
- backend-specific storage/search/queue interfaces

The CLI/TUI are operational interfaces to the runtime. They are not substitutes for the control-plane responsibilities owned by `agent-setup` and `model-router`.

## Development

Run the normal local checks with:

```bash
. .venv/bin/activate
python -m ruff format --check .
python -m ruff check .
python -m pytest -q
python -m build --wheel --sdist
```

For architectural changes, run the dogfood procedure after the relevant automated tests pass. A change is not considered complete merely because its unit tests are green.

## Documentation

- [`docs/DOGFOOD.md`](docs/DOGFOOD.md) - dogfood and release qualification procedure
- [`docs/architecture.md`](docs/architecture.md) - architecture and extension boundaries
- [`docs/contracts.md`](docs/contracts.md) - protocol contract inventory
- [`docs/`](docs/) - detailed design, operational, and integration documentation

## Project status

Loom is under active development. The current qualification work has established the canonical chunk contract and its persistence/API behavior. The next architectural priorities are the control-plane/model-router integration, worker isolation, and prompt-security hardening.

Changes should be independently reviewed and dogfooded rather than accumulating unrelated architectural work in a single implementation.

## License

Apache-2.0
