# FlossWare repository boundaries

This document records the current architectural ownership after consolidation of the former agent stack and supporting AI capabilities.

## Core Loom

| Repository | Canonical responsibility |
|---|---|
| `loom-ai` | Intent, Worker, Arbiter, execution, evidence, evaluation integration, checkpoints, Knowledge runtime contract, interaction observations, orchestration |
| `loom-setup` | Loom installation, runtime configuration, backend/resource setup, deployment validation |
| `loom-client-setup` | Configure external clients such as Crush, Claude Code, Codex, and Cursor to consume Loom |
| `model-gateway` | Provider/model/resource abstraction, invocation, credentials, hard feasibility, routing/selection, prompt caching |
| `knowledge` | Version-controlled canonical human-reviewable knowledge |

## Reusable AI capabilities

| Repository | Canonical responsibility |
|---|---|
| `evaluation` | Reusable evaluation and verification implementations; reward/outcome attribution |
| `strategy` | Reusable decision and optimization strategies |
| `consensus` | Reusable consensus/disagreement strategies |
| `genetic-optimizer` | Genetic/evolutionary optimization implementation |
| `rag` | Retrieval-augmented generation composition |
| `retrieval` | Lexical, vector, and hybrid retrieval/ranking |
| `chunking` | Canonical deterministic document chunking |
| `storage` | Persistence contracts and replaceable storage implementations |
| `scraping` | Resource discovery and acquisition |
| `structured-output` | Schema validation and structured result handling |

## Cross-cutting capabilities

| Repository | Canonical responsibility |
|---|---|
| `budget` | Token/cost accounting and budget constraints; enforcement authority integrates at the gateway/execution boundary |
| `cache` | Generic cache mechanics; prompt-cache semantics are owned by `model-gateway` |
| `conversation` | Message/session lifecycle mechanics; Loom owns semantic Interaction |
| `streaming` | Generic asynchronous stream mechanics; Loom owns semantic execution events |
| `observability` | Metrics, events, traces, execution telemetry, and cost/quality measurement |
| `resilience` | Retry, circuit breaking, rate limiting, and health policies |
| `security` | Secret handling, authorization/policy primitives, audit logging, and security constraints |

## Superseded / retirement candidates

| Repository | Decision |
|---|---|
| `learning` | Consolidate reusable pieces into Loom, Knowledge, Evaluation, and Strategy, then archive |
| `workflow` | Superseded by Loom orchestration; migrate reusable mechanics, then archive |

These repositories must not receive new architectural features while migration is underway.

## Architectural rules

1. A repository provides one coherent capability boundary. A capability implementation must not become a second control plane.
2. `loom-ai` owns orchestration. Do not create another Worker/Agent/Workflow runtime in a supporting repository.
3. Stable contracts live at the appropriate capability boundary. Implementations remain replaceable.
4. Composition is preferred over inheritance where a component merely uses another capability.
5. Execution state is explicit. Avoid hidden global state and service-locator contexts.
6. Model invocation belongs to `model-gateway`.
7. Durable Knowledge belongs to `knowledge`; runtime Knowledge access is a Loom capability.
8. Evaluation determines outcome quality. Strategy chooses among feasible alternatives.
9. Hard policy, authorization, safety, budget, quota, rate, availability, and capability constraints are authoritative. Learned optimization cannot bypass them.
10. Cross-cutting capabilities may decorate or support execution but must not own orchestration.

## Adaptive model/resource selection

The required ordering is:

```text
request
  -> candidates
  -> hard constraints
  -> feasible set
  -> selection strategy
  -> invocation
  -> usage/cost/outcome
  -> evaluation/reward
  -> strategy/Knowledge update
```

## RAG / Knowledge boundary

RAG is not Knowledge itself. RAG is a composition of retrieval, context construction, and generation. Knowledge is durable, versioned understanding with provenance. Retrieval may query Knowledge, but neither RAG nor retrieval owns Knowledge semantics.

## Historical repositories

`FlossWare/agent` is the predecessor to Loom and has been moved to `FlossWare-archives`. `agent-ai` was the package identity within that repository, not a separate current architectural repository.

The former `agent-setup` and `model-router` boundaries are now represented by `loom-setup` and `model-gateway`.
