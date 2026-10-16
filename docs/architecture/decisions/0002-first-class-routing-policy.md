# ADR-0002: First-Class Routing Policy

- **Status:** Proposed
- **Date:** 2026-10-16
- **Related issue:** #1017

## Context

Loom needs to choose among eligible model/provider implementations without making
one routing algorithm, provider SDK, or optimization technique part of the AI-domain
contract. If routing remains implicit inside provider adapters or orchestration
code, its inputs, constraints, decision provenance, and evolution become difficult
to inspect or reproduce.

Rules, capability filtering, cost-aware selection, Thompson sampling, contextual
bandits, and future policies can all implement useful selection behavior. They are
different strategies for satisfying the same routing-policy boundary, not separate
protocols.

## Decision

Routing is represented as a **first-class, provider-neutral policy contract**.
A routing component evaluates a declared request and candidate set under an
identified policy and produces a structured selection decision.

The contract describes the policy's inputs, constraints, output, identity, and
provenance. It does not prescribe an algorithm or require a single universal
routing implementation.

## Inputs

A routing request SHOULD make the following information explicit where applicable:

- **Candidate set:** stable identities for the candidate model/provider
  implementations being considered.
- **Requirements:** capabilities required for the requested operation, including
  relevant modalities, tool support, and context/input limits.
- **Hard constraints:** conditions a candidate must satisfy, such as authorization,
  capability feasibility, explicit budget limits, or caller restrictions.
- **Preferences and objectives:** soft goals used to rank feasible candidates,
  such as latency, cost, quality estimates, or workload-specific preferences.
- **Operational signals:** references to current availability/health information
  and execution-economics metadata where available.
- **Request context:** task requirements, deadlines, and other declared context
  that materially affects selection.
- **Policy reference:** policy identity, version, and applicable configuration.

The capability, health, and economics contracts are defined separately. Routing
consumes those signals; it does not become the authority that collects provider
health, accounts for actual usage, or defines model capability semantics.

Credentials, secrets, and private reasoning traces are not routing-policy inputs.

## Feasibility and selection

A conforming routing policy MUST distinguish **hard feasibility** from **soft
preference**:

1. Determine which candidates satisfy the declared hard constraints and required
   capabilities.
2. Rank or select only among candidates that remain eligible.
3. Return an explicit no-feasible-candidate outcome if no candidate satisfies the
   hard constraints.

A policy MUST NOT silently relax authorization, safety, required capabilities,
or explicit hard budget constraints merely to return a candidate. Any permitted
fallback or constraint relaxation must be an explicit, separately authorized
decision with provenance.

The policy MAY use rules, scoring, ranking, randomized selection, learned
estimates, or another algorithm to choose among eligible candidates. The contract
does not mandate a ranking formula, reward model, exploration strategy, or
optimization objective.

## Decision output

A routing decision SHOULD provide enough structured information to understand
and reproduce the selection where the underlying policy permits it:

- decision identity and timestamp;
- policy identity and version;
- selected candidate identity, or an explicit no-feasible-candidate outcome;
- candidate identities considered;
- eligibility/exclusion outcomes and concise reasons;
- hard constraints and soft objectives applied;
- relevant decision signals or scores where meaningful;
- random seed or equivalent decision-state provenance when a stochastic policy
  uses it and recording it is safe and practical.

The exact fields and representation remain language-neutral. A policy need not
publish proprietary algorithm internals, but it MUST expose enough structured
provenance to explain which declared constraints and signals materially affected
the decision. It MUST NOT require or emit private chain-of-thought.

## Identity, versioning, and reproducibility

A routing policy MUST have a stable identity and version. Configuration changes
that materially alter policy semantics SHOULD produce a new version or another
explicitly documented compatibility boundary.

The decision record MUST identify the policy version used. Where policy behavior
is stochastic or depends on changing operational signals, the record SHOULD
capture the relevant signal snapshot and randomness provenance when safe and
available. Reproducibility means that the inputs and decision context can be
inspected; it does not imply that every live provider or stochastic decision is
guaranteed to return the same candidate.

## Boundaries

Routing policy is separate from the following concerns:

- **Capability profile:** declares what a model/provider implementation can do.
- **Provider/model health:** reports availability and operational health.
- **Execution economics:** records estimated or actual usage, cost, latency, and
  cache behavior.
- **Recovery policy:** decides whether and how to retry, substitute, resume, or
  replan after an execution problem.
- **Evaluation and feedback:** measures task outcomes and provides signals that
  may inform future policy versions.
- **Decision provenance:** standardizes the evidence recorded about a particular
  routing decision.

These contracts may compose. They MUST NOT be collapsed into a single vendor-
specific routing object merely because one implementation uses them together.

A routing decision selects an implementation to attempt; it does not establish
that the requested task succeeded. Task outcome and acceptance remain separate
from transport completion and model selection.

## Consequences

### Positive

- Routing can evolve independently of provider SDKs and execution orchestration.
- Different algorithms can be compared behind one observable policy boundary.
- Hard constraints remain distinguishable from optimization preferences.
- Decisions gain stable identity, versioning, and inspectable provenance.
- Learning and evaluation can improve future policy versions without redefining
  the routing contract.

### Negative

- Candidate capability, health, economics, and decision-provenance contracts must
  be defined precisely enough to interoperate.
- Policy versioning and decision records add lifecycle and storage obligations.
- Some algorithms cannot provide fully deterministic replay; the contract must
  distinguish recorded decision context from guaranteed reproducibility.

## Non-goals

This ADR does not:

- mandate Thompson sampling, contextual bandits, rules, or any other algorithm;
- define a vendor-specific model/provider API;
- make routing the authority for credentials, authorization, or safety policy;
- combine execution economics, health collection, recovery, or evaluation into the
  routing policy;
- require disclosure of private model reasoning;
- define the final JSON schema or programming-language API.

## Relationship to other decisions

This decision complements the model capability/profile, decision provenance,
execution economics, provider/model health, recovery policy, and evaluation
contracts tracked in issues #1018–#1025. Those concerns should compose through
explicit references and stable semantics rather than duplicate or contradict one
another.
