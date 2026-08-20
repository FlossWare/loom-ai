"""OrientDB graph backend (requires ``pyorient`` extra).

Wraps the OrientDB Python driver behind the
:class:`~loom_ai.contracts_graph.KnowledgeGraph` protocol, providing
persistent graph storage with the OrientDB multi-model database.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import TYPE_CHECKING

try:
    import pyorient  # type: ignore[import-untyped]
except ImportError as _exc:
    raise ImportError(
        "OrientDB graph requires the 'pyorient' package.  "
        "Install with: pip install flossware-loom-ai[orientdb]"
    ) from _exc

if TYPE_CHECKING:
    from loom_ai.models_graph import (
        Claim,
        KnowledgeEntity,
        KnowledgeRelationship,
    )

_SAFE_RID = re.compile(r"^#\d+:\d+$")


def _escape(value: str) -> str:
    """Escape single quotes for OrientDB SQL string literals."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _validate_rid(rid: str) -> str:
    """Validate an OrientDB record ID (#cluster:position)."""
    if not _SAFE_RID.match(rid):
        raise ValueError(f"Invalid OrientDB record ID: {rid!r}")
    return rid


class OrientDBGraphBackend:
    """OrientDB-backed knowledge graph.

    Satisfies :class:`~loom_ai.contracts_graph.KnowledgeGraph` via
    structural subtyping.
    """

    def __init__(self, *, client: pyorient.OrientDB, db_name: str) -> None:
        self._client = client
        self._db_name = db_name

    async def close(self) -> None:
        """Close the underlying OrientDB connection."""
        await asyncio.to_thread(self._client.shutdown)

    @classmethod
    async def from_env(cls) -> OrientDBGraphBackend:
        """Build from environment variables (all blocking I/O runs in a thread)."""

        def _connect() -> OrientDBGraphBackend:
            host = os.environ.get("ORIENTDB_HOST", "localhost")
            port = int(os.environ.get("ORIENTDB_PORT", "2424"))
            user = os.environ.get("ORIENTDB_USER", "root")
            password = os.environ.get("ORIENTDB_PASSWORD", "")
            db_name = os.environ.get("ORIENTDB_DB", "loom_ai")
            client = pyorient.OrientDB(host, port)
            client.connect(user, password)
            if client.db_exists(db_name):
                client.db_open(db_name, user, password)
            return cls(client=client, db_name=db_name)

        return await asyncio.to_thread(_connect)

    async def add_entity(self, entity: KnowledgeEntity) -> str:
        label = _escape(entity.label)
        etype = _escape(entity.entity_type)
        cmd = (
            f"INSERT INTO KnowledgeEntity"
            f" SET label = '{label}',"
            f" entity_type = '{etype}'"
        )
        result = await asyncio.to_thread(self._client.command, cmd)
        rid = str(result[0]._rid) if result else entity.id or ""
        entity.id = rid
        return rid

    async def get_entity(self, entity_id: str) -> KnowledgeEntity | None:
        _validate_rid(entity_id)
        results = await asyncio.to_thread(
            self._client.command,
            f"SELECT FROM KnowledgeEntity WHERE @rid = {entity_id}",
        )
        if not results:
            return None
        from loom_ai.models_graph import KnowledgeEntity as KE

        rec = results[0]
        return KE(
            id=str(rec._rid),
            label=rec.label,
            entity_type=rec.entity_type,
        )

    async def add_relationship(self, relationship: KnowledgeRelationship) -> str:
        _validate_rid(relationship.source_id)
        _validate_rid(relationship.target_id)
        rtype = _escape(relationship.relation_type)
        cmd = (
            f"CREATE EDGE KnowledgeRelationship FROM {relationship.source_id} "
            f"TO {relationship.target_id} SET relation_type = '{rtype}'"
        )
        result = await asyncio.to_thread(self._client.command, cmd)
        rid = str(result[0]._rid) if result else relationship.id or ""
        relationship.id = rid
        return rid

    async def add_claim(self, claim: Claim) -> str:
        subject = _escape(claim.subject_id)
        predicate = _escape(claim.predicate)
        value = _escape(claim.value)
        cmd = (
            f"INSERT INTO Claim SET subject_id = '{subject}', "
            f"predicate = '{predicate}', value = '{value}'"
        )
        result = await asyncio.to_thread(self._client.command, cmd)
        rid = str(result[0]._rid) if result else claim.id or ""
        claim.id = rid
        return rid

    async def search_entities(
        self,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> list[KnowledgeEntity]:
        from loom_ai.models_graph import KnowledgeEntity as KE

        escaped_q = _escape(query)
        where = f"WHERE label LIKE '%{escaped_q}%'"
        if entity_type:
            where += f" AND entity_type = '{_escape(entity_type)}'"
        results = await asyncio.to_thread(
            self._client.command,
            f"SELECT FROM KnowledgeEntity {where} LIMIT {limit}",
        )
        return [
            KE(id=str(r._rid), label=r.label, entity_type=r.entity_type)
            for r in results
        ]
