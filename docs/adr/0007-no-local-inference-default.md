# ADR-0007: Policy-Driven AI Execution Topology

## Status
Accepted

## Date
2026-08-21

## Context

FlossWare originally favored remote inference by default to keep deployments accessible on small infrastructure and avoid coupling users to local GPU hardware, model packaging, and driver stacks.

That constraint is no longer sufficient as the architectural basis for FlossWare. FlossWare now supports and is expected to support hosted, commercial, free-tier, and local inference, with model selection adapting to workload requirements and runtime conditions.

Local execution can provide important advantages for privacy, data residency, air-gapped operation, predictable latency, offline operation, and economics. Hosted execution can provide advantages in model availability, hardware access, operational simplicity, and rapid access to new capabilities. Neither topology is universally superior.

The architecture therefore needs to separate **execution capability** from **execution topology**. Topology should be selected by explicit policy and runtime evidence rather than by a permanent local-first or remote-first rule.

## Scope

Execution topology selection for AI model workloads in FlossWare systems.

## Non-goals

- Does not mandate a particular model provider, model family, or local runtime.
- Does not require local inference support in every deployment.
- Does not define model quality or consensus policy; those are addressed by [ADR-0012](0009-multi-model-consensus-quality-gates.md) and [ADR-0013](0010-bandit-based-model-selection.md).

## Decision

FlossWare SHALL NOT impose a universal local-first or remote-first inference topology.

AI execution topology SHALL be selected through explicit deployment and runtime policy, subject to model inventory, verification, availability, and workload requirements.

### Execution candidates

Eligible execution candidates MAY include:

- Hosted commercial providers
- Hosted free-tier providers
- Self-hosted remote models
- Local models on developer or deployment hardware
- Other execution mechanisms introduced through the provider abstraction

### Policy determines eligibility

Configuration SHALL determine which execution candidates are permitted for a deployment or workload, consistent with [ADR-0016](ADR-0016-configuration-as-source-of-truth.md).

Relevant policy dimensions MAY include:

- Data privacy and trust boundaries
- Data residency and regulatory requirements
- Air-gapped or offline requirements
- Cost and budget constraints
- Latency requirements
- Required model capabilities
- Availability and reliability requirements
- Operational and hardware constraints
- Explicit organizational or user preferences

### Inventory and routing

The dynamic model inventory defined by [ADR-0015](0012-dynamic-ai-model-inventory.md) SHALL provide candidate inventory and verification state. Discovery SHALL NOT by itself grant routing eligibility.

Eligible candidates SHOULD be selected by the adaptive routing strategy defined by [ADR-0013](0010-bandit-based-model-selection.md), subject to workload-specific policy and quality requirements.

### Local execution

Local inference SHALL be treated as a first-class supported execution capability where an appropriate local runtime is available. Local execution MUST NOT require a special architectural exception merely because it is local.

Deployments MAY prefer local execution when policy or runtime conditions make it the best eligible option, including privacy, residency, offline, latency, or cost considerations.

### Hosted execution

Hosted inference SHALL remain a first-class execution capability. Deployments MAY prefer hosted execution when it provides the best eligible combination of capability, reliability, latency, cost, or operational simplicity.

### Free-first policy

The free-first principle in [ADR-0008](ADR-0008-free-first-modular-platform.md) remains a component-selection preference, not a universal runtime routing requirement. Paid execution MAY be selected when explicitly permitted by policy and justified by workload requirements.

### No implicit topology changes

The presence of a local model, provider, or optional runtime SHALL NOT silently change execution policy. Activation and eligibility remain configuration-owned and auditable.

## Consequences

### Positive

- FlossWare can optimize execution for privacy, cost, quality, latency, availability, and operational constraints.
- Local inference becomes a first-class capability without forcing hardware requirements on every deployment.
- Paid providers can be used where their capabilities justify the cost.
- Routing policy remains explicit, explainable, and adaptable.
- The architecture remains independent of any particular provider or inference runtime.

### Negative

- Policy and routing become more sophisticated than a single topology default.
- Deployments need clear eligibility and budget configuration.
- Supporting multiple execution topologies increases integration and operational testing requirements.

## Alternatives Considered

### Remote-first default
Rejected — no longer reflects FlossWare's broader execution model and unnecessarily privileges one topology.

### Local-first default
Rejected — imposes hardware and operational requirements that are inappropriate for many deployments.

### Free-only execution
Rejected — blocks capabilities, reliability, and quality that may justify paid execution.

### Policy-driven topology selection (chosen)
Provides a topology-neutral architecture while allowing deployments and adaptive routing to choose the best eligible execution path.

## Related ADRs

- [ADR-0002](0006-ai-provider-abstraction.md) — AI Provider Abstraction
- [ADR-0008](ADR-0008-free-first-modular-platform.md) — Free-First Modular Platform
- [ADR-0012](0009-multi-model-consensus-quality-gates.md) — Multi-Model Consensus for Quality Gates
- [ADR-0013](0010-bandit-based-model-selection.md) — Adaptive Model Selection
- [ADR-0015](0012-dynamic-ai-model-inventory.md) — Dynamic AI Model Inventory
- [ADR-0016](ADR-0016-configuration-as-source-of-truth.md) — Configuration as Source of Truth
