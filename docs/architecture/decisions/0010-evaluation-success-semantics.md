# ADR-0010: Evaluation and Success Semantics

- **Status:** Proposed
- **Date:** 2026-10-16
- **Related issue:** #1025

## Context

An execution can complete at the transport or process level while failing to meet
the requested objective. A model can return a response, a Worker can exit with a
success status, and an HTTP request can return 200 even when the output is
incorrect, incomplete, unsafe, or unverified.

If these events are all called "success", routing, learning, feedback, and
operator reporting receive misleading signals. Loom needs shared semantics for
evaluation status and task success without imposing one universal evaluator or
scoring algorithm.

## Decision

**Execution status and task outcome are separate dimensions.**

- Execution status describes what happened while running an operation.
- Evaluation status describes what the available evidence says about the requested
  criteria.
- Feedback records a human or system signal about the result and remains distinct
  from an evaluation judgment.

A completed invocation MUST NOT be treated as successful task completion unless
the applicable acceptance criteria have been evaluated and the assessment supports
that conclusion.

## Evaluation record

An Evaluation record SHOULD identify:

- the execution/result being evaluated;
- the Intent and acceptance criteria or evaluation target;
- criteria identity/version;
- evaluator identity and evaluator/policy version where applicable;
- evaluation status;
- evidence and measurements supporting the assessment;
- evaluation time and provenance;
- score/confidence/uncertainty where meaningful and defined by the evaluator.

The evaluator MAY be a deterministic test suite, verifier Worker, model-based
judge, human reviewer, downstream consumer, or another declared mechanism. The
contract does not prescribe one evaluator type.

## Portable evaluation statuses

A conforming evaluation representation SHOULD distinguish at least:

- **met:** the assessed criteria are supported by sufficient evidence;
- **partially_met:** some criteria are satisfied and others are not satisfied or
  remain outstanding;
- **not_met:** the assessed criteria are not satisfied;
- **inconclusive:** an assessment was attempted, but the available evidence does
  not support a reliable conclusion;
- **not_evaluated:** no assessment has been performed for the relevant criteria.

Implementations MAY provide more detailed states, but MUST preserve a clear mapping
to these meanings. Inconclusive and not-evaluated MUST NOT be silently mapped to
met.

A failure to execute, a cancellation, and an evaluation that determines the task
criteria were not met are distinct facts. They may all prevent task completion,
but they have different causes and recovery implications.

## Success semantics

Task success is relative to declared criteria and the applicable evaluation
policy. It is not a universal property of a model response.

- If required acceptance criteria are explicitly evaluated and met, the outcome
  MAY be reported as successful.
- If required criteria are partially met or not met, the result MUST preserve that
  distinction rather than collapsing it to success.
- If criteria have not been evaluated, the task outcome MUST remain unknown or
  not-evaluated even if the execution completed normally.
- If evidence is insufficient or conflicting, the outcome SHOULD be inconclusive
  unless a declared evaluation policy defines a justified resolution.
- Optional quality measurements MAY be reported separately from required
  acceptance criteria; a high optional score MUST NOT override a failed hard
  requirement.

Any aggregate success rule MUST identify the criteria and policy version used.
The contract does not define a universal confidence threshold, weighted score, or
majority-vote rule.

## Objective criteria and subjective feedback

Evaluation and feedback are related but not interchangeable:

- **Objective or declared criteria** can be assessed against tests, schema checks,
  verifier results, policy checks, or other explicit acceptance requirements.
- **Subjective feedback** expresses a person's or downstream consumer's judgment,
  preference, or satisfaction.
- **Operational measurements** such as cost, latency, token usage, and provider
  health can inform an evaluation but do not independently establish task success.

A human may override or supplement an automated assessment only through an
explicit, attributable evaluation or feedback record. The original assessment
MUST remain inspectable.

Feedback signals and outcome records are defined by the Execution Outcome and
Feedback Contract. This ADR defines the meaning of evaluation status and success,
not a universal feedback aggregation strategy.

## Multiple assessments and aggregation

One execution MAY have multiple evaluations against different criteria, versions,
or perspectives. Implementations MUST retain the identity of each assessment and
MUST NOT silently overwrite a prior evaluation when new evidence arrives.

If a consumer needs one aggregate outcome, the aggregation policy SHOULD define:

- which criteria are required;
- how partial, inconclusive, and missing assessments are handled;
- whether human review is required;
- how conflicting evaluations are resolved;
- the policy version and evidence used.

An aggregate outcome MUST preserve references to its contributing assessments.

## Relationship to execution and learning

Evaluation results MAY inform recovery, model/provider comparison, routing-policy
improvement, or learning. An evaluation result MUST NOT itself trigger an
unreviewed policy change unless the applicable policy explicitly authorizes that
action.

Execution Economics, Provider/Model Health, Context Artifacts, Decision Provenance,
and ExecutionTrace provide related evidence but remain separate contracts.
Successful transport, low cost, healthy provider status, or a plausible response
does not substitute for evaluating the task criteria.

## Provenance, privacy, and integrity

Evaluation SHOULD retain evidence references, criteria/evaluator versions, and
time information sufficient to explain the assessment. It MUST NOT require or
expose private chain-of-thought.

Sensitive source material and user feedback MUST follow applicable privacy,
retention, and authorization rules. Finalized assessments SHOULD be immutable;
new evidence SHOULD produce a linked new assessment or correction rather than
silently rewriting history.

## Conformance and evolution

Implementations SHOULD test that:

1. execution completion and task success are separate;
2. missing evaluation remains not-evaluated or equivalent;
3. insufficient evidence remains inconclusive or equivalent;
4. partial and failed criteria are preserved;
5. aggregate outcomes identify criteria and policy versions;
6. subjective feedback remains attributable and distinct from evaluation;
7. new assessments do not silently overwrite prior results;
8. private reasoning and unauthorized sensitive data are excluded.

No evaluation framework, model judge, testing library, score scale, or learning
algorithm is normative.

## Consequences

### Positive

- Task completion claims are tied to explicit criteria and evidence.
- Routing and learning receive more reliable outcome signals.
- Partial, unknown, and inconclusive outcomes remain visible.
- Different evaluators can coexist without silently rewriting one another.

### Negative

- Systems must manage criteria versions and multiple linked assessments.
- Some tasks cannot be objectively evaluated and will remain inconclusive or rely
  on attributable human judgment.
- Aggregate success policies require explicit design rather than a universal flag.

## Non-goals

This ADR does not define universal acceptance criteria, score normalization,
confidence thresholds, model-judge prompts, feedback aggregation, or automatic
learning updates.
