# ADR-0005: Execution Outcome and Feedback Contract

- **Status:** Proposed
- **Date:** 2026-10-16
- **Related issue:** #1019

## Context

Execution systems need to report what happened, while evaluation and learning
systems need to determine whether the requested outcome was achieved and what
feedback should influence future behavior. Treating these as one status creates
a dangerous ambiguity: a process can complete successfully while the task is
incorrect, incomplete, rejected, or never independently verified.

Loom needs a provider-neutral way to connect execution evidence with outcome
assessments and downstream feedback without making an evaluation algorithm,
learning strategy, or feedback source part of the execution contract.

## Decision

Execution results, outcome assessments, and feedback signals are distinct but
composable concepts.

1. **Execution Result** records the observable result of an invocation: what ran,
   its runtime status, output, failure/cancellation information, and evidence.
2. **Outcome Assessment** records an evaluation of that result against declared
   task requirements or acceptance criteria.
3. **Feedback Signal** records a human or system signal about an execution,
   outcome, decision, or candidate and preserves its source and attribution.

These records MAY reference one another by stable identifiers. They MUST NOT be
collapsed into one boolean success flag or one unqualified reward value.

## Execution Result

An Execution Result reports execution facts, not an unconditional claim that the
requested task was correct.

It SHOULD identify the execution and Intent, execution status, produced output or
artifact references, failure/cancellation information where applicable, relevant
evidence, and the implementation/worker that produced it.

Execution completion, process exit status, transport success, and successful
verification are different facts and MUST remain distinguishable where applicable.

## Outcome Assessment

An Outcome Assessment evaluates an Execution Result against explicit requirements,
acceptance criteria, evaluation criteria, or another declared objective.

It SHOULD identify:

- the execution/result being assessed;
- the evaluator or evaluation mechanism;
- the criteria and their version;
- the assessment status and relevant measurements;
- the evidence supporting the assessment;
- the timestamp and provenance of the assessment;
- uncertainty or confidence information where meaningful.

The status vocabulary and detailed distinction between objective evaluation,
subjective/user feedback, partial success, and downstream acceptance are defined
with the Evaluation and Success Semantics work tracked in issue #1025. This ADR
does not impose a universal score, reward scale, confidence threshold, or definition
of success for every workload.

An Outcome Assessment MUST NOT be inferred solely from a successful HTTP response,
worker process exit, or model response. If the requested criteria have not been
evaluated, the outcome MUST remain explicitly unevaluated or unknown rather than
being silently promoted to success.

## Feedback Signal

A Feedback Signal records an observation or judgment that may be useful for
evaluation, attribution, or future learning. It SHOULD identify:

- the signal and its stable identity;
- the target it refers to, such as an execution, outcome assessment, decision,
  policy version, model/provider candidate, or capability;
- the signal source, such as a user, verifier, automated evaluator, or downstream
  consumer;
- the signal type and value or payload;
- the time it was produced and, where different, the time of the event it concerns;
- provenance and references to supporting evidence;
- confidence, scope, or limitations where meaningful.

Feedback can be delayed, incomplete, noisy, subjective, or contradictory. A
feedback signal MUST retain its attribution and MUST NOT silently overwrite the
original execution result or outcome assessment. Implementations SHOULD preserve
multiple signals when their differences are meaningful.

## Relationship to learning and routing

Outcome assessments and feedback signals MAY be consumed by learning, evaluation,
model comparison, routing-policy improvement, or recovery-policy analysis.

Their existence MUST NOT itself authorize an automatic policy change. Any learned
artifact or policy update remains subject to its own identity, versioning,
evaluation, provenance, and applicable safety/authorization controls.

The contract does not prescribe Thompson sampling, contextual bandits, reward
attribution, neural learning, or any other algorithm. Those mechanisms consume
the shared signals as implementation strategies.

Execution economics and decision provenance remain separate records. A cost or
latency measurement may be evidence for an outcome assessment, but it is not
itself a judgment that the task succeeded.

## Provenance, privacy, and integrity

Outcome and feedback records SHOULD reference the relevant ExecutionTrace,
Decision Provenance, artifacts, and criteria versions rather than copying large
records unnecessarily.

They MUST NOT require or expose model private chain-of-thought. Sensitive inputs,
user feedback, and evaluation artifacts MUST follow applicable privacy, retention,
and authorization rules.

A finalized execution result SHOULD be immutable. Outcome assessments and feedback
may be added later as separate linked records. Corrections or superseding
assessments SHOULD retain links to prior records so downstream consumers can
understand the history.

## Conformance and evolution

Implementations SHOULD test that:

1. execution status and task outcome are separately represented;
2. an unevaluated result is not silently reported as verified success;
3. assessments identify their criteria/evaluator and supporting evidence;
4. feedback identifies its source and target;
5. conflicting or delayed feedback does not overwrite earlier records;
6. records can be correlated with execution and decision provenance;
7. sensitive data and private reasoning are excluded.

The wire representation may be JSON or another suitable format. No provider,
database, evaluation framework, learning algorithm, or Python API is normative.

## Consequences

### Positive

- Runtime completion is no longer confused with task correctness.
- Evaluators can assess work without changing the execution contract.
- Human and system feedback can be attributed and reused without losing provenance.
- Learning and routing can consume common signals without owning execution.
- Later assessments can be attached without rewriting execution history.

### Negative

- Implementations must manage linked records and their lifecycle.
- Criteria and evaluator versions become important for interpreting old outcomes.
- Noisy or contradictory feedback requires careful attribution and handling.

## Non-goals

This ADR does not define universal success criteria, reward scales, evaluation
algorithms, feedback aggregation rules, automatic learning updates, or provider-
specific telemetry. Those concerns remain separate contracts and implementations.

## Relationship to other decisions

This contract complements the ExecutionTrace and Decision Provenance ADRs, the
portable learning artifact boundary, and the Evaluation and Success Semantics
work tracked in issue #1025.
