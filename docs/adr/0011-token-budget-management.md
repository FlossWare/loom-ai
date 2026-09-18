# ADR-0011: Token Budget Management

## Status
Accepted

## Date
2026-08-07

## Context

AI model APIs charge per token or enforce context and rate limits. Without active token management, long prompts can consume budget unnecessarily, exhaust free-tier limits, or exceed model context windows.

Token management is a cross-cutting concern but should not be mandatory for every request because some tasks require exact prompt preservation and compression overhead can exceed its benefit.

Internal FlossWare evaluations observed useful savings for structured inputs and little benefit for very short prompts. These observations are internal and workload-specific.

## Decision

Token budget management SHALL be an explicit, opt-in cross-cutting capability ([ADR-0001](ADR-0001-explicit-opt-in-cross-cutting-behavior.md)).

### Opt-in activation

- Compression SHALL NOT be applied by default.
- Call sites or policy configuration SHALL explicitly enable token management.
- The implementation SHOULD be injected as a decorator or middleware ([ADR-0006](ADR-0006-cross-cutting-decorators.md)), not embedded in business logic.

### Compression and preservation

- Token-management implementations SHALL preserve required system, policy, tool, and user context according to the workload's contract.
- Compression SHALL NOT be described or implemented as modification of hidden model reasoning.
- Compression SHOULD occur before optional framework augmentation when doing so preserves required semantics.
- The original input SHALL remain available as a fallback when compression is unsafe or produces degenerate output.
- Thresholds, strategies, and safety floors SHALL be configuration rather than architectural constants ([ADR-0016](ADR-0016-configuration-as-source-of-truth.md)).

### Dual-context evaluation

When evaluating token management tools or strategies, teams SHOULD score separately for:

- **Free-tier context** — context-window utilization and rate-limit headroom.
- **Paid/metered context** — the above plus direct cost reduction.

### Budget tracking

- Systems SHOULD track tokens_before, tokens_after, tokens_saved, and compression_ratio per request when the provider exposes reliable token accounting.
- Compression statistics SHOULD be included in observability and cost monitoring pipelines.
- Adaptive model selection MAY incorporate token efficiency as a secondary reward signal when policy permits ([ADR-0013](0010-bandit-based-model-selection.md)).

## Consequences

### Positive
- Token management can reduce cost and rate-limit pressure without affecting exact-prompt workloads by default.
- Implementations can evolve independently of business logic.
- Policy and thresholds remain configurable.

### Negative
- Compression adds latency and implementation complexity.
- Lossy transformations can remove important context if poorly configured.
- Provider-specific token accounting may vary.

## Alternatives Considered

### Always-on compression
Rejected — can degrade exact-prompt tasks and wastes overhead on short prompts.

### No token management
Rejected — leaves avoidable cost, rate-limit, and context-window pressure.

### Opt-in, observable token management (chosen)
Balances efficiency with preservation of task semantics.

## Related ADRs
- [ADR-0001](ADR-0001-explicit-opt-in-cross-cutting-behavior.md) — Explicit Opt-In Cross-Cutting Behavior
- [ADR-0002](0006-ai-provider-abstraction.md) — AI Provider Abstraction
- [ADR-0006](ADR-0006-cross-cutting-decorators.md) — Cross-Cutting Decorators
- [ADR-0008](ADR-0008-free-first-modular-platform.md) — Free-First Modular Platform
- [ADR-0013](0010-bandit-based-model-selection.md) — Adaptive Model Selection
- [ADR-0016](ADR-0016-configuration-as-source-of-truth.md) — Configuration as Source of Truth
