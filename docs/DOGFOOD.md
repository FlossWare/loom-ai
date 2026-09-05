# Loom Dogfood and Release Qualification

This document defines the repeatable qualification procedure for `loom-ai` after a significant merge and before advancing to the next architectural priority.

The goal is to validate the **usable system**, not merely confirm that unit tests pass.

## Qualification gate

A P0 implementation is considered dogfood-ready only when:

1. `main` is clean and the expected commit is installed.
2. The full automated test suite passes.
3. Formatting, linting, packaging, and build checks pass.
4. The strict dogfood checks pass.
5. The canonical chunk contract passes end-to-end through the API/storage path.
6. Configured persistence backends can be exercised when infrastructure is available.
7. The CLI/TUI smoke path starts and performs its basic health checks.
8. A real model/provider path is exercised when model configuration is available.
9. Failures are recorded and classified as P0/P1/P2/P3 before new implementation work begins.

A green CI run alone is **not** sufficient for dogfood qualification.

## Fast path

From a checkout of `main`:

```bash
./scripts/dogfood.sh
```

The script creates an isolated virtual environment, installs the repository, runs the automated qualification checks, and reports a final PASS/FAIL result. It does not require production credentials or external model access for the baseline checks.

For a remote, clean-machine run:

```bash
curl -fsSL https://raw.githubusercontent.com/FlossWare/loom-ai/main/scripts/dogfood.sh | bash
```

Use a local checkout when investigating failures so the generated environment and test output can be retained.

## What the script validates

The qualification script performs these stages:

### 1. Source and environment

- verifies Git and Python prerequisites
- obtains the requested Loom revision
- creates an isolated virtual environment
- installs the project and test dependencies

### 2. Static quality

- Ruff formatting check
- Ruff lint check
- package/build validation

### 3. Automated tests

- complete pytest suite
- canonical chunk integration tests when present

### 4. Dogfood checks

The script invokes the repository's supported strict dogfood entry point when available. This is the qualification layer above ordinary unit tests.

### 5. Optional live infrastructure

The baseline script does not require PostgreSQL, Redis, OrientDB, or an LLM provider. When those services are intentionally configured, run the corresponding integration/smoke checks as part of the environment-specific qualification.

## Manual live qualification

After the baseline script passes, validate the configured deployment path:

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
- dogfood result
- enabled backends
- model/provider used, if any
- first failing command and error
- priority classification
- whether the failure reproduces from a clean environment

A concise failure report should include the exact command, relevant error output, and the smallest reproducible path.

## Advancement rule

Only advance to the next architectural implementation priority after the current P0 passes the baseline dogfood gate.

For the current roadmap, the expected next architectural work after canonical chunk qualification is the P1 control-plane/model-router integration, followed by worker isolation and prompt-security hardening. Those changes should be independently reviewed and qualified rather than folded into the canonical chunk fix.
