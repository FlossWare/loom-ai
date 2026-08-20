"""In-memory Slack integration backend.

All classes use only the standard library -- zero external dependencies.
Slack SDK support is behind an import guard and degrades gracefully.

Classes
-------
InMemorySlackGraphAdapter   -- ExternalGraphAdapter protocol implementation
InMemorySlackCapability     -- CapabilityBackend protocol implementation
"""

from __future__ import annotations

import uuid
from typing import Any

from loom_ai.models_context import CapabilityDescriptor, CapabilityResult
from loom_ai.models_graph import (
    ExternalEntity,
    ExternalRelationship,
    ImportMapping,
    ImportResult,
)

try:
    import slack_sdk as _slack_lib  # type: ignore[import-untyped]

    _HAS_SLACK = True
except ImportError:
    _slack_lib = None  # type: ignore[assignment]
    _HAS_SLACK = False


def slack_available() -> bool:
    return _HAS_SLACK


_ENTITY_TYPES = {"channel", "message", "thread", "user", "workspace", "reaction"}
_RELATIONSHIP_TYPES = {
    "channel_has_message",
    "message_has_thread",
    "user_sent_message",
}

_CAPABILITIES = [
    CapabilityDescriptor(
        name="send_message",
        description="Send a Slack message",
        backend_type="slack",
        input_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "text": {"type": "string"},
                "thread_ts": {"type": "string"},
            },
            "required": ["channel", "text"],
        },
    ),
    CapabilityDescriptor(
        name="search_messages",
        description="Search Slack messages",
        backend_type="slack",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "channel": {"type": "string"},
            },
            "required": ["query"],
        },
    ),
    CapabilityDescriptor(
        name="list_channels",
        description="List Slack channels",
        backend_type="slack",
        input_schema={
            "type": "object",
            "properties": {
                "types": {"type": "string", "enum": ["public", "private", "all"]},
            },
        },
    ),
    CapabilityDescriptor(
        name="get_thread",
        description="Get thread replies",
        backend_type="slack",
        input_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "thread_ts": {"type": "string"},
            },
            "required": ["channel", "thread_ts"],
        },
    ),
]


class InMemorySlackGraphAdapter:
    """In-memory adapter for importing Slack entities into the knowledge graph."""

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
            source_system="slack",
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
            source_system="slack",
        )


class InMemorySlackCapability:
    """In-memory capability backend for Slack operations."""

    def __init__(self) -> None:
        self._messages: dict[str, dict[str, Any]] = {}
        self._channels: dict[str, dict[str, Any]] = {}
        self._threads: dict[str, list[dict[str, Any]]] = {}
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
        if name == "send_message":
            msg_id = str(uuid.uuid4())
            self._messages[msg_id] = {
                "channel": arguments.get("channel", ""),
                "text": arguments.get("text", ""),
                "thread_ts": arguments.get("thread_ts"),
                "ts": msg_id,
            }
            return CapabilityResult(
                capability_name=name,
                backend_type="slack",
                output={"ok": True, "ts": msg_id, **self._messages[msg_id]},
            )
        if name == "search_messages":
            query = arguments.get("query", "").lower()
            results = [
                {"id": mid, **m}
                for mid, m in self._messages.items()
                if query in m.get("text", "").lower()
            ]
            return CapabilityResult(
                capability_name=name,
                backend_type="slack",
                output={"results": results, "query": arguments.get("query", "")},
            )
        if name == "list_channels":
            return CapabilityResult(
                capability_name=name,
                backend_type="slack",
                output={"channels": list(self._channels.values())},
            )
        if name == "get_thread":
            key = f"{arguments.get('channel', '')}:{arguments.get('thread_ts', '')}"
            return CapabilityResult(
                capability_name=name,
                backend_type="slack",
                output={"replies": self._threads.get(key, [])},
            )
        return CapabilityResult(
            capability_name=name,
            backend_type="slack",
            error=f"unknown capability: {name}",
        )

    async def health(self, name: str | None = None) -> dict[str, bool]:
        if name:
            return {name: any(c.name == name for c in _CAPABILITIES)}
        return {c.name: True for c in _CAPABILITIES}

    async def supports(self, name: str) -> bool:
        return any(c.name == name for c in _CAPABILITIES)
