# FlossWare repository boundaries

This document records the current architectural ownership after consolidation of the former agent stack.

| Repository | Canonical responsibility |
|---|---|
| `loom-ai` | Intent, Worker, Arbiter, execution, evidence, evaluation integration, checkpoints, Knowledge runtime contract, orchestration |
| `loom-setup` | Loom installation, runtime configuration, backend/resource setup, deployment validation |
| `loom-client-setup` | Configure external clients such as Crush, Claude Code, Codex, and Cursor to consume Loom |
| `model-gateway` | Provider/model/resource abstraction, invocation, credentials, hard feasibility, routing/selection, prompt caching |
| `knowledge` | Version-controlled canonical human-reviewable knowledge |
| `evaluation` | Reusable evaluation and verification implementations |
| `strategy` | Reusable decision and optimization strategies |
| `consensus` | Reusable consensus/disagreement strategies |
| `genetic-optimizer` | Genetic/evolutionary optimization implementation |
| `scraping` | Resource discovery and acquisition |
| `chunking` | Canonical deterministic document chunking |

## Architectural rule

A repository may provide an implementation of a Loom capability without becoming a separate architectural control plane. Stable contracts live at the appropriate capability boundary; implementations remain replaceable.

The ordering for adaptive model/resource selection is:

```text
request
  → candidates
  → hard constraints
  → feasible set
  → selection strategy
  → invocation
  → usage/cost/outcome
  → evaluation/learning
```

Hard policy, authorization, safety, budget, quota, and capability constraints are authoritative. Learned optimization cannot bypass them.

## Historical repositories

`FlossWare/agent` is the predecessor to Loom and has been moved to `FlossWare-archives`. `agent-ai` was the package identity within that repository, not a separate current architectural repository.

The former `agent-setup` and `model-router` boundaries are now represented by `loom-setup` and `model-gateway`.
