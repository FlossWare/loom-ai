# ADR-0006: Context Lifecycle and Context Artifact

- **Status:** Proposed
- **Date:** 2026-10-16
- **Related issue:** #1021

## Context

AI execution often assembles context from task inputs, prior results, retrieved
artifacts, tools, instructions, and other sources. Treating context as an opaque
string passed directly to a provider loses source attribution, transformation
history, token accounting, cache identity, and lifecycle information.

Context must be inspectable enough to support feasibility checks, provenance,
reproducibility, safe caching, and evaluation without requiring every consumer to
persist raw prompts or private reasoning traces.

## Decision

Context is modeled as a **Context Artifact** with stable identity, source
references, assembly/transformation provenance, and lifecycle metadata. The
artifact represents the logical context used for an operation; a provider-specific
serialized prompt or request is a realization of that context, not its definition.

A Context Artifact MAY contain inline content, references to other artifacts, or
a combination. Implementations are not required to persist all content
permanently, and the contract does not prescribe a particular storage system.

## Artifact identity and content

A Context Artifact SHOULD identify:

- context artifact ID and version;
- the execution, Intent, or operation that uses it;
- source items or stable references to them;
- the assembly policy and version;
- transformations applied and their versions;
- token/size estimates and the tokenizer or measurement method where available;
- applicable privacy, authorization, and retention scope;
- creation time and relevant lifecycle/expiration information.

A source item MAY be a user-supplied instruction, task input, prior Worker Result,
retrieved artifact, tool result, evidence record, or other explicitly declared
input. Each item SHOULD retain its origin and relevant version/reference.

The context artifact describes what information was made available to an operation.
It MUST NOT imply that the model attended to, understood, or used every item.

## Assembly and transformation provenance

Context assembly and transformation SHOULD be explicit operations whose outputs
can be associated with their inputs and policy versions.

Transformations may include ordering, selection, redaction, truncation,
compression, summarization, format conversion, and other declared changes.
A transformation SHOULD record:

- its identity/type and version;
- input artifact/item references;
- output artifact identity;
- relevant limits or configuration;
- measurable changes such as size/token counts where available;
- any source information intentionally omitted or summarized.

A transformed context MUST NOT silently claim to contain the same full information
as its source when truncation, filtering, or compression removed material. When
the original source is retained, provenance SHOULD permit a consumer to inspect
which source items contributed to the derived context.

The contract does not require a universal context assembly algorithm or a specific
summarization technique.

## Token and size accounting

A Context Artifact SHOULD expose size/token estimates relevant to feasibility and
budget decisions. When token counts depend on a tokenizer, model profile, or
serialization, the record SHOULD identify the measurement method and its scope.

Token estimates MUST NOT be represented as exact provider usage unless confirmed
by the provider's usage record. Actual input/output usage and cost remain part of
Execution Economics; context artifacts record the estimates and source facts
needed to understand request construction.

Context limits declared by a Model Capability Profile constrain feasible context
construction. Routing and assembly MUST NOT silently assume that a candidate can
accept context larger than its declared limits.

## Cache identity and reuse

A context cache identity SHOULD account for the source item identities/versions,
assembly policy version, transformation chain, relevant serialization or
tokenization version, and applicable authorization/privacy scope.

Two contexts MUST NOT be treated as interchangeable merely because their final
text appears similar if their provenance, security scope, or declared semantics
differ materially.

Cache reuse MUST respect authorization and data-isolation boundaries. Cache keys
and metadata MUST NOT expose raw secrets or sensitive prompt content when stable
references or protected digests are sufficient.

Caching is an implementation capability. This ADR defines the provenance needed
to reason about context reuse; it does not require a cache or prescribe a cache
backend.

## Lifecycle and retention

A Context Artifact MAY pass through lifecycle states such as assembled,
transformed, selected for an operation, consumed, superseded, expired, or deleted.
Implementations SHOULD document the lifecycle states they support and distinguish
an artifact's logical status from the availability of its stored content.

Retention SHOULD be driven by purpose, privacy, security, reproducibility, and
operational requirements. Implementations MAY retain only metadata and references
after content expires, provided they do not imply that unavailable content can be
replayed or inspected.

Expired or deleted context MUST NOT be silently reused as if the original content
were still available. References to expired artifacts SHOULD expose their
availability state and any applicable reason.

## Privacy and reasoning boundary

Context may contain private user data, source code, retrieved documents, secrets,
or other sensitive material. Context artifact access and retention MUST respect
the source's authorization and privacy constraints.

The contract does not require storing private model chain-of-thought. Model
private reasoning is not a required context artifact, and it MUST NOT be captured
as context provenance. Concise structured decisions and externally meaningful
evidence remain governed by the execution-tracing and decision-provenance
contracts.

## Relationship to other contracts

Context Artifacts compose with:

- **Intent and Worker Context:** describe the task and execution-time context.
- **Model Capability Profile:** supplies applicable context and token limits.
- **Routing Policy:** uses context size and requirements when filtering candidates.
- **Execution Economics:** records actual usage, cost, latency, and cache outcomes.
- **Decision Provenance:** records relevant context/profile references used by a
  routing or recovery decision.
- **ExecutionTrace:** records assembly, transformation, consumption, and failure
  events where those events are part of execution evidence.
- **Learning Artifacts:** may reference approved context-derived artifacts, subject
  to privacy and sharing constraints.

These contracts SHOULD use stable references rather than duplicate one another's
full payloads.

## Conformance and evolution

Implementations SHOULD test that:

1. context artifacts have stable identity and provenance;
2. source items and transformation history can be correlated;
3. token/size estimates identify their measurement scope where available;
4. truncation/compression does not silently erase provenance;
5. cache identity includes relevant versions and security scope;
6. expired/deleted content is not represented as replayable;
7. sensitive context and private reasoning are not exposed through metadata.

No programming language, provider SDK, tokenizer, storage backend, prompt format,
or cache implementation is normative.

## Consequences

### Positive

- Context assembly becomes inspectable and attributable.
- Routing can use context size and limits before selecting a candidate.
- Cache reuse can be safer and more reproducible.
- Context compression and transformation can be evaluated without losing source
  provenance.
- Retention and privacy decisions can be made explicitly.

### Negative

- Context provenance adds metadata and lifecycle responsibilities.
- Token counts and transformations may be approximate or provider-dependent.
- Some source content cannot be retained or shared because of privacy constraints.

## Non-goals

This ADR does not prescribe a universal prompt template, context-window strategy,
summarization model, retrieval algorithm, caching backend, or retention duration.
It does not require persistence of raw prompts or private reasoning traces.
