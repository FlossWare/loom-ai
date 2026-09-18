# ADR-0010: Adaptive Model Selection

## Status
Accepted

## Date
2026-08-07

## Context

With hundreds of AI models available across free and paid providers, static model assignment cannot adapt to models that degrade, disappear, appear, specialize by task, or encounter changing provider limits.

A routing strategy is needed that balances exploitation of known-good models with exploration of alternatives while adapting to performance signals.

Internal FlossWare evaluations observed useful behavior from Thompson Sampling with Beta priors, modest exploration, and bounded observation history. These are internal operational observations, not externally published reproducible research.

## Decision

Model selection for AI workloads SHALL be adaptive, policy-driven, and replaceable. The default reference strategy is a multi-armed bandit using Thompson Sampling with Beta priors.

The architectural requirement is adaptive selection, not permanent commitment to one mathematical algorithm.

### Core mechanism

- Each model MAY maintain a statistical state representing observed success/failure.
- The reference implementation uses a Beta(alpha, beta) distribution and Thompson Sampling.
- Exploration parameters and observation limits SHALL be configuration, not architectural constants ([ADR-0016](ADR-0016-configuration-as-source-of-truth.md)).
- Alternative adaptive selection algorithms MAY be introduced without changing service or agent contracts.

### Reward signal

- Reward SHALL be based on objective, mechanically verifiable criteria when possible (correct answer, successful API call, response within latency budget).
- Subjective quality scores MAY supplement but SHALL NOT replace objective signals where objective signals are available.
- Failed API calls MAY receive a stronger penalty than incorrect responses to accelerate disabling of dead models.

### Integration with health checking

- Models entering the routing pool SHOULD be health-checked before receiving production traffic (see [ADR-0015](ADR-0015-dynamic-service-discovery-ai-models.md)).
- Models that fail health checks SHALL be removed from the routing pool and their selection state preserved where useful.
- Models that recover SHOULD re-enter with retained or decayed history according to policy rather than requiring unconditional reset.

### Task-type specialization

- Selection state SHOULD be maintained per task type when workload characteristics differ materially.
- A model that excels at one task type SHALL NOT be assumed to excel at others.

### Fallback behavior

- When all models in the primary pool are unavailable, the system SHALL fall back to a curated set of known-reliable verified models when available.

## Consequences

### Positive
- Model routing adapts without requiring static priority tables.
- The selection mechanism can evolve without changing external contracts.
- Exploration can discover improvements while exploitation uses established performance.

### Negative
- Exploration can intentionally select a suboptimal model.
- Low-traffic task types may not generate enough evidence for reliable adaptation.
- Persistent selection state and observability are required.

## Alternatives Considered

### Static routing table
Rejected — cannot adapt to availability and quality changes.

### Round-robin
Rejected — treats models as equivalent despite differing performance.

### Fixed Thompson Sampling as an immutable architectural requirement
Rejected — unnecessarily couples the architecture to one algorithm.

### Adaptive selection with Thompson Sampling as the reference implementation (chosen)
Preserves the architectural goal while allowing improved selection algorithms over time.

## Related ADRs
- [ADR-0002](0006-ai-provider-abstraction.md) — AI Provider Abstraction
- [ADR-0012](0009-multi-model-consensus-quality-gates.md) — Multi-Model Consensus for Quality Gates
- [ADR-0015](ADR-0015-dynamic-service-discovery-ai-models.md) — Dynamic Service Discovery for AI Models
- [ADR-0016](ADR-0016-configuration-as-source-of-truth.md) — Configuration as Source of Truth
