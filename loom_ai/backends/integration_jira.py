"""In-memory Jira integration backend.

All classes use only the standard library -- zero external dependencies.
Jira API support is behind an import guard and degrades gracefully.

Classes
-------
InMemoryJiraGraphAdapter   -- ExternalGraphAdapter protocol implementation
InMemoryJiraCapability     -- CapabilityBackend protocol implementation
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
    import jira as _jira_lib  # type: ignore[import-untyped]

    _HAS_JIRA = True
except ImportError:
    _jira_lib = None  # type: ignore[assignment]
    _HAS_JIRA = False


def jira_available() -> bool:
    return _HAS_JIRA


_ENTITY_TYPES = {"issue", "project", "sprint", "epic", "component", "version"}
_RELATIONSHIP_TYPES = {
    "project_has_issue",
    "sprint_has_issue",
    "issue_in_epic",
    "issue_has_component",
}

_CAPABILITIES = [
    CapabilityDescriptor(
        name="create_issue",
        description="Create a Jira issue",
        backend_type="jira",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "issue_type": {"type": "string"},
            },
            "required": ["project", "summary"],
        },
    ),
    CapabilityDescriptor(
        name="search_issues",
        description="Search Jira issues with JQL",
        backend_type="jira",
        input_schema={
            "type": "object",
            "properties": {
                "jql": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["jql"],
        },
    ),
    CapabilityDescriptor(
        name="transition_issue",
        description="Transition a Jira issue to a new state",
        backend_type="jira",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {"type": "string"},
                "transition_id": {"type": "string"},
            },
            "required": ["issue_key", "transition_id"],
        },
    ),
    CapabilityDescriptor(
        name="get_issue",
        description="Get Jira issue details",
        backend_type="jira",
        input_schema={
            "type": "object",
            "properties": {"issue_key": {"type": "string"}},
            "required": ["issue_key"],
        },
    ),
]


class InMemoryJiraGraphAdapter:
    """In-memory adapter for importing Jira entities into the knowledge graph."""

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
            source_system="jira",
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
            source_system="jira",
        )


class InMemoryJiraCapability:
    """In-memory capability backend for Jira operations."""

    def __init__(self) -> None:
        self._issues: dict[str, dict[str, Any]] = {}
        self._counter: int = 0
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
        if name == "create_issue":
            self._counter += 1
            project = arguments.get("project", "PROJ")
            issue_key = f"{project}-{self._counter}"
            self._issues[issue_key] = {
                "key": issue_key,
                "project": project,
                "summary": arguments.get("summary", ""),
                "description": arguments.get("description", ""),
                "issue_type": arguments.get("issue_type", "Task"),
                "status": "To Do",
            }
            return CapabilityResult(
                capability_name=name,
                backend_type="jira",
                output=self._issues[issue_key],
            )
        if name == "search_issues":
            jql = arguments.get("jql", "").lower()
            max_results = arguments.get("max_results", 50)
            results = [
                issue
                for issue in self._issues.values()
                if jql in issue.get("summary", "").lower()
                or jql in issue.get("description", "").lower()
            ][:max_results]
            return CapabilityResult(
                capability_name=name,
                backend_type="jira",
                output={"issues": results, "total": len(results)},
            )
        if name == "transition_issue":
            issue_key = arguments.get("issue_key", "")
            issue = self._issues.get(issue_key)
            if issue:
                issue["status"] = arguments.get("transition_id", "Done")
                return CapabilityResult(
                    capability_name=name,
                    backend_type="jira",
                    output={"key": issue_key, "status": issue["status"]},
                )
            return CapabilityResult(
                capability_name=name,
                backend_type="jira",
                error=f"issue not found: {issue_key}",
            )
        if name == "get_issue":
            issue_key = arguments.get("issue_key", "")
            issue = self._issues.get(issue_key)
            if issue:
                return CapabilityResult(
                    capability_name=name,
                    backend_type="jira",
                    output=issue,
                )
            return CapabilityResult(
                capability_name=name,
                backend_type="jira",
                error=f"issue not found: {issue_key}",
            )
        return CapabilityResult(
            capability_name=name,
            backend_type="jira",
            error=f"unknown capability: {name}",
        )

    async def health(self, name: str | None = None) -> dict[str, bool]:
        if name:
            return {name: any(c.name == name for c in _CAPABILITIES)}
        return {c.name: True for c in _CAPABILITIES}

    async def supports(self, name: str) -> bool:
        return any(c.name == name for c in _CAPABILITIES)
