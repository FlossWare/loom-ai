# ADR-0004: Decision Provenance

- **Status:** Proposed
- **Date:** 2026-10-16
- **Related issue:** #1020

## Context

Loom decisions affect execution, routing, recovery, policy enforcement, and
downstream learning. A trace can show that an execution occurred, but it may not
identify which policy version, candidate set, constraints, and operational signals
led to a particular selection.

Decision provenance must make those inputs and outcomes inspectable without
coupling Loom to a routing algorithm, provider, storage system, or private model
reasoning format.

## Decision

A **Decision Provenance** record is a structured, provider-neutral record of a
specific execution decision and the declared inputs that materially influenced it.

Decision provenance is distinct from an overall ExecutionTrace:

- an ExecutionTrace records the lifecycle and evidence of an execution;
- Decision Provenance identifies a particular decision within or associated with
  that execution and records the policy, candidates, constraints, signals, and
  selected outcome.

A decision record MAY be embedded in an execution trace or linked by stable
identifiers. The contract does not prescribe a storage or transport format.

## Required semantic information

A finalized decision record MUST identify the decision and its outcome. Where
applicable, it SHOULD include:

- **Identity:** decision ID, decision type, timestamp, and related execution/run
  identity.
- **Policy:** policy identity and version, plus a reference to the effective
  configuration or profile version.
- **Candidates:** candidate identities considered and their eligibility or
  exclusion outcomes.
- **Constraints:** material hard constraints, exclusions, authorization boundaries,
  and soft objectives applied.
- **Selected outcome:** the selected candidate/action, or an explicit no-selection
  or terminal-decision outcome.
- **Decision signals:** structured references or values for the signals that
  materially affected the choice, including source and observation time where
  available.
- **Provenance references:** links to the relevant capability profile, health
  observation, economics record, execution evidence, or other input artifact.
- **Rationale:** a concise structured explanation of the material factors, not a
  private reasoning transcript.

The exact fields depend on decision type. A routing decision may record candidate
models and provider identities; a recovery decision may record the failed step,
attempt count, recovery policy, and selected action. The shared semantics remain
stable while type-specific extensions remain explicit.

## Provenance quality

A decision record SHOULD distinguish:

- declared configuration and hard constraints;
- observed operational signals;
- estimated or predicted values;
- policy-derived scores or ranks;
- the final decision and its outcome.

The record SHOULD preserve version and time references needed to understand which
facts were available at decision time. A later health observation or policy update
MUST NOT silently rewrite the historical explanation of an earlier decision.

A finalized record SHOULD be immutable. If a correction is required, the
implementation SHOULD emit a correction or superseding record linked to the
original rather than silently overwriting the decision history.

Provenance supports inspection and replay analysis; it does not guarantee that a
future run will make the same decision when providers, availability, external
signals, or stochastic policy state have changed.

## Privacy and security boundary

Decision provenance MUST NOT require or expose model private chain-of-thought.
It MUST NOT record credentials, secret material, or unauthorized private inputs.

Concise rationale and structured decision signals are evidence about the
application's decision, not a transcript of hidden model reasoning. Sensitive
candidate metadata, policy configuration, or user data MUST be redacted or
restricted according to the applicable authorization and retention rules.

A decision record SHOULD identify the source and scope of its inputs without
copying large or sensitive artifacts when stable references are sufficient.

## Relationship to other contracts

Decision Provenance composes with, but does not replace:

- **ExecutionTrace:** overall execution lifecycle, actions, results, and evidence.
- **Routing Policy:** selection inputs, feasibility rules, policy identity/version,
  and selection output.
- **Model Capability Profile:** the declared capability facts used for feasibility.
- **Provider/Model Health:** time-scoped availability and operational observations.
- **Execution Economics:** usage, cost, latency, and cache-related signals.
- **Recovery Policy:** retry, fallback, substitution, resume, replan, and terminal
  decisions.
- **Execution Outcome and Feedback:** evaluation and downstream feedback about
  the result of execution.

These contracts SHOULD use stable identifiers and references rather than define
competing provenance formats for each algorithm.

## Conformance and evolution

Implementations that emit decision provenance SHOULD test that:

1. each record has a stable identity, type, timestamp, and linked execution or
   decision context where applicable;
2. policy and profile versions are preserved;
3. material candidates, constraints, exclusions, and selection outcome are
   represented;
4. signal provenance and observation time are retained where available;
5. secrets and private reasoning are excluded;
6. later observations do not silently mutate finalized historical decisions;
7. decision records can be correlated with the associated ExecutionTrace.

The representation may be JSON or another suitable serialization. No Python class,
database schema, observability vendor, or routing algorithm is normative.

## Consequences

### Positive

- Routing and recovery decisions become inspectable and attributable.
- Learning and evaluation can consume structured decision history without scraping
  logs or depending on private reasoning traces.
- Policy changes can be compared against the decisions they produced.
- Operational signals remain distinct from policy configuration and outcomes.

### Negative

- Decision records require stable identity, version, and retention semantics.
- Implementations must select useful signals without copying excessive or sensitive
  data.
- Some algorithms cannot be fully replayed; provenance must not overstate
  determinism.

## Non-goals

This ADR does not define a routing algorithm, evaluation metric, recovery strategy,
trace storage backend, or private reasoning format. It does not require every
internal implementation choice to become public evidence; only the declared,
externally meaningful decision inputs and outcomes are in scope.
