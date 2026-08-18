"""OrientDB graph backend (requires ``pyorient`` extra).

Wraps the OrientDB Python driver behind the
:class:`~loom_ai.contracts_phase4.KnowledgeGraph` protocol, providing
persistent graph storage with the OrientDB multi-model database.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

try:
    import pyorient  # type: ignore[import-untyped]
except ImportError as _exc:
    raise ImportError(
        "OrientDB graph requires the 'pyorient' package.  "
        "Install with: pip install flossware-loom-ai[orientdb]"
    ) from _exc

if TYPE_CHECKING:
    from loom_ai.models_phase4 import (
        Claim,
        KnowledgeEntity,
        KnowledgeRelationship,
        SubgraphResult,
    )


class OrientDBGraphBackend:
    """OrientDB-backed knowledge graph.

    Satisfies :class:`~loom_ai.contracts_phase4.KnowledgeGraph` via
    structural subtyping.
    """

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 2424,
        user: str = "root",
        password: str = "",
        db_name: str = "loom_ai",
    ) -> None:
        self._client = pyorient.OrientDB(host, port)
        self._client.connect(user, password)
        self._db_name = db_name
        if self._client.db_exists(db_name):
            self._client.db_open(db_name, user, password)

    @classmethod
    async def from_env(cls) -> OrientDBGraphBackend:
        """Build from environment variables."""
        return cls(
            host=os.environ.get("ORIENTDB_HOST", "localhost"),
            port=int(os.environ.get("ORIENTDB_PORT", "2424")),
            user=os.environ.get("ORIENTDB_USER", "root"),
            password=os.environ.get("ORIENTDB_PASSWORD", ""),
            db_name=os.environ.get("ORIENTDB_DB", "loom_ai"),
        )

    async def add_entity(self, entity: KnowledgeEntity) -> str:
        cmd = f"INSERT INTO KnowledgeEntity SET label = '{entity.label}', entity_type = '{entity.entity_type}'"
        result = self._client.command(cmd)
        rid = str(result[0]._rid) if result else entity.id or ""
        entity.id = rid
        return rid

    async def get_entity(self, entity_id: str) -> KnowledgeEntity | None:
        results = self._client.command(f"SELECT FROM KnowledgeEntity WHERE @rid = {entity_id}")
        if not results:
            return None
        from loom_ai.models_phase4 import KnowledgeEntity as KE

        rec = results[0]
        return KE(
            id=str(rec._rid),
            label=rec.label,
            entity_type=rec.entity_type,
        )

    async def add_relationship(self, relationship: KnowledgeRelationship) -> str:
        cmd = (
            f"CREATE EDGE KnowledgeRelationship FROM {relationship.source_id} "
            f"TO {relationship.target_id} SET relation_type = '{relationship.relation_type}'"
        )
        result = self._client.command(cmd)
        rid = str(result[0]._rid) if result else relationship.id or ""
        relationship.id = rid
        return rid

    async def add_claim(self, claim: Claim) -> str:
        cmd = (
            f"INSERT INTO Claim SET subject_id = '{claim.subject_id}', "
            f"predicate = '{claim.predicate}', value = '{claim.value}'"
        )
        result = self._client.command(cmd)
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
        from loom_ai.models_phase4 import KnowledgeEntity as KE

        where = f"WHERE label LIKE '%{query}%'"
        if entity_type:
            where += f" AND entity_type = '{entity_type}'"
        results = self._client.command(
            f"SELECT FROM KnowledgeEntity {where} LIMIT {limit}"
        )
        return [
            KE(id=str(r._rid), label=r.label, entity_type=r.entity_type)
            for r in results
        ]
