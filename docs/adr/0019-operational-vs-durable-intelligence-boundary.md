# ADR-0019: Operational vs. Durable Intelligence Boundary

## Status
Proposed

## Date

2026-08-27

## Context

FlossWare AI systems produce both rapidly changing operational learning data and durable knowledge that can be shared across executions. Treating these as the same class of data risks either turning Git into a telemetry store or forcing durable architectural knowledge into infrastructure that is difficult to version and distribute.

Thompson Sampling and genetic algorithms make the distinction especially important. Individual rewards, observations, and transient populations may change continuously, while priors, aggregated results, promoted populations, and winning configurations may be valuable for long-term reuse.

## Scope

Applies to AI learning, model selection, routing, evaluation, agent orchestration, Thompson Sampling, genetic algorithms, and related FlossWare systems.

## Non-goals

- Does not require a specific database or telemetry platform.
- Does not prohibit exporting operational data for analysis.
- Does not require every durable artifact to be stored in Git.
- Does not define the schemas of individual intelligence artifacts.

## Decision

FlossWare SHALL distinguish **operational intelligence** from **durable shared intelligence**.

### Operational intelligence

Operational intelligence SHOULD remain in an operational store appropriate to its volume and access pattern. Examples include:

- Raw Thompson Sampling observations and rewards.
- High-frequency model-selection events.
- Execution telemetry and detailed traces.
- Transient genetic algorithm populations.
- Intermediate fitness evaluations.
- Large datasets and embeddings.
- Short-lived experimental state.

Operational intelligence SHALL NOT be committed to Git merely because it is related to learning.

### Durable shared intelligence

Durable intelligence MAY be promoted into versioned artifacts suitable for Git distribution. Examples include:

- Initial or learned Thompson priors and posterior snapshots.
- Aggregated benchmark and evaluation results.
- Model capability profiles.
- Promoted routing policies.
- Genetic algorithm winning configurations or useful population snapshots.
- Experiment manifests and reproducibility metadata.
- Stable evaluation definitions and schemas.

Promotion SHALL be based on durability, reuse value, reproducibility, and reasonable repository churn rather than on the mere existence of a learning result.

### Boundary rule

A practical default SHALL be:

> If another machine or agent needs the information to make a materially better or reproducible decision in the future, and the information is stable enough to version, it is a candidate for durable shared intelligence. If it changes frequently or primarily describes execution history, it belongs in operational storage.

Systems MAY retain both forms: operational observations remain available for learning, while promoted summaries or learned state are distributed as durable intelligence.

## Consequences

### Positive

- Prevents Git repositories from becoming telemetry databases.
- Makes the distinction between learning and shared knowledge explicit.
- Enables efficient aggregation followed by selective promotion.
- Supports reproducibility without preserving every execution event.
- Gives FlossWare a consistent boundary across AI components.

### Negative

- Promotion criteria require judgment and eventually automation.
- Some information may need both operational and durable representations.
- Consumers need to understand which artifacts are authoritative for their use case.

## Alternatives Considered

### Put everything in Git

Rejected because operational learning data is too dynamic and voluminous for Git to be an effective primary store.

### Put everything in databases

Rejected because durable knowledge benefits from version control, review, reproducibility, portability, and offline distribution.

### No formal boundary

Rejected because different FlossWare components would otherwise make incompatible storage and distribution decisions.

### Explicit operational/durable boundary (chosen)

Provides a simple architectural rule while allowing implementation-specific storage choices.

## Related ADRs

- [ADR-0013](0010-bandit-based-model-selection.md) — Bandit-Based Model Selection
- [ADR-0016](ADR-0016-configuration-as-source-of-truth.md) — Configuration as Source of Truth
- [ADR-0023](0018-git-based-shared-intelligence.md) — Git-Based Shared Intelligence
- ADR-0025 — Intelligence Promotion, Provenance, and Versioning
