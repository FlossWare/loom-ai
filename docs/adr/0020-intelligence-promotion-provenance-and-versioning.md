# ADR-0020: Intelligence Promotion, Provenance, and Versioning

## Status
Proposed

## Date

2026-08-27

## Context

FlossWare AI systems can learn from operational observations and produce candidate improvements to model routing, agent behavior, Thompson Sampling state, genetic algorithm configurations, and evaluation knowledge. If these improvements are shared directly, incorrect or incompatible learning can propagate across the ecosystem.

Durable shared intelligence therefore needs a controlled promotion lifecycle that preserves provenance, supports validation, permits rollback, and remains compatible with Git-based distribution.

## Scope

Applies to promotion of durable AI intelligence from operational systems into Git-distributed artifacts across FlossWare.

## Non-goals

- Does not require human approval for every intelligence update.
- Does not mandate a particular CI platform, database, serialization format, or Git hosting workflow.
- Does not define the learning algorithms themselves.
- Does not require every candidate learning result to be promoted.

## Decision

Durable shared intelligence SHALL follow a promotion lifecycle:

```text
Operational observations
        ↓
Aggregation / learning
        ↓
Candidate intelligence
        ↓
Validation
        ↓
Versioned Git change
        ↓
Review or automated acceptance
        ↓
Published shared intelligence
        ↓
Fleet consumption
```

### Candidate generation

Learning systems MAY generate candidate intelligence automatically. Candidate generation SHALL NOT by itself make the result authoritative shared intelligence.

### Validation

Before promotion, candidates SHOULD be validated for:

- Schema and format compatibility.
- Internal consistency and integrity.
- Benchmark or evaluation performance where applicable.
- Regression against the currently promoted state.
- Provenance and reproducibility metadata.
- Policy and environment constraints.

Safety, security, privacy, licensing, and deployment constraints SHALL take precedence over measured performance.

### Versioning

Every promoted intelligence artifact SHALL have a version or commit identity sufficient for consumers to determine which representation they are using.

Breaking schema changes SHALL NOT silently replace an incompatible artifact. Consumers SHOULD reject unsupported schema versions rather than guessing how to interpret them.

### Provenance

Promoted intelligence SHOULD identify, where applicable:

- Generating component and version.
- Source commit or release.
- Experiment or evaluation identifier.
- Input dataset or benchmark identifier.
- Generation timestamp.
- Learning algorithm and relevant parameters.
- Parent artifact or prior version.
- Validation results.

Sensitive data, credentials, private prompts, private user information, and other non-shareable material SHALL NOT be embedded in shared intelligence artifacts merely to improve provenance.

### Git workflow

A candidate SHOULD normally enter the shared intelligence repository through a normal Git change or pull request when the environment supports review workflows.

Automated promotion MAY merge directly when explicitly authorized by policy and when required validation gates pass.

Consumers SHALL be able to roll back to a previously known-good intelligence version through normal Git versioning or an equivalent immutable reference.

### Attribution and reproducibility

Intelligence changes SHOULD preserve enough information to reproduce or independently evaluate the reason for promotion. Aggregated results are preferred over raw telemetry when the raw data is unnecessary for reproduction.

## Consequences

### Positive

- Prevents unvalidated learning from becoming ecosystem-wide behavior.
- Provides auditability and rollback.
- Makes model and agent improvements reproducible.
- Supports both human-reviewed and automated promotion.
- Creates a consistent lifecycle for Thompson, GA, routing, and evaluation knowledge.

### Negative

- Promotion adds validation and metadata requirements.
- Automated promotion requires trustworthy quality gates.
- Provenance can become expensive if poorly scoped.
- Rollback requires consumers to retain compatibility with prior versions where practical.

## Alternatives Considered

### Automatically share every learning result

Rejected because transient or poorly validated results could propagate regressions throughout the fleet.

### Require manual approval for every update

Rejected as the universal rule because safe, well-validated numerical updates can be frequent and automation is desirable.

### Centralized immutable intelligence service

Rejected as the sole mechanism because Git provides useful review, history, portability, and offline distribution characteristics.

### Validated versioned promotion (chosen)

Balances automation with safety and provides a clear lifecycle from observations to trusted shared intelligence.

## Related ADRs

- [ADR-0013](0010-bandit-based-model-selection.md) — Bandit-Based Model Selection
- [ADR-0022](ADR-0022-reproducible-build-artifacts-and-distribution.md) — Reproducible Build Artifacts and Distribution
- [ADR-0023](0018-git-based-shared-intelligence.md) — Git-Based Shared Intelligence
- [ADR-0024](0019-operational-vs-durable-intelligence-boundary.md) — Operational vs. Durable Intelligence Boundary
