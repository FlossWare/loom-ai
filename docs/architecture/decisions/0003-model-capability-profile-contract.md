# ADR-0003: Model Capability and Profile Contract

- **Status:** Proposed
- **Date:** 2026-10-16
- **Related issue:** #1018

## Context

Routing policies need a provider-neutral description of what a model/provider
implementation can do. If capabilities are inferred from vendor names, model IDs,
or ad hoc adapter fields, routing becomes brittle and implementations cannot
compare candidates consistently.

The profile must describe declared capability without conflating it with current
availability, observed quality, execution cost, or task success. Those signals
change independently and have their own contracts.

## Decision

The AI domain defines a **Model Capability Profile** as a versioned, provider-
neutral declaration of an identified model/provider implementation's supported
capabilities and operational limits.

A profile is evidence for feasibility decisions, not a guarantee that a particular
request will succeed or produce a good result. Routing policies consume the
profile together with separately defined health, economics, and evaluation signals.

## Identity and versioning

A profile MUST identify:

- the provider implementation or provider boundary;
- the model/deployment identity within that provider boundary;
- the profile identity and version;
- the source and observation time for claims that are not static or provider-
  guaranteed, where available.

Provider identity, model/deployment identity, profile version, and repository or
package version are distinct. A profile update that materially changes declared
capability semantics SHOULD use an explicit version or compatibility boundary.

A profile MUST NOT require a particular provider SDK or vendor-specific naming
scheme. Provider-specific identifiers MAY be carried as identifiers or extension
metadata, but portable capability decisions MUST be based on the shared semantics.

## Capability dimensions

A profile SHOULD declare the dimensions relevant to the implementation, including:

- **Input modalities:** text, image, audio, video, or other declared input forms.
- **Output modalities:** text, structured data, image, audio, or other declared
  output forms.
- **Tool interaction:** support for tool/function-call requests, the supported
  request/response shape, and relevant limits.
- **Context limits:** maximum supported context size and any relevant combined
  input/context constraints.
- **Token limits:** maximum input and output token counts, and whether limits are
  fixed, deployment-specific, or request-dependent.
- **Structured output:** supported constrained-output or schema-guided modes and
  their declared limitations.
- **Interaction features:** streaming, parallel tool calls, or other features
  only where they materially affect request feasibility.
- **Known restrictions:** declared input/output restrictions or other capability
  constraints that callers must respect.

Profiles MAY declare additional AI-specific capabilities. A capability claim SHOULD
be precise enough to drive a feasibility decision or explain why a request was
rejected; vague labels such as “good at coding” are not substitutes for explicit
capability semantics.

## Capability versus operational signals

The following concerns MUST remain distinct from intrinsic capability declarations:

- **Availability and health:** whether a provider/model endpoint is currently
  reachable, rate-limited, degraded, or unavailable. This belongs to the
  provider/model health contract.
- **Execution economics:** token usage, cache behavior, latency, estimated/actual
  cost, and related usage measures. This belongs to execution economics.
- **Quality and task outcome:** whether an invocation met acceptance criteria.
  This belongs to evaluation and outcome/feedback contracts.
- **Routing preference:** whether an eligible candidate is preferred for a
  particular request. This belongs to the routing policy.

A profile MAY reference external health or economics observations, but those
observations MUST retain their own identity, provenance, and time scope. A static
profile MUST NOT imply that a candidate is currently healthy, inexpensive, or
likely to succeed.

## Unknown and conditional capabilities

A profile MUST distinguish unsupported capabilities from unknown or unverified
capabilities. Missing data MUST NOT be interpreted as affirmative support.

A capability MAY be conditional on deployment, endpoint, request mode, region, or
other declared constraints. Such conditions MUST be represented explicitly enough
for a routing policy to determine whether the capability applies to the current
request.

When capability limits are estimates or observations rather than provider
guarantees, the profile SHOULD identify that distinction and provide provenance
where available.

## Use by routing and execution

Routing policies consume capability profiles to determine whether candidates can
satisfy a request's hard requirements. A policy MUST NOT select a candidate that
is known to violate a required capability or limit unless a separately authorized
fallback explicitly changes the requirement.

The profile does not choose a candidate, rank candidates, call a provider, resolve
credentials, or decide whether a task succeeded. Those responsibilities remain
with routing, invocation, authorization, and evaluation contracts respectively.

## Conformance and evolution

A conforming implementation SHOULD provide machine-readable profile data and
tests covering:

- stable profile/model/provider identity and version;
- explicit modality and tool-support claims;
- context and token limits;
- unsupported versus unknown capabilities;
- conditional capability constraints;
- separation of capability data from time-sensitive health/economics signals;
- compatibility when profile fields or capability semantics evolve.

The representation may be JSON Schema or another suitable mechanism. The schema
does not define the semantics by itself, and no Python class or provider SDK is
normative.

## Consequences

### Positive

- Routing can filter candidates by explicit feasibility rather than vendor-name
  heuristics.
- Multiple providers can express comparable capability claims.
- Health, cost, quality, and capability can evolve independently.
- Unknown or conditional capability is visible rather than guessed.
- New routing algorithms can consume the same profile contract.

### Negative

- Capability dimensions and compatibility semantics require careful definition.
- Providers may expose incomplete or non-comparable information.
- Some capability claims need provenance and observation scope.
- Adapters must normalize provider-specific features without inventing guarantees.

## Non-goals

This ADR does not:

- prescribe a provider SDK or model catalog service;
- require every provider to expose every modality or feature;
- define routing scores, exploration algorithms, or selection policy;
- define health collection, cost accounting, evaluation, or recovery behavior;
- guarantee task quality from capability declarations;
- require disclosure of private reasoning traces.

## Relationship to other decisions

This profile composes with the first-class Routing Policy contract (ADR-0002).
Provider/model health, execution economics, decision provenance, recovery, and
evaluation remain separate contracts tracked in issues #1019–#1025.
