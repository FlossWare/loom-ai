"""Canonical document-to-chunk interoperability boundary.

This module deliberately has no dependency on the standalone ``chunking``
package. Loom consumes the published contract structurally, allowing the
producer and consumer to evolve independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from loom_ai.models import Chunk


_REQUIRED = (
    "id",
    "document_id",
    "sequence",
    "content",
    "token_count",
    "start_offset",
    "end_offset",
    "metadata",
    "provenance",
)


@dataclass(frozen=True)
class CanonicalChunk:
    """The stable chunk contract emitted by the FlossWare chunking stage."""

    id: str
    document_id: str
    sequence: int
    content: str
    token_count: int
    start_offset: int
    end_offset: int
    metadata: Mapping[str, Any]
    provenance: Mapping[str, Any]

    @classmethod
    def from_resource(cls, resource: Mapping[str, Any] | Any) -> "CanonicalChunk":
        """Validate and normalize a canonical chunk mapping/object."""
        values: dict[str, Any] = {}
        for name in _REQUIRED:
            if isinstance(resource, Mapping):
                if name not in resource:
                    raise ValueError(f"canonical chunk missing field: {name}")
                values[name] = resource[name]
            else:
                if not hasattr(resource, name):
                    raise ValueError(f"canonical chunk missing field: {name}")
                values[name] = getattr(resource, name)

        if not isinstance(values["content"], str):
            raise TypeError("canonical chunk content must be str")
        if values["start_offset"] < 0 or values["end_offset"] < values["start_offset"]:
            raise ValueError("canonical chunk offsets are invalid")
        if values["sequence"] < 0:
            raise ValueError("canonical chunk sequence must be non-negative")
        if values["token_count"] < 0:
            raise ValueError("canonical chunk token_count must be non-negative")
        if values["end_offset"] - values["start_offset"] != len(values["content"]):
            raise ValueError("canonical chunk offsets do not match content length")

        return cls(
            id=str(values["id"]),
            document_id=str(values["document_id"]),
            sequence=int(values["sequence"]),
            content=values["content"],
            token_count=int(values["token_count"]),
            start_offset=int(values["start_offset"]),
            end_offset=int(values["end_offset"]),
            metadata=dict(values["metadata"]),
            provenance=dict(values["provenance"]),
        )

    def to_loom_chunk(self) -> Chunk:
        """Adapt the canonical contract to Loom's internal chunk model."""
        return Chunk(
            id=self.id,
            document_id=self.document_id,
            content=self.content,
            chunk_index=self.sequence,
            content_hash=str(self.provenance.get("content_hash", "")),
        )
