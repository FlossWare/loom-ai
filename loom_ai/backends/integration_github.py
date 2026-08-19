"""In-memory GitHub integration backend.

All classes use only the standard library -- zero external dependencies.
GitHub API support is behind an import guard and degrades gracefully.

Classes
-------
InMemoryGitHubGraphAdapter   -- ExternalGraphAdapter protocol implementation
InMemoryGitHubCapability     -- CapabilityBackend protocol implementation
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
    import github as _github_lib  # type: ignore[import-untyped]

    _HAS_GITHUB = True
except ImportError:
    _github_lib = None  # type: ignore[assignment]
    _HAS_GITHUB = False


def github_available() -> bool:
    return _HAS_GITHUB


_ENTITY_TYPES = {"repository", "issue", "pull_request", "commit", "branch", "release"}
_RELATIONSHIP_TYPES = {
    "repo_has_issue",
    "repo_has_pr",
    "pr_references_issue",
    "commit_in_repo",
    "branch_of_repo",
}

_CAPABILITIES = [
    CapabilityDescriptor(
        name="create_issue",
        description="Create a GitHub issue",
        backend_type="github",
        input_schema={
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "labels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["repo", "title"],
        },
    ),
    CapabilityDescriptor(
        name="search_code",
        description="Search code in GitHub repositories",
        backend_type="github",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["query"],
        },
    ),
    CapabilityDescriptor(
        name="list_pull_requests",
        description="List pull requests for a repository",
        backend_type="github",
        input_schema={
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "state": {"type": "string", "enum": ["open", "closed", "all"]},
            },
            "required": ["repo"],
        },
    ),
    CapabilityDescriptor(
        name="get_commit",
        description="Get commit details",
        backend_type="github",
        input_schema={
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "sha": {"type": "string"},
            },
            "required": ["repo", "sha"],
        },
    ),
    CapabilityDescriptor(
        name="list_repos",
        description="List repositories for an org or user",
        backend_type="github",
        input_schema={
            "type": "object",
            "properties": {"org_or_user": {"type": "string"}},
            "required": ["org_or_user"],
        },
    ),
]


class InMemoryGitHubGraphAdapter:
    """In-memory adapter for importing GitHub entities into the knowledge graph."""

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
            source_system="github",
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
            source_system="github",
        )


class InMemoryGitHubCapability:
    """In-memory capability backend for GitHub operations."""

    def __init__(self) -> None:
        self._issues: dict[str, dict[str, Any]] = {}
        self._prs: dict[str, list[dict[str, Any]]] = {}
        self._repos: dict[str, list[str]] = {}
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
            issue_id = str(uuid.uuid4())
            self._issues[issue_id] = {
                "repo": arguments.get("repo", ""),
                "title": arguments.get("title", ""),
                "body": arguments.get("body", ""),
                "labels": arguments.get("labels", []),
                "state": "open",
            }
            return CapabilityResult(
                capability_name=name,
                backend_type="github",
                output={"id": issue_id, **self._issues[issue_id]},
            )
        if name == "search_code":
            return CapabilityResult(
                capability_name=name,
                backend_type="github",
                output={"results": [], "query": arguments.get("query", "")},
            )
        if name == "list_pull_requests":
            repo = arguments.get("repo", "")
            return CapabilityResult(
                capability_name=name,
                backend_type="github",
                output={"repo": repo, "pull_requests": self._prs.get(repo, [])},
            )
        if name == "get_commit":
            return CapabilityResult(
                capability_name=name,
                backend_type="github",
                output={
                    "repo": arguments.get("repo", ""),
                    "sha": arguments.get("sha", ""),
                    "message": "(in-memory stub)",
                },
            )
        if name == "list_repos":
            org = arguments.get("org_or_user", "")
            return CapabilityResult(
                capability_name=name,
                backend_type="github",
                output={"org_or_user": org, "repos": self._repos.get(org, [])},
            )
        return CapabilityResult(
            capability_name=name,
            backend_type="github",
            error=f"unknown capability: {name}",
        )

    async def health(self, name: str | None = None) -> dict[str, bool]:
        if name:
            return {name: any(c.name == name for c in _CAPABILITIES)}
        return {c.name: True for c in _CAPABILITIES}

    async def supports(self, name: str) -> bool:
        return any(c.name == name for c in _CAPABILITIES)
