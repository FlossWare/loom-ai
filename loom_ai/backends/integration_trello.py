"""In-memory Trello integration backend.

All classes use only the standard library -- zero external dependencies.
Trello API support is behind an import guard and degrades gracefully.

Classes
-------
InMemoryTrelloGraphAdapter   -- ExternalGraphAdapter protocol implementation
InMemoryTrelloCapability     -- CapabilityBackend protocol implementation
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
    import trello as _trello_lib  # type: ignore[import-untyped]

    _HAS_TRELLO = True
except ImportError:
    _trello_lib = None  # type: ignore[assignment]
    _HAS_TRELLO = False


def trello_available() -> bool:
    return _HAS_TRELLO


_ENTITY_TYPES = {"board", "list", "card", "member", "label", "checklist"}
_RELATIONSHIP_TYPES = {
    "board_has_list",
    "list_has_card",
    "card_has_member",
    "card_has_label",
}

_CAPABILITIES = [
    CapabilityDescriptor(
        name="create_card",
        description="Create a Trello card",
        backend_type="trello",
        input_schema={
            "type": "object",
            "properties": {
                "list_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["list_id", "name"],
        },
    ),
    CapabilityDescriptor(
        name="move_card",
        description="Move a card between lists",
        backend_type="trello",
        input_schema={
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "target_list_id": {"type": "string"},
            },
            "required": ["card_id", "target_list_id"],
        },
    ),
    CapabilityDescriptor(
        name="list_boards",
        description="List all boards for a member",
        backend_type="trello",
        input_schema={
            "type": "object",
            "properties": {"member_id": {"type": "string"}},
            "required": ["member_id"],
        },
    ),
    CapabilityDescriptor(
        name="get_card",
        description="Get card details",
        backend_type="trello",
        input_schema={
            "type": "object",
            "properties": {"card_id": {"type": "string"}},
            "required": ["card_id"],
        },
    ),
]


class InMemoryTrelloGraphAdapter:
    """In-memory adapter for importing Trello entities into the knowledge graph."""

    def __init__(self) -> None:
        self._entities: dict[str, ExternalEntity] = {}
        self._relationships: dict[str, ExternalRelationship] = {}

    async def import_entities(
        self,
        entities: list[ExternalEntity],
        *,
        mapping: ImportMapping | None = None,
    ) -> ImportResult:
        imported = 0
        updated = 0
        errors: list[str] = []
        for entity in entities:
            if entity.entity_type not in _ENTITY_TYPES:
                errors.append(f"unsupported entity type: {entity.entity_type}")
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
            source_system="trello",
        )

    async def import_relationships(
        self,
        relationships: list[ExternalRelationship],
        *,
        mapping: ImportMapping | None = None,
    ) -> ImportResult:
        imported = 0
        updated = 0
        errors: list[str] = []
        for rel in relationships:
            if rel.relation_type not in _RELATIONSHIP_TYPES:
                errors.append(f"unsupported relation type: {rel.relation_type}")
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
            source_system="trello",
        )


class InMemoryTrelloCapability:
    """In-memory capability backend for Trello operations."""

    def __init__(self) -> None:
        self._cards: dict[str, dict[str, Any]] = {}
        self._boards: dict[str, list[dict[str, Any]]] = {}

    async def discover(self) -> list[CapabilityDescriptor]:
        return list(_CAPABILITIES)

    async def invoke(
        self,
        name: str,
        arguments: dict,
        *,
        auth_token: str | None = None,
    ) -> CapabilityResult:
        if name == "create_card":
            card_id = str(uuid.uuid4())
            self._cards[card_id] = {
                "list_id": arguments.get("list_id", ""),
                "name": arguments.get("name", ""),
                "description": arguments.get("description", ""),
            }
            return CapabilityResult(
                capability_name=name,
                backend_type="trello",
                output={"id": card_id, **self._cards[card_id]},
            )
        if name == "move_card":
            card_id = arguments.get("card_id", "")
            if card_id in self._cards:
                self._cards[card_id]["list_id"] = arguments.get("target_list_id", "")
                return CapabilityResult(
                    capability_name=name,
                    backend_type="trello",
                    output={"moved": True, "card_id": card_id},
                )
            return CapabilityResult(
                capability_name=name,
                backend_type="trello",
                error=f"card not found: {card_id}",
            )
        if name == "list_boards":
            member = arguments.get("member_id", "")
            return CapabilityResult(
                capability_name=name,
                backend_type="trello",
                output={"member_id": member, "boards": self._boards.get(member, [])},
            )
        if name == "get_card":
            card_id = arguments.get("card_id", "")
            card = self._cards.get(card_id)
            if card:
                return CapabilityResult(
                    capability_name=name,
                    backend_type="trello",
                    output={"id": card_id, **card},
                )
            return CapabilityResult(
                capability_name=name,
                backend_type="trello",
                error=f"card not found: {card_id}",
            )
        return CapabilityResult(
            capability_name=name,
            backend_type="trello",
            error=f"unknown capability: {name}",
        )

    async def health(self, name: str | None = None) -> dict[str, bool]:
        if name:
            return {name: any(c.name == name for c in _CAPABILITIES)}
        return {c.name: True for c in _CAPABILITIES}

    async def supports(self, name: str) -> bool:
        return any(c.name == name for c in _CAPABILITIES)
