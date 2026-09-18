# ADR-0009: Multi-Model Consensus for Quality Gates

## Status
Accepted

## Date
2026-08-05

## Context

AI-assisted code review, design evaluation, and decision-making can use a single model or multiple models. Single-model review is fast and cheap but blind to that model's systematic biases. Multi-model consensus introduces diverse perspectives at the cost of latency and API calls.

Internal FlossWare evaluations (multi-round model fleets used in development and review workflows) observed patterns consistent with:

- Multi-model review surfacing defects that single-model review and unit tests missed (e.g. shared-state races, ordering errors, weak validation).
- Consensus not reliably outperforming the single best model on simple factual tasks (math, lookup, logic).
- A substantial share of model-reported “failures” in code review being non-reproducible (often tied to truncated or incomplete context) rather than confirmed defects.

These are **internal operational observations**, not externally published reproducible research. Decisions below stand on architectural risk management; numbers from any specific experiment run SHOULD NOT be treated as universal constants.

The value of consensus is highest when the task is subjective, multi-dimensional, or when correctness is hard to verify mechanically.

## Scope

Quality gates for design review, high-impact code review, and architecture decisions in FlossWare AI-assisted workflows.

## Non-goals

- Does not mandate consensus for every prompt or low-stakes query.
- Does not specify a particular vendor product or voting product SKU.

## Decision

Multi-model consensus SHALL be used as a quality gate for the following categories:

- **Design reviews** — before implementation begins, not after.
- **Code reviews** — for changes affecting shared infrastructure, routing logic, or security boundaries.
- **Architecture decisions** — when multiple valid approaches exist.

Single-model evaluation SHOULD be preferred for:

- Simple factual queries with mechanically verifiable answers.
- Tasks where latency matters more than thoroughness.
- Exploratory or brainstorming phases where diversity of thought comes from iteration, not parallel voting.

### Consensus panel composition

- Panels SHOULD include models from at least **3 distinct diversity units** (see below).
- Panels SHOULD use a minimum of 3 voters; 5–7 SHOULD be used for quality gates.
- The same model SHALL NOT serve as both generator and sole evaluator of an output (anti-self-referential safeguard).

### Diversity units (not API “providers”)

**Diversity unit** means an independent **model family / training organization lineage**, not merely a different URL or reseller.

This is distinct from **provider** in [ADR-0002](0006-ai-provider-abstraction.md) / [ADR-0015](0012-dynamic-ai-model-inventory.md), which means an integration adapter (endpoint, auth, call format).

| Counts toward diversity? | Example |
|--------------------------|---------|
| **Yes** | Distinct model families from different training organizations |
| **Weak / partial** | Different model families from the **same** organization |
| **No** | Same model exposed via direct API vs cloud proxy vs marketplace |
| **No** | Same weights behind two endpoint hostnames or regions |

Rules:

- Operational configs that say “3 distinct providers” for consensus SHALL mean **3 diversity units** as defined above.
- Hosting platform alone SHALL NOT satisfy diversity if the underlying model family is the same.
- When only correlated models are available, panels SHOULD document reduced diversity and prefer human review for contested findings.

### Handling disagreement

- Majority vote is sufficient for binary decisions (accept/reject).
- For multi-dimensional reviews (correctness, security, performance), each dimension SHOULD be scored independently.
- Contested findings (near 50/50 split) SHOULD be flagged for human review rather than auto-resolved.

### False positive mitigation

- Review prompts SHALL include sufficient context for the model to evaluate (full imports, type signatures, surrounding code).
- Findings SHOULD be adversarially verified: a different model from a different **diversity unit** attempts to reproduce or refute each finding before it is reported.
- Findings that cannot be reproduced by at least one independent verifier SHOULD be discarded.

## Consequences

### Positive
- Catches real defects that single-model review misses.
- Reduces systematic bias from any single model lineage.
- Review-before-build reduces costly rework vs review-only-after-build.
- Adversarial verification filters hallucinated findings.
- Diversity definition is testable in panel configuration.

### Negative
- Higher latency and API cost per review cycle.
- Consensus can still converge on a wrong answer when models share training data biases.
- Requires infrastructure to fan out prompts and collect votes.
- Rate limits across integration providers can cause partial panel failures; retry logic is necessary.

## Alternatives Considered

### Single-model review only
Rejected — misses defects due to systematic blind spots observed in internal evaluations.

### All decisions by consensus (no single-model path)
Rejected — overkill for simple factual tasks; wastes API budget.

### Diversity = distinct API endpoints only
Rejected — allows false confidence when the same model is reached through multiple hosts.

### Multi-model consensus with task-appropriate scope and lineage-based diversity (chosen)
Balances thoroughness for high-stakes decisions with efficiency for routine operations.

## Related ADRs
- [ADR-0001](ADR-0001-explicit-opt-in-cross-cutting-behavior.md) — Explicit Opt-In Cross-Cutting Behavior
- [ADR-0002](0006-ai-provider-abstraction.md) — AI Provider Abstraction
- [ADR-0008](ADR-0008-free-first-modular-platform.md) — Free-First Modular Platform
- [ADR-0013](0010-bandit-based-model-selection.md) — Bandit-Based Model Selection
- [ADR-0015](0012-dynamic-ai-model-inventory.md) — Dynamic AI Model Inventory
