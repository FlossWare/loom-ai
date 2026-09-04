"""Dogfood qualification for the canonical chunk contract."""

from __future__ import annotations

import pytest

from loom_ai.chunk_contract import CanonicalChunk


FIXTURE = {
    "id": "doc-1:0",
    "document_id": "doc-1",
    "sequence": 0,
    "content": "First sentence.",
    "token_count": 4,
    "start_offset": 0,
    "end_offset": 15,
    "metadata": {
        "uri": "file://exports/papers/example.pdf",
        "media_type": "application/pdf",
    },
    "provenance": {
        "source": "scraping",
        "content_hash": "sha256:example",
    },
}


def test_canonical_chunk_is_consumable_without_chunking_dependency() -> None:
    canonical = CanonicalChunk.from_resource(FIXTURE)
    chunk = canonical.to_loom_chunk()

    assert canonical.id == chunk.id
    assert canonical.document_id == chunk.document_id
    assert canonical.sequence == chunk.chunk_index
    assert canonical.content == chunk.content
    assert canonical.provenance["content_hash"] == chunk.content_hash


def test_canonical_chunk_preserves_source_contract_fields() -> None:
    canonical = CanonicalChunk.from_resource(FIXTURE)

    assert canonical.start_offset == 0
    assert canonical.end_offset == len(canonical.content)
    assert canonical.metadata["uri"].startswith("file://")
    assert canonical.metadata["media_type"] == "application/pdf"
    assert canonical.provenance["source"] == "scraping"


@pytest.mark.parametrize(
    "missing",
    ["id", "document_id", "sequence", "content", "start_offset", "end_offset"],
)
def test_canonical_chunk_rejects_missing_required_fields(missing: str) -> None:
    resource = dict(FIXTURE)
    del resource[missing]

    with pytest.raises(ValueError, match="missing field"):
        CanonicalChunk.from_resource(resource)


def test_canonical_chunk_rejects_inconsistent_offsets() -> None:
    resource = dict(FIXTURE)
    resource["end_offset"] = resource["start_offset"] + 1

    with pytest.raises(ValueError, match="offsets do not match"):
        CanonicalChunk.from_resource(resource)
