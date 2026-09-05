# Loom Dogfood and Release Qualification

This document defines the repeatable qualification procedure for `loom-ai` after a significant merge and before advancing to the next architectural priority.

The goal is to validate the **usable system**, not merely confirm that unit tests pass.

## Qualification gate

A P0 implementation is considered ready to advance only when:

1. `main` is clean and the expected commit is installed.
2. The full automated test suite passes.
3. Formatting, linting, packaging, and build checks pass.
4. The live Loom doctor/preflight gate passes.
5. The canonical chunk contract passes end-to-end through the API/storage path.
6. Configured persistence backends can be exercised.
7. The CLI/TUI smoke path starts and performs its basic health checks.
8. A real model/provider and non-noop embedding path are exercised.
9. Failures are recorded and classified as P0/P1/P2/P3 before new implementation work begins.

A green CI run alone is **not** sufficient for dogfood qualification.

## Fast path

There are two modes because not every machine has a live model provider and infrastructure available.

### Baseline qualification

From an existing Loom checkout:

```bash
./scripts/dogfood.sh
```

From a clean machine directly from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/FlossWare/loom-ai/main/scripts/dogfood.sh | bash
```

This mode creates an isolated `.venv`, installs the development/qualification dependencies, runs Ruff, the complete pytest suite, and the package build. It does not require a live LLM, embeddings service, PostgreSQL, Redis, OrientDB, or Podman.

### Full live dogfood

Run the same script with the live gate enabled:

```bash
LOOM_DOGFOOD_LIVE=1 ./scripts/dogfood.sh
```

Or directly from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/FlossWare/loom-ai/main/scripts/dogfood.sh | LOOM_DOGFOOD_LIVE=1 bash
```

Live mode additionally runs `scripts/doctor.sh` and the Loom acceptance harness. The environment must already have the required provider, embedding, and infrastructure configuration. The script never manufactures credentials or production infrastructure.

### Qualifying another revision

```bash
LOOM_DOGFOOD_REF=0.3 ./scripts/dogfood.sh
```

For a remote run, `LOOM_DOGFOOD_REF` is passed to the shallow clone. Set `LOOM_DOGFOOD_KEEP=1` to retain the temporary checkout after a remote run.

## What the script validates

### Baseline mode

1. **Source and environment**
   - verifies Git and Python 3.11+
   - records the exact commit SHA, Python version, and operating system
   - requires the Loom canary gate (`LOOM_CANARY=1`)
   - creates an isolated virtual environment
   - installs the project and development dependencies

2. **Static quality**
   - Ruff formatting check
   - Ruff lint check

3. **Automated tests**
   - complete pytest suite
   - canonical chunk integration tests as part of the full suite

4. **Package validation**
   - wheel build
   - source distribution build

### Live mode

Live mode adds `scripts/doctor.sh`, which verifies the supported host environment and configured dogfood dependencies, including Python, Git, curl, rootless Podman, Loom importability, the configured LLM provider, and a non-noop embedding backend. PostgreSQL availability is checked when PostgreSQL storage is selected.

The live acceptance harness then performs the repository's deterministic acceptance checks and records qualification evidence.

The doctor gate is intentionally stricter than ordinary development setup. A machine that can import Loom is not necessarily a machine that can dogfood Loom.

## Manual live qualification

After the automated gate passes, validate the configured deployment path:

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

The exact provider and infrastructure configuration depends on the environment. Never commit credentials or copy production secrets into test configuration.

### Canonical chunk checks

Verify that a chunk entering Loom retains:

- canonical `id`
- `document_id`
- sequence/chunk index
- `content`
- `token_count`
- `start_offset` and `end_offset`
- metadata
- provenance
- content hash where supplied

Verify that multiple chunks are not silently renumbered and that Unicode offsets retain their documented character-offset semantics.

### API checks

Exercise the REST storage path and verify a round trip:

```text
producer -> POST /knowledge/chunks/store -> persistence -> read -> producer-visible response
```

The API must not manufacture replacement IDs or sequence numbers when canonical values were supplied by the upstream chunking system.

### TUI/CLI smoke test

Verify that the installed command starts, reports its health/configuration state, and exits cleanly from the basic diagnostic path. A TUI that technically imports but cannot start is not dogfood-ready.

## Failure classification

Record the first meaningful failure and classify it before changing code:

| Priority | Meaning | Qualification impact |
|---|---|---|
| P0 | Contract/data-loss/catastrophic failure | Blocks dogfood and release |
| P1 | Architectural or security blocker | Blocks dogfood |
| P2 | Significant hardening/performance issue | Track and schedule |
| P3 | Cleanup/documentation/non-blocking issue | Track separately |

Do not mix unrelated P1/P2/P3 implementation into a P0 qualification fix.

## Evidence to record

For each qualification run record:

- Loom commit SHA
- Python version
- operating system
- installation method
- test command and result
- lint/format/build results
- doctor result, when live mode is used
- enabled backends
- model/provider used, when live mode is used
- first failing command and error
- priority classification
- whether the failure reproduces from a clean environment

A concise failure report should include the exact command, relevant error output, and the smallest reproducible path.

## Advancement rule

Only advance to the next architectural implementation priority after the **live dogfood gate** passes for a P0 implementation.

For the current roadmap, the next architectural work after canonical chunk qualification is the P1 control-plane/model-router integration, followed by worker isolation and prompt-security hardening. Those changes should be independently reviewed and qualified rather than folded into the canonical chunk fix.
