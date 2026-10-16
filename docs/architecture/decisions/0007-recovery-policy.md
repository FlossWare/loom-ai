# ADR-0007: Recovery Policy

- **Status:** Proposed
- **Date:** 2026-10-16
- **Related issue:** #1022

## Context

Execution can fail because of transient provider errors, timeouts, rate limits,
invalid requests, unavailable capabilities, verification failures, process
termination, or other causes. Treating every failure as a retry, or embedding
recovery behavior inside a provider adapter, risks duplicate side effects,
unbounded cost, loss of provenance, and inconsistent behavior across runtimes.

Loom needs a provider-neutral recovery-policy boundary that decides what action
is permitted after a failure while leaving execution, routing, health, economics,
and verification as separate concerns.

## Decision

A **Recovery Policy** is a versioned policy that maps a classified execution
condition and current execution state to an explicit recovery decision.

A recovery decision MAY choose to:

- retry the same operation;
- resume from a supported checkpoint or persisted state;
- substitute another eligible provider/model/Worker;
- replan the remaining work;
- request human intervention;
- terminate with an explicit failure or cancellation outcome.

The policy does not execute the recovery action itself. The Orchestrator or
execution owner applies the decision through the existing execution and routing
contracts.

## Inputs

A recovery decision SHOULD consider:

- failure category and available failure evidence;
- execution and step identity, attempt count, and current lifecycle state;
- whether the operation is idempotent or has externally visible side effects;
- checkpoint/resume availability and validity;
- remaining time, cost, and retry budgets;
- current provider/model health signals;
- candidates and capabilities available for substitution;
- applicable safety, authorization, and caller constraints;
- Recovery Policy identity/version and its configuration.

Health and economics are inputs, not properties owned by the recovery policy.
The policy MUST NOT infer that a failure is transient solely because retrying is
convenient.

## Failure classification and action

Implementations SHOULD classify failures at least sufficiently to distinguish:

- transient or potentially transient infrastructure/provider failures;
- rate limits and capacity exhaustion;
- request/validation failures unlikely to succeed unchanged;
- capability or authorization failures;
- execution timeout or cancellation;
- verification/acceptance failure;
- unrecoverable state corruption or missing required artifacts.

The policy MUST produce an explicit decision for the classified condition. It
MUST NOT silently turn a failed or cancelled execution into a successful outcome.

### Retry

A retry decision MUST respect a bounded attempt budget and time/cost constraints.
The policy SHOULD specify whether the initial attempt counts toward the total
attempt limit and MUST make retry-count semantics unambiguous.

Retries of operations with external side effects MUST require idempotency,
deduplication, compensation, or another explicit safety mechanism. A retry MUST
NOT duplicate a non-idempotent action merely because the prior response was lost.

Backoff, jitter, and provider-specific retry hints MAY be used as implementation
strategies, but their use and limits SHOULD be represented in policy configuration
or decision provenance where they materially affect behavior.

### Resume and checkpoint

A resume decision MUST identify the execution state/checkpoint from which
execution will continue and verify that it is valid for the current policy and
implementation version.

Resume MUST preserve the stable execution identity and relevant provenance. It
MUST NOT imply that expired or missing context/artifacts remain available.

### Substitute and replan

Substitution MUST select only a candidate that satisfies the applicable hard
constraints and capability requirements. Recovery MUST NOT bypass the routing
policy's feasibility rules or silently relax safety, authorization, or hard budget
limits.

Replanning MAY change the remaining execution plan, but MUST preserve the original
Intent, the reason for recovery, prior results, and the provenance needed to
understand the revised plan. Earlier execution results MUST NOT be overwritten by
the replan.

### Terminal failure or human intervention

If no permitted recovery action remains, the policy MUST choose an explicit
terminal outcome or human-intervention path. The final result MUST retain the
failure category and relevant evidence. An implementation MUST NOT retry
indefinitely or claim success because the recovery budget was exhausted.

## Budgets and safety

Recovery policy MUST respect caller and system limits for attempts, elapsed time,
cost, concurrency, and resource use where those limits are configured.

A recovery decision MUST NOT override authorization, safety policy, required
capabilities, or explicit hard budget constraints. Any human approval requirement
remains in force across retry, resume, substitution, and replan actions.

## Provenance

Each recovery decision SHOULD record:

- decision identity and timestamp;
- Recovery Policy identity/version;
- execution/step identity and attempt count;
- failure category and evidence references;
- action selected and why it was permitted;
- applicable budget state and relevant health/capability references;
- the resulting execution identity/checkpoint/candidate, where applicable.

The record composes with Decision Provenance and ExecutionTrace. It MUST NOT
require private chain-of-thought or expose secrets.

## Relationship to other contracts

Recovery Policy is distinct from:

- **Routing Policy:** chooses an eligible candidate for an operation; recovery
  decides whether to retry, resume, substitute, replan, escalate, or stop.
- **Provider/Model Health:** supplies time-scoped operational signals.
- **Execution Economics:** supplies actual/estimated cost, latency, and usage.
- **Context Artifact:** defines context identity, provenance, and availability.
- **Execution Outcome and Feedback:** assess whether the task succeeded and may
  provide signals for future policy evaluation.
- **ExecutionTrace and Decision Provenance:** record what happened and why a
  recovery action was selected.

These contracts SHOULD compose through stable identifiers and references rather
than duplicating each other's state or semantics.

## Conformance and evolution

Implementations SHOULD test that:

1. retries respect explicit attempt/time/cost limits;
2. non-idempotent actions are not repeated without a safety mechanism;
3. resume preserves execution identity and verifies checkpoint validity;
4. substitution respects routing feasibility and hard constraints;
5. replan preserves prior results and provenance;
6. terminal failure remains distinct from successful completion;
7. every recovery action is attributable to a policy version and failure evidence.

No retry library, orchestration framework, provider SDK, or particular recovery
algorithm is normative.

## Consequences

### Positive

- Recovery behavior is explicit, bounded, and auditable.
- Retries are less likely to duplicate side effects or exhaust budgets.
- Resume, substitution, and replan can be compared across implementations.
- Health, cost, routing, and outcome semantics remain independently evolvable.

### Negative

- Failure classification and checkpoint validity require consistent contracts.
- Implementations must track retry budgets and recovery provenance.
- Some operations cannot safely be retried or resumed and must fail or escalate.

## Non-goals

This ADR does not define a universal retry count, backoff formula, checkpoint
format, compensation framework, or provider-specific recovery API.
