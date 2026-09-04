# Canonical chunk dogfood

The qualification path verifies that Loom can consume a canonical chunk emitted by the standalone chunking stage without importing the producer package.

Acceptance criteria:

1. Canonical required fields are validated.
2. Source offsets are internally consistent with content.
3. URI and media type survive the consumer boundary.
4. Provenance content hash maps to Loom's internal chunk model.
5. The test fixture is JSON and represents an acquired PDF resource.
6. Loom has no runtime dependency on the standalone chunking package.
