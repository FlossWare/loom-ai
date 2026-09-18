# AI-domain conformance fixtures

The fixtures in this directory are language-neutral examples of the semantics defined by `loom-ai`.

They are normative examples, not Python serialization requirements. A language implementation may use a different in-memory representation or transport while preserving the stated semantics.

The authoritative fixture lives in `loom-ai`. Language implementations should consume or reproduce the fixture semantics through an adapter-specific conformance test.

The initial fixture is intentionally small:

- represent an Intent without a language-specific execution plan;
- produce a Worker Result with status, output, and evidence;
- make successful completion externally observable without requiring private reasoning traces.

Future implementations such as `loom-ai-java` should be able to validate the same semantic cases without depending on Python types.
