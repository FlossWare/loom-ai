# ADR-0006: AI Provider Abstraction

## Status
Accepted

## Date
2026-08-07

## Context

FlossWare requires AI capabilities across code generation, review, retrieval, and orchestration. Binding the platform to a single model vendor, runtime, or deployment topology would create lock-in, complicate testing, and constrain workload-specific policy.

Teams need to swap providers without rewriting business logic.

### Terminology

In this ADR and related integration ADRs, **provider** means an **integration adapter**: endpoint pattern, authentication, and call format for invoking models ([ADR-0015](0012-dynamic-ai-model-inventory.md) bridge tables). It does **not** mean a consensus **diversity unit** (model family / training lineage); that sense is defined only in [ADR-0012](0009-multi-model-consensus-quality-gates.md).

## Scope

How FlossWare application and platform code obtains AI model inference and related model APIs.

## Non-goals

- Does not choose specific model vendors or ranking algorithms ([ADR-0013](0010-bandit-based-model-selection.md)).
- Does not define agent tool protocols ([ADR-0004](0008-mcp-tool-contracts.md)).
- Does not establish a preferred pricing tier or execution topology.

## Decision

All AI capabilities SHALL be accessed through provider abstractions.

- Call sites depend on contracts (interfaces / ports), not concrete SDKs.
- Providers MAY include hosted APIs, local inference runtimes, enterprise-managed endpoints, or other compatible execution mechanisms when policy permits.
- Provider and model selection SHALL be policy- and capability-driven as defined by [ADR-0021](0017-provider-neutral-ai-selection.md).
- Routing, fallback, and consensus policies sit above the provider layer ([ADR-0012](0009-multi-model-consensus-quality-gates.md), [ADR-0013](0010-bandit-based-model-selection.md)).

## Consequences

### Positive

- No model vendor or pricing-tier lock-in.
- Capabilities are selected through contracts.
- Local inference is an optional capability, not a requirement.
- Tests can substitute fake or recorded providers.
- Provider choice can evolve without changing business logic.

### Negative

- Extra abstraction cost and adapter maintenance.
- Feature parity across providers is imperfect; lowest-common-denominator APIs may hide advanced features unless optional capability interfaces exist.
- Capability discovery and routing policy require explicit metadata and observability.

## Alternatives Considered

### Single-vendor SDK everywhere
Rejected — couples product roadmap to one vendor.

### Direct multi-SDK usage at call sites
Rejected — scatters vendor logic and makes policy (routing, fallback) inconsistent.

### Provider abstraction (chosen)
Accepted — centralizes integration and preserves deployment and policy flexibility.

## Related ADRs
- [ADR-0003](0007-no-local-inference-default.md) — Policy-Driven AI Execution Topology
- [ADR-0004](0008-mcp-tool-contracts.md) — MCP and Tool Contracts
- [ADR-0012](0009-multi-model-consensus-quality-gates.md) — Multi-Model Consensus for Quality Gates
- [ADR-0013](0010-bandit-based-model-selection.md) — Bandit-Based Model Selection
- [ADR-0015](0012-dynamic-ai-model-inventory.md) — Dynamic AI Model Inventory
- [ADR-0021](0017-provider-neutral-ai-selection.md) — Provider-Neutral AI Selection
