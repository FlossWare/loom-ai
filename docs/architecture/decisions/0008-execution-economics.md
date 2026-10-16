# ADR-0008: Execution Economics

- **Status:** Proposed
- **Date:** 2026-10-16
- **Related issue:** #1023

## Context

Model and Worker execution has measurable usage and operational cost: input/output
tokens, provider-reported usage, latency, cache effects, resource consumption,
and monetary charges. These facts are often exposed through provider-specific
fields or hidden inside routing logic, making cost comparison, budgeting, and
learning difficult across implementations.

Loom needs a provider-neutral economics record that preserves the source and
meaning of measurements without pretending that different providers' usage or
pricing models are automatically equivalent.

## Decision

**Execution Economics** is a structured record of resource usage and cost
associated with an execution, attempt, or operation. It records measurements,
estimates, and their provenance; it does not decide whether a task succeeded,
select a model, or enforce a budget.

Economics records SHOULD be linkable to an ExecutionTrace, Execution Result,
Decision Provenance record, Context Artifact, provider/model identity, and the
relevant policy or pricing version.

## Measurement dimensions

Where applicable, an economics record SHOULD distinguish:

- **Usage:** input/output tokens, other provider-reported units, tool calls, or
  other metered resources.
- **Latency:** queue/wait time, time to first output, execution duration, and
  end-to-end duration when those measurements are available and meaningful.
- **Cache effects:** cache lookup/hit/miss, cached input/output usage, and the
  applicable cache identity or policy reference where available.
- **Cost:** amount, currency or unit, whether the value is estimated or actual,
  and the pricing source/version used.
- **Resource consumption:** other metered resources such as compute time or
  storage where relevant to the execution.
- **Attribution:** execution/attempt identity, provider/model identity, time
  interval, and source of the measurement.

A record MAY contain only a subset of these dimensions. Missing or unavailable
measurements MUST NOT be represented as zero. An estimate MUST be distinguished
from a provider-confirmed usage or charge.

## Usage and cost provenance

Every usage/cost measurement SHOULD identify its source, such as provider-reported
usage, local tokenizer estimate, metering service, or derived calculation.

Token measurements SHOULD identify the tokenizer/model/serialization scope when
those differences affect comparability. A token estimate derived from a
Context Artifact MUST NOT be presented as actual provider-billed usage.

Cost calculations SHOULD reference the pricing model/version and the inputs used
to derive the amount. If pricing is unavailable or uncertain, the record SHOULD
preserve that uncertainty rather than fabricate precision.

Different providers may count usage, cache hits, or billable units differently.
Implementations MUST retain provider/source provenance and MUST NOT claim
cross-provider equivalence without a declared normalization rule.

## Budget boundary

Budgets and limits are policy inputs, not economics measurements.

- Execution Economics records observed or estimated consumption and remaining
  budget information where available.
- Routing Policy and Recovery Policy may use economics estimates to select or
  recover from an execution.
- The applicable budget/authorization policy determines whether an operation is
  permitted.
- A measurement or cost estimate MUST NOT itself authorize a budget increase or
  bypass a hard limit.

Where a budget is checked, the decision SHOULD be linked through Decision
Provenance to the economics snapshot and policy version used.

## Cache accounting

Cache behavior MUST be reported separately from ordinary input/output usage when
it materially changes cost or latency. A cache hit is an operational fact, not a
guarantee that the cached content is semantically appropriate.

Cache identity and security scope are defined by the Context Artifact and
applicable authorization contracts. Execution Economics records cache outcomes
and their measured effects; it does not define cache-key semantics.

## Lifecycle and aggregation

Economics records SHOULD be attributable to an individual execution or attempt
before being aggregated. Retries, resumed executions, and fallback providers
MUST NOT be silently merged into one measurement if doing so hides duplicated
usage or makes attribution ambiguous.

Aggregated reports SHOULD preserve enough information to distinguish per-attempt
measurements from totals and estimates from actual values. Corrections SHOULD
retain provenance to the original record.

Retention and access MUST respect applicable privacy, tenant, and provider-data
constraints. Economics records MUST NOT require private chain-of-thought or
unnecessary prompt content.

## Relationship to other contracts

Execution Economics composes with:

- **Routing Policy:** uses cost/latency estimates as selection signals.
- **Model Capability Profile:** provides declared limits, not actual usage.
- **Provider/Model Health:** reports availability and operational health, not cost.
- **Context Artifact:** provides estimated context size and cache identity inputs.
- **Recovery Policy:** considers retry budgets and expected recovery cost.
- **Execution Outcome and Feedback:** may evaluate cost or latency as part of an
  outcome, but economics does not define task success.
- **Decision Provenance and ExecutionTrace:** record which economics snapshot was
  used and what happened during execution.

## Conformance and evolution

Implementations SHOULD test that:

1. estimates are distinguished from actual measurements;
2. missing values are not treated as zero;
3. usage/cost measurements have source and scope provenance;
4. pricing model versions are retained for derived cost;
5. retries and fallbacks remain attributable to individual attempts;
6. cache effects are distinguishable where relevant;
7. budget enforcement remains a policy decision;
8. private reasoning and unnecessary sensitive inputs are excluded.

The representation may be JSON or another suitable format. No provider billing
API, tokenizer, cache backend, monitoring vendor, or cost formula is normative.

## Consequences

### Positive

- Usage and cost can be compared without embedding provider SDKs in routing.
- Budget decisions can be audited against the measurements and policy versions
  used at the time.
- Retries and fallback behavior can be evaluated without hiding duplicated cost.
- Cache effects and estimation uncertainty become explicit.

### Negative

- Provider usage fields and pricing models may not be directly comparable.
- Accurate cost requires source, version, and unit provenance.
- Aggregation must preserve attempt-level attribution to avoid misleading totals.

## Non-goals

This ADR does not define a universal pricing table, budget enforcement algorithm,
cache implementation, provider billing adapter, or task-success metric.
