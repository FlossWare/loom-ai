# Canonical chunk consumer boundary

Loom consumes the document-to-chunk contract structurally. The standalone `chunking` package is not a Loom dependency.

A canonical chunk provides:

- `id` and `document_id`
- zero-based `sequence`
- `content` and `token_count`
- `start_offset` and `end_offset`
- `metadata` containing source information such as URI and media type
- `provenance` containing acquisition/pipeline evidence such as content hash

`loom_ai.chunk_contract.CanonicalChunk.from_resource()` validates these fields and `to_loom_chunk()` adapts them to Loom's internal `Chunk` model. This keeps the producer and consumer independently deployable while making the interoperability boundary executable and testable.
