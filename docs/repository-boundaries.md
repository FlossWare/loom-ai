# FlossWare repository boundaries

This document records architectural ownership for the Loom family and supporting capabilities.

## Loom contract family

| Repository | Canonical responsibility |
|---|---|
| `loom` | Foundational, language-neutral Loom protocol and semantic contract |
| `loom-python` | Python implementation of the foundational Loom contract |
| `loom-ai` | Language-neutral AI-domain contracts and semantics built on Loom |
| `loom-ai-python` | Python implementation of the AI-domain contracts |

The contract repositories are authoritative for meaning. Language-specific repositories are authoritative only for their realization of those contracts.

`loom-ai` MUST NOT redefine, contradict, or replace generic Loom semantics owned by `loom`. It may extend Loom with AI-domain semantics.

Concrete Python runtime code, packaging, implementation tests, and Python-specific dogfood belong in `loom-ai-python`, not `loom-ai`.

Future implementations such as `loom-ai-java` and `loom-ai-erlang` are peers of `loom-ai-python`.

## Supporting capabilities

| Repository | Canonical responsibility |
|---|---|
| `loom-setup` | Loom installation, runtime configuration, backend/resource setup, deployment validation |
| `loom-client-setup` | Configure external clients such as Crush, Claude Code, Codex, and Cursor to consume Loom |
| `model-gateway` | Provider/model/resource abstraction, invocation, credentials, hard feasibility, routing/selection, prompt caching |
| `knowledge` | Reusable knowledge-domain contracts and implementations, with provenance; not the private authoring corpus |
| `evaluation` | Reusable evaluation and verification implementations; reward/outcome attribution |
| `strategy` | Reusable decision-strategy implementations |
| `optimization` | Reusable genetic and evolutionary optimization algorithms |
| `consensus` | Reusable consensus and disagreement-handling behavior |
| `output-validation` | Schema validation, parsing/normalization, and structured result handling |
| `rag` | Retrieval-augmented generation composition |
| `retrieval` | Lexical, vector, and hybrid retrieval/ranking |
| `chunking` | Canonical deterministic document chunking |
| `storage` | Persistence contracts and replaceable storage implementations |
| `scraping` | Resource discovery and acquisition |

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
| `memory` | Remembered state and context semantics, separate from durable Knowledge |
| `learning` | Outcome-driven updates to future behavior and decision estimates |
| `messaging` | Message envelopes and delivery mechanics; not durable event storage by default |
| `alerting` | Alert lifecycle, deduplication, and notification capabilities |

## Architectural rules

1. A repository provides one coherent capability or contract boundary.
2. Contract repositories define language-neutral meaning. Implementations remain replaceable.
3. A domain contract may extend its foundational contract but must not redefine or contradict it.
4. Concrete language implementations belong in language-specific repositories.
5. `loom-ai` is a contract layer, not a Python runtime or orchestration implementation.
6. Model invocation belongs to `model-gateway`; provider SDKs, credentials, routing, budgets, caching, and optimization remain separate capabilities.
7. Execution state is explicit. Avoid hidden global state and service-locator contexts.
8. Cross-cutting capabilities may decorate or support execution but must not create a second orchestration control plane.
9. Composition is preferred over inheritance where a component merely uses another capability.
10. A reusable capability should be independently consumable and must not require Loom unless its contract is explicitly Loom-specific.

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
  -> strategy/learning update
```

Hard authorization, security, safety, quota, availability, and budget constraints are applied before strategy selection. Learned behavior cannot override them.

## RAG / Knowledge boundary

RAG is not Knowledge itself. RAG composes retrieval, context construction, and generation. The `knowledge` capability owns reusable knowledge-domain semantics and provenance. The private `kbase` repository is the authoring corpus. Retrieval may query Knowledge, but neither RAG nor retrieval owns Knowledge semantics.

## Historical repositories

`FlossWare/agent` is the predecessor to Loom and has been moved to `FlossWare-archives`. `agent-ai` was the package identity within that repository, not a separate current architectural repository.

The former `agent-setup` and `model-router` boundaries are now represented by `loom-setup` and `model-gateway`. The former `structured-output` repository has been renamed `output-validation`; the former genetic/evolutionary optimization repository naming is superseded by `optimization`.
