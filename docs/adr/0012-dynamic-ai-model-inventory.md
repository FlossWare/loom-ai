# ADR-0012: Dynamic AI Model Inventory

> Formerly titled “Dynamic Service Discovery for AI Models” — renamed to avoid confusion with microservice service-discovery.

## Status
Accepted

## Date
2026-08-07

## Context

The AI model landscape changes rapidly: integration providers add and remove models, free tiers appear and disappear, rate limits shift, and model quality varies over time. Static model registries cannot keep pace with this churn.

Internal FlossWare operations observed that automated discovery can surface additional routable models without code changes, health checks can catch models that are reachable but unreliable, and provider bridge tables reduce integration cost. These are internal operational observations, not externally published studies.

## Scope

How FlossWare maintains an inventory of AI models and their eligibility for routing — not general microservice discovery (DNS, service mesh, etc.).

## Non-goals

- Does not define consensus diversity units ([ADR-0012](0009-multi-model-consensus-quality-gates.md)).
- Does not replace configuration-owned policy ([ADR-0016](ADR-0016-configuration-as-source-of-truth.md)).

## Decision

AI model inventories SHALL be maintained as dynamic registries, not hardcoded configuration alone.

### Inventory, trust, and policy are separate

The following states SHALL remain conceptually distinct:

1. **Discovered** — the model exists in the inventory.
2. **Verified** — the model passed the configured health checks.
3. **Trusted/eligible** — policy permits the model to participate in a routing pool.
4. **Routable** — current availability and routing policy allow production selection.
5. **Disabled** — the model is intentionally or automatically excluded.

Discovery SHALL NOT automatically grant trust, authorization, routing eligibility, or MCP exposure.

### Registry as inventory source

- The model registry SHALL be the authoritative *inventory* source for available models, integration providers, and capabilities.
- Hardcoded model entries MAY exist as bootstrap or override data but SHALL NOT be the sole source of routing information. Bootstrap lists are non-authoritative seeds, not configuration policy.
- The registry SHOULD be populated by automated discovery rather than manual entry only.
- **Policy** (allowed pools, free-first filters, budgets) remains configuration-owned ([ADR-0016](ADR-0016-configuration-as-source-of-truth.md)).

### Provider bridge tables

Here **provider** means an **integration adapter** (endpoint, auth, call format), consistent with [ADR-0002](0006-ai-provider-abstraction.md).

- Systems SHALL maintain provider configuration that maps each provider to its endpoint pattern, authentication mechanism, and call format.
- Adding a model from a known provider SHALL NOT require code changes when its provider contract is already supported.
- New providers require a bridge configuration and, if the call format is novel, a new adapter.

### Health verification lifecycle

- Only verified and policy-eligible models SHOULD receive production traffic by default.
- Health checks SHOULD use objective, mechanically verifiable probes where practical.
- Health results SHOULD update the registry and routing eligibility.

### Free-tier filtering

- Systems operating under a free-first policy ([ADR-0008](ADR-0008-free-first-modular-platform.md)) SHALL maintain explicit free/paid policy metadata.
- Dynamic models from paid-only providers SHALL NOT enter the routing pool unless explicitly enabled.
- Free/paid classification SHOULD be registry metadata while the decision to allow a pool remains configuration-owned.

### Graceful degradation

- If the registry is unreachable, the system SHALL use the last valid registry snapshot or configured bootstrap entries according to policy.
- Registry refresh failures SHALL be logged but SHALL NOT block request processing when a valid routing snapshot exists.
- Stale snapshots SHALL be subject to expiration policy.

## Consequences

### Positive
- New models can become eligible without application code changes.
- Dead or degraded models can be removed from routing automatically.
- Inventory remains distinct from policy and authorization.
- Provider adapters remain reusable.

### Negative
- Registry infrastructure must be operated and monitored.
- Automated discovery can import low-quality models that consume verification budget.
- Health probes test only selected capabilities and cannot prove general model quality.
- Stale snapshots require explicit expiration handling.

## Alternatives Considered

### Hardcoded model list only
Rejected — cannot adapt to ecosystem changes.

### Fully dynamic with no configured fallback
Rejected — registry outage would leave the system with no available inventory.

### Dynamic inventory with explicit verification, eligibility, and routing policy (chosen)
Provides adaptability without conflating discovery with permission or production use.

## Related ADRs
- [ADR-0002](0006-ai-provider-abstraction.md) — AI Provider Abstraction
- [ADR-0003](0007-no-local-inference-default.md) — No Local Inference by Default
- [ADR-0008](ADR-0008-free-first-modular-platform.md) — Free-First Modular Platform
- [ADR-0012](0009-multi-model-consensus-quality-gates.md) — Multi-Model Consensus for Quality Gates
- [ADR-0013](0010-bandit-based-model-selection.md) — Bandit-Based Model Selection
- [ADR-0016](ADR-0016-configuration-as-source-of-truth.md) — Configuration as Source of Truth
