"""Notion integration backend for Loom AI.

Classes:
    InMemoryNotionGraphAdapter: Notion entity graph adapter.
        Handles Notion entities and relationships in-memory.
    InMemoryNotionCapability: Capability backend for executing Notion actions in-memory.
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
    from notion_client import Client as NotionClient

    HAS_NOTION_SDK = True
except ImportError:
    HAS_NOTION_SDK = False
    NotionClient = None


class InMemoryNotionGraphAdapter:
    def __init__(self) -> None:
        self._entities: dict[str, ExternalEntity] = {}
        self._relationships: dict[str, ExternalRelationship] = {}

    async def import_entities(
        self,
        entities: list[ExternalEntity],
        *,
        mapping: ImportMapping | None = None,
    ) -> ImportResult:
        valid_types = {"page", "database", "block", "user", "workspace"}
        type_map = getattr(mapping, "type_mappings", None) or {}
        imported = 0
        errors = []

        for entity in entities:
            try:
                raw_type = getattr(entity, "entity_type", None)
                entity_type = type_map.get(raw_type, raw_type) if raw_type else None
                entity_id = getattr(entity, "entity_id", None)

                if not entity_id:
                    errors.append("Entity missing entity_id")
                    continue

                if entity_type in valid_types:
                    self._entities[entity_id] = entity
                    imported += 1
                else:
                    errors.append(f"Unsupported entity type: {entity_type}")
            except Exception as e:
                errors.append(str(e))

        return ImportResult(
            success=len(errors) == 0,
            imported_count=imported,
            failed_count=len(entities) - imported,
            errors=errors if errors else None,
        )

    async def import_relationships(
        self,
        relationships: list[ExternalRelationship],
        *,
        mapping: ImportMapping | None = None,
    ) -> ImportResult:
        valid_types = {"database_has_page", "page_has_block", "user_created_page"}
        type_map = getattr(mapping, "type_mappings", None) or {}
        imported = 0
        errors = []

        for rel in relationships:
            try:
                raw_rtype = getattr(rel, "relationship_type", None)
                rel_type = type_map.get(raw_rtype, raw_rtype) if raw_rtype else None
                rel_id = getattr(rel, "relationship_id", None) or f"rel_{uuid.uuid4()}"

                if rel_type in valid_types:
                    self._relationships[rel_id] = rel
                    imported += 1
                else:
                    errors.append(f"Unsupported relationship type: {rel_type}")
            except Exception as e:
                errors.append(str(e))

        return ImportResult(
            success=len(errors) == 0,
            imported_count=imported,
            failed_count=len(relationships) - imported,
            errors=errors if errors else None,
        )


class InMemoryNotionCapability:
    def __init__(self) -> None:
        self._pages: list[dict[str, Any]] = [
            {"id": "page_1", "title": "Getting Started", "parent_db": "db_1"},
            {"id": "page_2", "title": "Architecture Notes", "parent_db": "db_1"},
        ]
        self._databases: list[dict[str, Any]] = [
            {"id": "db_1", "title": "Project Wiki"},
        ]
        self._capabilities = {"create_page", "search", "query_database", "update_page"}

    async def discover(self) -> list[CapabilityDescriptor]:
        return [
            CapabilityDescriptor(
                name="create_page",
                description="Create a new page in a Notion database or as a sub-page",
                parameters={
                    "type": "object",
                    "properties": {
                        "parent_id": {
                            "type": "string",
                            "description": "Parent database or page ID",
                        },
                        "title": {"type": "string", "description": "Page title"},
                        "content": {"type": "string", "description": "Page content"},
                    },
                    "required": ["parent_id", "title"],
                },
            ),
            CapabilityDescriptor(
                name="search",
                description="Search for pages and databases in Notion",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                    },
                    "required": ["query"],
                },
            ),
            CapabilityDescriptor(
                name="query_database",
                description="Query a Notion database for pages matching filters",
                parameters={
                    "type": "object",
                    "properties": {
                        "database_id": {
                            "type": "string",
                            "description": "Database ID to query",
                        },
                        "filter": {
                            "type": "object",
                            "description": "Optional filter criteria",
                        },
                    },
                    "required": ["database_id"],
                },
            ),
            CapabilityDescriptor(
                name="update_page",
                description="Update properties of an existing Notion page",
                parameters={
                    "type": "object",
                    "properties": {
                        "page_id": {
                            "type": "string",
                            "description": "Page ID to update",
                        },
                        "title": {"type": "string", "description": "New title"},
                        "content": {"type": "string", "description": "New content"},
                    },
                    "required": ["page_id"],
                },
            ),
        ]

    def _invoke_live(
        self, name: str, arguments: dict, auth_token: str
    ) -> CapabilityResult:
        client = NotionClient(auth=auth_token)
        if name == "create_page":
            res = client.pages.create(
                parent={"database_id": arguments["parent_id"]},
                properties={
                    "title": {"title": [{"text": {"content": arguments["title"]}}]}
                },
            )
            return CapabilityResult(success=True, result=dict(res), error=None)
        if name == "search":
            res = client.search(query=arguments["query"])
            return CapabilityResult(success=True, result=dict(res), error=None)
        if name == "query_database":
            res = client.databases.query(database_id=arguments["database_id"])
            return CapabilityResult(success=True, result=dict(res), error=None)
        if name == "update_page":
            props = {}
            if "title" in arguments:
                props["title"] = {"title": [{"text": {"content": arguments["title"]}}]}
            res = client.pages.update(
                page_id=arguments["page_id"],
                properties=props,
            )
            return CapabilityResult(success=True, result=dict(res), error=None)
        return CapabilityResult(
            success=False, result=None, error=f"Unknown capability: {name}"
        )

    def _invoke_in_memory(self, name: str, arguments: dict) -> CapabilityResult:
        if name == "create_page":
            new_page = {
                "id": f"p_{uuid.uuid4().hex[:8]}",
                "title": arguments["title"],
                "content": arguments.get("content", ""),
                "parent_db": arguments["parent_id"],
            }
            self._pages.append(new_page)
            return CapabilityResult(success=True, result={"page": new_page}, error=None)
        if name == "search":
            query = arguments["query"].lower()
            matches = [p for p in self._pages if query in p.get("title", "").lower()]
            matches += [
                d for d in self._databases if query in d.get("title", "").lower()
            ]
            return CapabilityResult(
                success=True, result={"results": matches}, error=None
            )
        if name == "query_database":
            db_id = arguments["database_id"]
            pages = [p for p in self._pages if p.get("parent_db") == db_id]
            return CapabilityResult(success=True, result={"results": pages}, error=None)
        if name == "update_page":
            page_id = arguments["page_id"]
            page = next((p for p in self._pages if p["id"] == page_id), None)
            if page is None:
                return CapabilityResult(
                    success=False, result=None, error="Page not found"
                )
            if "title" in arguments:
                page["title"] = arguments["title"]
            if "content" in arguments:
                page["content"] = arguments["content"]
            return CapabilityResult(success=True, result={"page": page}, error=None)
        return CapabilityResult(
            success=False, result=None, error=f"Unknown capability: {name}"
        )

    async def invoke(
        self,
        name: str,
        arguments: dict,
        *,
        auth_token: str | None = None,
    ) -> CapabilityResult:
        if not await self.supports(name):
            return CapabilityResult(
                success=False,
                result=None,
                error=f"Capability '{name}' is not supported.",
            )
        if auth_token and HAS_NOTION_SDK and NotionClient is not None:
            try:
                return self._invoke_live(name, arguments, auth_token)
            except Exception as e:
                return CapabilityResult(success=False, result=None, error=str(e))
        try:
            return self._invoke_in_memory(name, arguments)
        except KeyError as e:
            return CapabilityResult(
                success=False,
                result=None,
                error=f"Missing required argument: {str(e)}",
            )

    async def health(self, name: str | None = None) -> dict[str, bool]:
        status = dict.fromkeys(self._capabilities, True)
        if name is not None:
            return {name: status.get(name, False)}
        return status

    async def supports(self, name: str) -> bool:
        return name in self._capabilities
