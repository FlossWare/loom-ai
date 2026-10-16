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

## Sequential arbitration pipelines

A **sequential arbitration pipeline** is a configured sequence of one or more arbitration stages. Each stage runs a set of independent Workers against the same current task and relevant execution context, then asks its Arbiter to adjudicate the collected results.

Conceptually:

```text
Intent + execution context
          |
          v
  Stage 1: Workers
          |
          v
  Stage 1: Arbiter
          |
          +---- selected result + preserved context ----+
                                                        |
                                                        v
                                               Stage 2: Workers
                                                        |
                                                        v
                                               Stage 2: Arbiter
                                                        |
                                                        v
                                                   Final result
```

The following semantics are normative:

1. **Shared stage input.** Workers within a stage MUST receive the same logical task and stage-input context. A binding MAY provide immutable snapshots or equivalent representations, but one Worker’s private in-memory mutations MUST NOT silently change another Worker’s input.
2. **Independent results.** The stage MUST collect each dispatched Worker’s result and relevant evidence. A Worker failure is represented as a result with its status and failure information; it MUST NOT be silently rewritten as a successful result.
3. **Adjudication.** The Arbiter MUST evaluate the available results and evidence and select or produce a justified stage result. It is not merely a prose summarizer. The contract does not prescribe majority voting, a particular scoring algorithm, or a particular internal reasoning method.
4. **Preserved handoff.** If another stage is configured, its input MUST include the selected prior result and enough underlying context for independent re-evaluation. Depending on the task, that includes the original Intent, the artifact being reviewed or changed, relevant workspace/repository state, files or diffs, evidence, Worker findings, material disagreements or rejected alternatives, and stage/execution metadata.
5. **No prose-only handoff.** A stage MUST NOT reduce the handoff to only the previous Arbiter’s textual synthesis when the underlying result, evidence, or execution state is relevant to evaluating it.
6. **Configured termination.** The configured pipeline topology determines the number of stages. If another stage is configured and execution has not been cancelled or terminated by an explicit execution failure policy, the pipeline MUST proceed to that stage. Confidence scores or implicit confidence thresholds MUST NOT silently shorten the configured pipeline.
7. **Final result.** The final configured Arbiter produces the pipeline result. The result MUST retain sufficient provenance to identify the stage outcome and the evidence used to support it.
8. **Single-stage compatibility.** A one-stage pipeline is valid and uses the same semantics as any other stage; multiple stages do not define a separate orchestration architecture.

### Task modes and pipeline depth

Task mode describes the work being requested; pipeline depth describes how many sequential arbitration stages are configured. They are separate dimensions.

- `review`: one arbitration stage performing review.
- `multi-review`: multiple sequential arbitration stages performing review.
- `solve`: one arbitration stage performing a solution task.
- `multi-solve`: multiple sequential arbitration stages performing a solution task.

An implementation MAY support additional depth notation or configuration forms, but MUST preserve this separation. A pipeline MUST NOT require a fixed discovery → verifier → synthesizer topology. Each stage’s worker set and adjudication policy are configuration, not universal protocol primitives.

These semantics describe observable behavior only. They do not prescribe a programming-language API, agent vendor, provider, orchestration framework, or private reasoning format.

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
