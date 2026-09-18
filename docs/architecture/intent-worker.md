# Intent, Worker, and Arbiter

This document defines the language-neutral AI-domain semantics. It is normative for meaning, not for a particular programming-language API.

The Python types in `loom-ai-python` are one realization of these concepts. A future implementation in Java, Erlang, or another language must preserve the semantics without copying Python method signatures.

## Intent

An **Intent** describes a desired outcome and the information required to evaluate that outcome.

An Intent MAY contain:

- a goal or desired outcome;
- requirements;
- constraints;
- acceptance criteria;
- provenance or other caller-supplied context.

An Intent MUST NOT acquire a language-specific execution plan merely by being represented as an Intent. Model selection, provider configuration, credentials, and implementation-specific routing are outside the Intent contract.

A language-neutral conceptual representation is:

```text
Intent {
  goal
  requirements[]
  constraints[]
  acceptance[]
  provenance
}
```

The wire representation may be JSON, another serialization, or an adapter-specific form. The representation does not change the semantic contract.

## Worker

A **Worker** is an executable implementation that accepts execution context and produces a Worker Result.

Conceptually:

```text
Worker
  execute(Context)
      |
      v
WorkerResult
```

The operation is semantic, not a Python signature. An implementation may expose it through an in-process API, HTTP, messaging, or another Loom binding.

A Worker Result contains, at minimum:

- an implementation/worker identity;
- execution status;
- an output value;
- evidence describing material execution facts;
- an error or failure description when unsuccessful.

Execution context MUST make relevant execution state explicit rather than relying on hidden global state.

## Arbiter

An **Arbiter** is a Worker that composes other Workers.

It evaluates Worker Results and may decide to:

- complete;
- continue with another Worker;
- retry an eligible operation;
- replan by selecting another Worker or composition.

The Arbiter therefore remains a Composite of the Worker contract. It does not establish a second orchestration model.

Conceptually:

```text
Arbiter
  |
  +-- Worker
  +-- Worker
  +-- Worker
       |
       v
   Result + Evidence
       |
       v
   Evaluation
       |
       +--> Complete
       +--> Continue
       +--> Retry
       +--> Replan
```

Nested Arbiters are valid because an Arbiter satisfies the Worker contract.

## Result and evidence

Results communicate externally meaningful execution outcomes. Evidence communicates provenance or other facts needed to understand how the result was produced or verified.

These are not private chain-of-thought. Implementations MUST NOT require disclosure of private reasoning traces to satisfy this contract.

## Model-provider boundary

AI-domain model invocation is represented by a provider-neutral contract. A Model Request describes the requested generation inputs and associated metadata. A Model Response describes generated output, provider/model identity, completion status, and provenance.

The contract does not prescribe a provider SDK, credential mechanism, routing strategy, caching mechanism, budget implementation, or optimization algorithm.

## Conformance

A conforming implementation MUST preserve the semantics defined here while remaining free to choose:

- programming language;
- in-process or remote binding;
- serialization format;
- internal data structures;
- transport;
- runtime architecture.

Python-specific types and method signatures in `loom-ai-python` are implementation details. They are evidence of one conforming realization, not the definition of the AI-domain contract.

Generic Loom semantics remain authoritative in `FlossWare/loom`. AI-domain semantics may extend Loom but must not redefine or contradict them.
