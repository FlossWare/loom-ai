"""In-memory Google Workspace (GSuite) integration backend.

All classes use only the standard library -- zero external dependencies.
Google API support is behind an import guard and degrades gracefully.

Classes
-------
InMemoryGSuiteGraphAdapter   -- ExternalGraphAdapter protocol implementation
InMemoryGSuiteCapability     -- CapabilityBackend protocol implementation
"""

from __future__ import annotations

import uuid
from typing import Any

from loom_ai.models_phase4 import (
    ExternalEntity,
    ExternalRelationship,
    ImportMapping,
    ImportResult,
)
from loom_ai.models_phase9 import CapabilityDescriptor, CapabilityResult

try:
    import googleapiclient as _gapi_lib  # type: ignore[import-untyped]

    _HAS_GSUITE = True
except ImportError:
    _gapi_lib = None  # type: ignore[assignment]
    _HAS_GSUITE = False


def gsuite_available() -> bool:
    return _HAS_GSUITE


_ENTITY_TYPES = {"document", "spreadsheet", "presentation", "drive_file", "folder"}
_RELATIONSHIP_TYPES = {
    "folder_contains_file",
    "doc_references_sheet",
    "file_shared_with",
}

_CAPABILITIES = [
    CapabilityDescriptor(
        name="create_doc",
        description="Create a Google Doc",
        backend_type="gsuite",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["title"],
        },
    ),
    CapabilityDescriptor(
        name="search_drive",
        description="Search Google Drive files",
        backend_type="gsuite",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    ),
    CapabilityDescriptor(
        name="list_files",
        description="List files in a folder",
        backend_type="gsuite",
        input_schema={
            "type": "object",
            "properties": {"folder_id": {"type": "string"}},
            "required": ["folder_id"],
        },
    ),
    CapabilityDescriptor(
        name="get_document",
        description="Get document content",
        backend_type="gsuite",
        input_schema={
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
        },
    ),
]


class InMemoryGSuiteGraphAdapter:
    """In-memory adapter for importing GSuite entities into the knowledge graph."""

    def __init__(self) -> None:
        self._entities: dict[str, ExternalEntity] = {}
        self._relationships: dict[str, ExternalRelationship] = {}

    async def import_entities(
        self,
        entities: list[ExternalEntity],
        *,
        mapping: ImportMapping | None = None,
    ) -> ImportResult:
        type_map = getattr(mapping, "type_mappings", None) or {}
        imported = 0
        updated = 0
        errors: list[str] = []
        for entity in entities:
            etype = type_map.get(entity.entity_type, entity.entity_type)
            if etype not in _ENTITY_TYPES:
                errors.append(f"unsupported entity type: {etype}")
                continue
            eid = entity.external_id or str(uuid.uuid4())
            if eid in self._entities:
                updated += 1
            else:
                imported += 1
            self._entities[eid] = entity
        return ImportResult(
            entities_imported=imported,
            entities_updated=updated,
            errors=errors,
            source_system="gsuite",
        )

    async def import_relationships(
        self,
        relationships: list[ExternalRelationship],
        *,
        mapping: ImportMapping | None = None,
    ) -> ImportResult:
        type_map = getattr(mapping, "type_mappings", None) or {}
        imported = 0
        updated = 0
        errors: list[str] = []
        for rel in relationships:
            rtype = type_map.get(rel.relation_type, rel.relation_type)
            if rtype not in _RELATIONSHIP_TYPES:
                errors.append(f"unsupported relation type: {rtype}")
                continue
            rid = rel.external_id or str(uuid.uuid4())
            if rid in self._relationships:
                updated += 1
            else:
                imported += 1
            self._relationships[rid] = rel
        return ImportResult(
            relationships_imported=imported,
            relationships_updated=updated,
            errors=errors,
            source_system="gsuite",
        )


class InMemoryGSuiteCapability:
    """In-memory capability backend for Google Workspace operations."""

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}
        self._files: dict[str, list[dict[str, Any]]] = {}
        self._auth_token: str | None = None

    async def discover(self) -> list[CapabilityDescriptor]:
        return list(_CAPABILITIES)

    async def invoke(
        self,
        name: str,
        arguments: dict,
        *,
        auth_token: str | None = None,
    ) -> CapabilityResult:
        if auth_token is not None:
            self._auth_token = auth_token
        if name == "create_doc":
            doc_id = str(uuid.uuid4())
            self._docs[doc_id] = {
                "title": arguments.get("title", ""),
                "content": arguments.get("content", ""),
            }
            return CapabilityResult(
                capability_name=name,
                backend_type="gsuite",
                output={"id": doc_id, **self._docs[doc_id]},
            )
        if name == "search_drive":
            query = arguments.get("query", "").lower()
            results = [
                {"id": did, **d}
                for did, d in self._docs.items()
                if query in d.get("title", "").lower()
            ]
            return CapabilityResult(
                capability_name=name,
                backend_type="gsuite",
                output={"results": results, "query": arguments.get("query", "")},
            )
        if name == "list_files":
            folder_id = arguments.get("folder_id", "")
            return CapabilityResult(
                capability_name=name,
                backend_type="gsuite",
                output={
                    "folder_id": folder_id,
                    "files": self._files.get(folder_id, []),
                },
            )
        if name == "get_document":
            doc_id = arguments.get("doc_id", "")
            doc = self._docs.get(doc_id)
            if doc:
                return CapabilityResult(
                    capability_name=name,
                    backend_type="gsuite",
                    output={"id": doc_id, **doc},
                )
            return CapabilityResult(
                capability_name=name,
                backend_type="gsuite",
                error=f"document not found: {doc_id}",
            )
        return CapabilityResult(
            capability_name=name,
            backend_type="gsuite",
            error=f"unknown capability: {name}",
        )

    async def health(self, name: str | None = None) -> dict[str, bool]:
        if name:
            return {name: any(c.name == name for c in _CAPABILITIES)}
        return {c.name: True for c in _CAPABILITIES}

    async def supports(self, name: str) -> bool:
        return any(c.name == name for c in _CAPABILITIES)
