# ADR-0017: Provider-Neutral AI Selection

## Status
Accepted

## Date
2026-08-23

## Context

FlossWare has evolved beyond an architecture organized around a preferred pricing tier or a preferred model vendor. AI workloads may use hosted services, local runtimes, enterprise-managed endpoints, self-hosted infrastructure, or other compatible execution mechanisms.

Treating any pricing tier, including zero-cost execution, as an architectural preference creates unnecessary coupling and causes setup tools, routing logic, documentation, and examples to age as the available model ecosystem changes.

FlossWare needs a durable abstraction in which providers and models are interchangeable implementation choices selected according to the requirements of a workload.

## Decision

FlossWare AI components SHALL be **provider-neutral and pricing-neutral**.

They MUST NOT require, prefer, advertise, or assume:

- a specific model vendor;
- a specific provider;
- a hosted or local execution model;
- a free, paid, or other pricing tier; or
- a particular authentication mechanism when the integration supports alternatives.

Provider and model selection SHALL be determined at runtime or deployment time from explicit policy and capability information.

### Selection dimensions

Routing MAY consider, as applicable:

- required capabilities and modalities;
- quality and evaluation results;
- availability and health;
- latency and capacity;
- context and output limits;
- cost and budget policy;
- security, privacy, compliance, and data-residency requirements;
- authentication and authorization state;
- deployment topology;
- organizational policy; and
- workload-specific constraints.

**Cost is a routing attribute, not an architectural identity.** A zero-cost model is not a privileged class of provider.

### Provider integrations

Provider-specific adapters MAY exist. They SHALL remain behind contracts or capability interfaces and SHALL NOT leak provider preference into business logic, default configuration, documentation, or generated agent configuration.

### Discovery and authentication

Where a provider or agent CLI exposes an existing authenticated session, setup and routing components SHOULD discover and reuse that capability rather than unnecessarily requiring a second credential. Credentials SHALL remain outside generated project configuration unless a secure mechanism explicitly requires otherwise.

### Documentation and examples

FlossWare documentation, examples, templates, and setup experiences SHALL describe provider selection in capability/policy terms. They MUST NOT frame any pricing tier or vendor as the default architectural choice.

Specific providers may be used in tests or examples when necessary to demonstrate an integration, but the surrounding documentation SHALL make the example's implementation-specific nature clear.

## Consequences

### Positive

- Prevents vendor and pricing-tier lock-in.
- Keeps routing architecture stable as providers and pricing change.
- Allows users to consume capabilities they already have access to.
- Makes cost a transparent policy input rather than a hidden architectural constraint.
- Supports hosted, local, enterprise, and other execution topologies without changing business logic.

### Negative

- Provider discovery and capability metadata require additional implementation work.
- Provider-specific features need explicit capability modeling.
- Routing policy becomes more important and must be observable and auditable.

## Supersession

This ADR supersedes the pricing-tier preference in [ADR-0008](ADR-0008-free-first-modular-platform.md). ADR-0008 remains historical context for FlossWare's earlier accessibility goals, but its free-first selection rule is no longer normative.

## Related ADRs

- [ADR-0002](0006-ai-provider-abstraction.md) — AI Provider Abstraction
- [ADR-0003](0007-no-local-inference-default.md) — Policy-Driven AI Execution Topology
- [ADR-0012](0009-multi-model-consensus-quality-gates.md) — Multi-Model Consensus Quality Gates
- [ADR-0013](0010-bandit-based-model-selection.md) — Adaptive Model Selection
- [ADR-0015](0012-dynamic-ai-model-inventory.md) — Dynamic AI Model Inventory
- [ADR-0017](0013-agent-neutral-architecture.md) — Agent-Neutral Architecture
