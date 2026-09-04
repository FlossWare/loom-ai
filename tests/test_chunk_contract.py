"""Dogfood qualification for the canonical chunk contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loom_ai.chunk_contract import CanonicalChunk


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "canonical_chunk.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_canonical_chunk_is_consumable_without_chunking_dependency() -> None:
    canonical = CanonicalChunk.from_resource(load_fixture())
    chunk = canonical.to_loom_chunk()

    assert canonical.id == chunk.id
    assert canonical.document_id == chunk.document_id
    assert canonical.sequence == chunk.chunk_index
    assert canonical.content == chunk.content
    assert canonical.provenance["content_hash"] == chunk.content_hash


def test_canonical_chunk_preserves_source_contract_fields() -> None:
    canonical = CanonicalChunk.from_resource(load_fixture())

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
    resource = load_fixture()
    del resource[missing]

    with pytest.raises(ValueError, match="missing field"):
        CanonicalChunk.from_resource(resource)


def test_canonical_chunk_rejects_inconsistent_offsets() -> None:
    resource = load_fixture()
    resource["end_offset"] = resource["start_offset"] + 1

    with pytest.raises(ValueError, match="offsets do not match"):
        CanonicalChunk.from_resource(resource)
