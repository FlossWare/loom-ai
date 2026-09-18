# ADR-0018: Git-Based Shared Intelligence

## Status
Proposed

## Date

2026-08-27

## Context

FlossWare AI components increasingly learn or accumulate durable information about model selection, agent behavior, evaluation results, Thompson Sampling, genetic algorithms, and routing. This information can be useful across machines, repositories, agents, and execution environments.

Operational learning state is often high-volume and rapidly changing, while a smaller subset of learned information is durable, reproducible, reviewable, and useful as shared system knowledge. FlossWare already uses Git as the authoritative and versioned distribution mechanism for source, configuration, architecture decisions, and reproducible artifacts.

The ecosystem therefore needs an explicit architectural decision about whether Git may also distribute durable shared intelligence without turning Git into an operational telemetry database.

## Scope

Applies to FlossWare components that produce or consume durable AI intelligence, including model routing, Thompson Sampling, genetic algorithms, agent orchestration, evaluation, and benchmark systems.

## Non-goals

- Does not make Git a replacement for operational databases, telemetry systems, or event streams.
- Does not require raw observations or high-frequency learning state to be committed to Git.
- Does not prescribe a particular serialization format for intelligence artifacts.
- Does not require every learned result to become shared intelligence.

## Decision

Git SHALL be an approved distribution and provenance mechanism for durable shared intelligence.

Durable intelligence MAY include:

- Thompson Sampling priors and promoted posterior snapshots.
- Model and provider capability profiles.
- Aggregated benchmark and evaluation results.
- Routing policies and promoted routing knowledge.
- Genetic algorithm population snapshots and promoted configurations.
- Fitness-function definitions and experiment manifests.
- Prompt and instruction versions that materially affect evaluation or routing behavior.
- Shared evaluation definitions and reproducibility metadata.
- Schemas and compatibility metadata for intelligence artifacts.

Shared intelligence artifacts SHALL be versioned and traceable to their generating source, experiment, or evaluation context where practical.

Git-distributed intelligence SHALL remain derived or promoted knowledge rather than an excuse to bypass the authoritative source of source code or configuration. The artifact itself SHALL identify the schema/version necessary for compatible consumers when applicable.

Repositories consuming shared intelligence SHOULD validate artifact schema, compatibility, integrity, and provenance before use.

Shared intelligence MAY be distributed through a dedicated repository or an appropriate existing FlossWare repository, provided ownership and authority are unambiguous.

## Consequences

### Positive

- Learned knowledge becomes portable across machines and agents.
- Git history provides provenance, review, rollback, and reproducibility.
- Shared intelligence can be consumed without requiring every component to access a central learning database.
- Model-routing and agent systems can improve collectively rather than relearning identical facts independently.
- Intelligence changes can use normal CI and review mechanisms.

### Negative

- Poorly selected data can cause repository churn and unnecessary commits.
- Learned artifacts require schemas and compatibility discipline.
- Promotion of intelligence introduces another lifecycle to maintain.
- Incorrect shared intelligence can propagate across consumers unless validation and provenance are enforced.

## Alternatives Considered

### Keep all learned state in operational databases

Rejected as the only mechanism because durable knowledge then becomes harder to distribute, review, reproduce, and consume across otherwise independent environments.

### Commit all telemetry to Git

Rejected because Git is not an operational telemetry store and high-frequency observations would create excessive churn and poor query characteristics.

### Centralized intelligence service only

Rejected as the sole mechanism because it creates unnecessary runtime coupling and makes offline, portable, and independently operated FlossWare components harder to support.

### Git for durable shared intelligence (chosen)

Provides portable, versioned, reviewable distribution while preserving operational stores for high-volume and rapidly changing state.

## Related ADRs

- [ADR-0013](0010-bandit-based-model-selection.md) — Bandit-Based Model Selection
- [ADR-0016](ADR-0016-configuration-as-source-of-truth.md) — Configuration as Source of Truth
- [ADR-0021](0017-provider-neutral-ai-selection.md) — Provider-Neutral AI Selection
- [ADR-0022](ADR-0022-reproducible-build-artifacts-and-distribution.md) — Reproducible Build Artifacts and Distribution
- ADR-0024 — Operational vs. Durable Intelligence Boundary
- ADR-0025 — Intelligence Promotion, Provenance, and Versioning
