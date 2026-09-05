# Loom Dogfood and Release Qualification

This document defines the repeatable qualification procedure for `loom-ai` after a significant merge and before advancing to the next architectural priority.

The goal is to validate the **usable system**, not merely confirm that unit tests pass.

## Qualification gate

A P0 implementation is considered dogfood-ready only when:

1. `main` is clean and the expected commit is installed.
2. The full automated test suite passes.
3. Formatting, linting, packaging, and build checks pass.
4. The Loom doctor/preflight gate passes.
5. The canonical chunk contract passes end-to-end through the API/storage path.
6. Configured persistence backends can be exercised.
7. The CLI/TUI smoke path starts and performs its basic health checks.
8. A real model/provider and non-noop embedding path are exercised.
9. Failures are recorded and classified as P0/P1/P2/P3 before new implementation work begins.

A green CI run alone is **not** sufficient for dogfood qualification.

## Fast path: one command

From an existing Loom checkout:

```bash
./scripts/dogfood.sh
```

For a clean-machine qualification directly from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/FlossWare/loom-ai/main/scripts/dogfood.sh | bash
```

The curl form clones a shallow copy of `main` into a temporary directory and executes the repository's qualification script. Set `LOOM_DOGFOOD_REF` to qualify another branch or tag, and `LOOM_DOGFOOD_KEEP=1` to retain the temporary checkout for investigation.

The dogfood script intentionally uses the repository's existing environment and configuration. It does **not** manufacture provider credentials, databases, or other infrastructure. Configure the environment first when running the full live gate.

## What the script validates

The qualification script performs these stages:

### 1. Source and environment

- verifies the Git checkout
- records the exact commit SHA, Python version, and operating system
- requires the Loom canary gate (`LOOM_CANARY=1`)

### 2. Doctor/preflight

`./scripts/doctor.sh` verifies the supported host environment and configured dogfood dependencies, including Python, Git, curl, rootless Podman, Loom importability, the configured LLM provider, and a non-noop embedding backend. PostgreSQL availability is checked when PostgreSQL storage is selected.

The doctor gate is intentionally stricter than ordinary development setup. A machine that can import Loom is not necessarily a machine that can dogfood Loom.

### 3. Static quality

- Ruff formatting check
- Ruff lint check

### 4. Automated tests

- complete pytest suite
- canonical chunk integration tests as part of the full suite

### 5. Package validation

- wheel build
- source distribution build, when the Python build module is installed

## Baseline tests versus full dogfood

There are two useful levels of validation.

### Baseline CI qualification

Use this when you only need to verify source-level correctness and do not have live provider/infrastructure configuration:

```bash
python3 -m pytest -q
ruff format --check .
ruff check .
python3 -m build --wheel --sdist
```

### Full dogfood qualification

Use `./scripts/dogfood.sh`. This is the release/advancement gate and requires the environment checks in `scripts/doctor.sh` to pass, including a real LLM provider and non-noop embeddings.

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

Verify that the installed command starts, reports its health/configuration state, and exits cleanly from the basic diagnostic path. A TUI that technically imports but cannot start is not dogfood-ready. Humans have somehow made this distinction necessary.

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
- doctor result
- enabled backends
- model/provider used
- first failing command and error
- priority classification
- whether the failure reproduces from a clean environment

A concise failure report should include the exact command, relevant error output, and the smallest reproducible path.

## Advancement rule

Only advance to the next architectural implementation priority after the current P0 passes the dogfood gate.

For the current roadmap, the expected next architectural work after canonical chunk qualification is the P1 control-plane/model-router integration, followed by worker isolation and prompt-security hardening. Those changes should be independently reviewed and qualified rather than folded into the canonical chunk fix.
