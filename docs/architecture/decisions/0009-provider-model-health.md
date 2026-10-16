# ADR-0009: Provider and Model Health as a Routing Signal

- **Status:** Proposed
- **Date:** 2026-10-16
- **Related issue:** #1024

## Context

A model/provider can advertise the required capabilities and still be unavailable,
rate-limited, degraded, or too slow to serve a request at a particular time.
Embedding health checks and transient failure handling inside a routing algorithm
makes the signal difficult to compare, expire, attribute, and reuse across
implementations.

Loom needs a provider-neutral health signal that routing and recovery policies
can consume without making health collection part of the capability profile or
the routing-policy contract.

## Decision

**Provider/Model Health** is a time-scoped observation of operational availability
and service condition for an identified provider, model/deployment, or endpoint.

Health is a signal, not a guarantee. It is separate from static capability,
execution economics, task outcome, and recovery action. The contract does not
prescribe an active-probe system, monitoring vendor, circuit breaker, or routing
algorithm.

## Identity and scope

A health observation SHOULD identify:

- provider and model/deployment/endpoint identities;
- region or service scope where relevant;
- observation ID and timestamp;
- observation source and method;
- health state and the measurements supporting it;
- freshness/expiry information or a declared maximum age;
- confidence or limitations where meaningful.

A health state MUST be associated with the scope and time interval it describes.
An observation about one endpoint, region, or deployment MUST NOT automatically
be treated as the health of every model or provider offering.

## Health state and measurements

A health record SHOULD distinguish at least:

- **available:** current evidence indicates the endpoint is accepting requests;
- **degraded:** requests may succeed but observed service is impaired;
- **unavailable:** current evidence indicates the endpoint cannot serve requests;
- **unknown:** there is no sufficiently fresh or reliable observation.

Unknown MUST NOT be interpreted as healthy. Implementations MAY expose more
detailed states, but they SHOULD preserve a portable mapping to these categories.

Supporting measurements MAY include availability, latency, timeout/error rate,
rate-limit/capacity responses, queue delay, or other operational observations.
The record SHOULD distinguish raw observations from derived health state and
identify the method or policy used to derive that state.

## Sources and freshness

Health may be derived from:

- passive observations of real execution attempts;
- provider-reported status or rate-limit signals;
- active health probes;
- monitoring or service telemetry.

The source and observation time MUST be preserved. Active probes SHOULD be
bounded and MUST NOT create unbounded traffic or materially worsen the service
condition they are measuring.

Health is time-sensitive. A routing or recovery policy SHOULD consider the age
and scope of an observation and SHOULD treat stale data as unknown or otherwise
apply an explicit freshness rule. A past success MUST NOT be represented as a
permanent health guarantee.

## Use by routing and recovery

Routing Policy MAY use health as an input when ranking or filtering candidates.
The health contract does not prescribe thresholds, weights, fallback choices, or
a circuit-breaker algorithm.

Recovery Policy MAY use health observations to decide whether to retry, wait,
substitute, resume, or terminate. A health signal does not itself authorize a
retry or relaxation of hard constraints.

Health MUST NOT override capability feasibility, authorization, safety rules, or
explicit budget limits. An unavailable candidate can remain capability-compatible;
a healthy candidate can still be incapable of satisfying the request.

## Separation from adjacent contracts

- **Model Capability Profile** describes declared supported behavior and limits.
- **Execution Economics** records usage, cost, latency, and cache effects for an
  execution or attempt. Health may consume latency/error observations but does not
  own the economics record.
- **Routing Policy** selects an eligible candidate using health and other signals.
- **Recovery Policy** chooses an action after a failure or degradation.
- **Execution Outcome and Feedback** assesses task success and downstream value.

These records SHOULD reference one another through stable identities and
timestamps rather than duplicate or collapse their semantics.

## Provenance and privacy

Health observations SHOULD retain source, scope, time, and derivation provenance.
Derived health states SHOULD be explainable through structured measurements or
rules rather than private reasoning traces.

Records MUST NOT contain credentials or unnecessary user prompt/content data.
Access to provider telemetry and per-tenant observations MUST respect applicable
authorization and privacy boundaries.

## Conformance and evolution

Implementations SHOULD test that:

1. health observations identify provider/model scope and observation time;
2. unknown and stale health are not silently treated as healthy;
3. health state can be traced to source measurements or a declared derivation;
4. active probes are bounded;
5. routing uses health only within the applicable scope and freshness rule;
6. health does not override capability, safety, authorization, or budget constraints;
7. health records remain distinct from task outcomes and economics.

The representation may be JSON or another suitable format. No monitoring service,
probe protocol, provider SDK, or circuit-breaker implementation is normative.

## Consequences

### Positive

- Routing and recovery can consume comparable, time-scoped health signals.
- Stale or unknown information is distinguishable from healthy status.
- Health collection can evolve independently from routing algorithms.
- Operational failures gain attribution and measurement provenance.

### Negative

- Health requires freshness, scope, and source semantics.
- Active probes may consume resources and need careful bounds.
- Different providers expose different telemetry, limiting direct comparability.

## Non-goals

This ADR does not define universal health thresholds, active-probe schedules,
circuit-breaker state machines, retry counts, or provider-specific status APIs.
