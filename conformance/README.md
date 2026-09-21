# AI-domain conformance fixtures

The fixtures in this directory are language-neutral examples of the semantics defined by `loom-ai`.

They are normative examples, not Python serialization requirements. A language implementation may use a different in-memory representation or transport while preserving the stated semantics.

The authoritative fixture lives in `loom-ai`. Language implementations should consume or reproduce the fixture semantics through an adapter-specific conformance test.

The initial fixture is intentionally small:

- represent an Intent without a language-specific execution plan;
- produce a Worker Result with status, output, and evidence;
- make successful completion externally observable without requiring private reasoning traces.

Future implementations such as `loom-ai-java` should be able to validate the same semantic cases without depending on Python types.


## Arbiter terminal semantics

An Arbiter must not report successful completion when the most recent executed WorkerResult is failed and the evaluation schedules no subsequent work.

In particular:

- REPLAN or CONTINUE with an empty worker set after a failed WorkerResult is terminal failure.
- A later WorkerResult may establish recovery. If subsequent work completes successfully, the overall Arbiter result may be successful.
- The terminal result must preserve evidence and provenance for the failed attempt and the terminal outcome.
- This semantic applies independently of language, transport, or in-memory representation.

The rule prevents an exhausted orchestration queue from converting an unrecovered worker failure into successful completion.


## Durable execution state

A Loom implementation that supports resumable execution must associate durable execution state with a stable execution identity.

The contract distinguishes four concerns:

- **Execution identity** identifies the unit of work that may be observed or continued. An `Intent.intent_id` may provide identity for an intent, but intent identity alone does not make execution state durable.
- **Durable state** contains the state required to reconstruct the execution context needed for continued work. It is not required to be a transcript.
- **Evidence and provenance** preserve externally observable facts about work that has already occurred, including the relationship between prior attempts and subsequent work. Private model reasoning is not part of this contract.
- **Transport** carries requests to observe or continue an execution. The durable-state contract is independent of HTTP or any other transport.

### Resume semantics

A continuation must reference the existing execution identity rather than resubmit the original conversation or transcript.

When resuming, the implementation reconstructs the execution context from durable state and preserved evidence/provenance. The consumer must not need to replay the original transcript merely to recover execution state.

A continuation is new work against an existing execution state. It must not silently create an unrelated execution that happens to reuse the same intent data.

### Process interruption and terminal state

A process interruption before successful terminal completion must not be represented as successful completion.

An implementation must distinguish an execution that completed successfully from one that stopped before terminal completion. If durable state is sufficient to continue, a later operation may resume the incomplete execution. If it is not sufficient, the implementation must expose that recovery is unavailable rather than manufacture a successful result.

Once an execution is terminal, its recorded outcome and evidence remain available for observation. A later continuation must preserve the provenance of the prior terminal outcome and must not rewrite history.

### Persistence boundary

Persistence is a separate capability from Worker and Arbiter execution.

Workers and Arbiters produce execution results, state, evidence, and provenance according to their contracts. A persistence implementation is responsible for durably storing and retrieving the information required by the resume semantics. Neither Worker nor Arbiter semantics depend on a particular database, file format, serialization library, or storage service.

The contract therefore does not prescribe PostgreSQL, Redis, OrientDB, or any other persistence technology.

### Evolution and integrity

Durable execution state must be identifiable as belonging to the execution it represents and must be possible to distinguish from unrelated or superseded state.

An implementation should provide an explicit representation/version for its durable state so that incompatible state cannot be silently interpreted as current state. Corrupt, missing, incomplete, or superseded state must be surfaced as such rather than treated as successful completion.

The semantic boundary is intentionally small: stable execution identity, durable resumable state, preserved evidence/provenance, explicit interruption/terminal semantics, and independent persistence. Concrete APIs, storage schemas, and transport operations belong to language or implementation-specific layers.

