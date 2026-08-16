"""In-memory knowledge graph backend with optional OrientDB integration.

All classes use only the standard library -- zero external dependencies.
OrientDB support is behind an import guard and degrades gracefully.
Suitable for testing, local development, and the 'crush' deployment
profile.  All data is lost on process exit.

Classes
-------
InMemoryKnowledgeGraph  -- KnowledgeGraph protocol implementation
                           with BFS/DFS traversal and path finding

The ``InMemoryKnowledgeGraph`` satisfies the ``KnowledgeGraph`` protocol
from ``contracts_phase4.py`` via structural subtyping.
"""

from __future__ import annotations

import uuid
from collections import deque

from loom_ai.models_phase4 import (
    Claim,
    KnowledgeEntity,
    KnowledgeRelationship,
    SubgraphResult,
)

# ── Optional OrientDB integration ────────────────────────────────────────

try:
    import pyorient  # type: ignore[import-untyped]

    _HAS_ORIENTDB = True
except ImportError:
    pyorient = None  # type: ignore[assignment]
    _HAS_ORIENTDB = False


def orientdb_available() -> bool:
    """Return ``True`` if the ``pyorient`` driver is importable."""
    return _HAS_ORIENTDB


# ── InMemoryKnowledgeGraph ───────────────────────────────────────────────


class InMemoryKnowledgeGraph:
    """In-memory graph store implementing the KnowledgeGraph protocol.

    Provides:
    - Node (entity) storage with properties and metadata
    - Edge (relationship) storage with labels and properties
    - BFS and DFS traversal
    - Shortest-path finding (BFS-based)
    - Entity search by label or properties

    Satisfies :class:`~loom_ai.contracts_phase4.KnowledgeGraph` via
    structural subtyping.
    """

    def __init__(self) -> None:
        # entity_id -> KnowledgeEntity
        self._entities: dict[str, KnowledgeEntity] = {}
        # relationship_id -> KnowledgeRelationship
        self._relationships: dict[str, KnowledgeRelationship] = {}
        # claim_id -> Claim
        self._claims: dict[str, Claim] = {}

        # Adjacency indexes for fast traversal.
        # entity_id -> set of relationship_ids (outgoing)
        self._outgoing: dict[str, set[str]] = {}
        # entity_id -> set of relationship_ids (incoming)
        self._incoming: dict[str, set[str]] = {}

    # -- KnowledgeGraph protocol methods -----------------------------------

    async def add_entity(self, entity: KnowledgeEntity) -> str:
        """Persist an entity and return its id."""
        eid = entity.id or str(uuid.uuid4())
        entity.id = eid
        self._entities[eid] = entity
        self._outgoing.setdefault(eid, set())
        self._incoming.setdefault(eid, set())
        return eid

    async def get_entity(self, entity_id: str) -> KnowledgeEntity | None:
        """Return an entity by id, or ``None`` if not found."""
        return self._entities.get(entity_id)

    async def update_entity(
        self,
        entity_id: str,
        *,
        properties: dict | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Update properties and/or metadata on an existing entity."""
        entity = self._entities.get(entity_id)
        if entity is None:
            return
        if properties is not None:
            entity.properties.update(properties)
        if metadata is not None:
            entity.metadata.update(metadata)

    async def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity and its incident relationships."""
        if entity_id not in self._entities:
            return False

        # Remove incident relationships.
        rel_ids = set()
        rel_ids.update(self._outgoing.pop(entity_id, set()))
        rel_ids.update(self._incoming.pop(entity_id, set()))
        for rid in rel_ids:
            rel = self._relationships.pop(rid, None)
            if rel is not None:
                # Clean the other end's index.
                if rel.source_id != entity_id:
                    self._outgoing.get(rel.source_id, set()).discard(rid)
                if rel.target_id != entity_id:
                    self._incoming.get(rel.target_id, set()).discard(rid)

        # Remove claims about this entity.
        to_remove = [
            cid for cid, c in self._claims.items() if c.subject_id == entity_id
        ]
        for cid in to_remove:
            del self._claims[cid]

        del self._entities[entity_id]
        return True

    async def add_relationship(self, relationship: KnowledgeRelationship) -> str:
        """Persist a relationship and return its id."""
        rid = relationship.id or str(uuid.uuid4())
        relationship.id = rid
        self._relationships[rid] = relationship

        self._outgoing.setdefault(relationship.source_id, set()).add(rid)
        self._incoming.setdefault(relationship.target_id, set()).add(rid)
        return rid

    async def get_relationships(
        self,
        entity_id: str,
        *,
        relation_type: str | None = None,
        direction: str = "outgoing",
    ) -> list[KnowledgeRelationship]:
        """Return relationships for an entity.

        *direction* is one of ``"outgoing"``, ``"incoming"``, or ``"both"``.
        """
        rel_ids: set[str] = set()
        if direction in ("outgoing", "both"):
            rel_ids.update(self._outgoing.get(entity_id, set()))
        if direction in ("incoming", "both"):
            rel_ids.update(self._incoming.get(entity_id, set()))

        results: list[KnowledgeRelationship] = []
        for rid in sorted(rel_ids):
            rel = self._relationships.get(rid)
            if rel is None:
                continue
            if relation_type is not None and rel.relation_type != relation_type:
                continue
            results.append(rel)
        return results

    async def delete_relationship(self, relationship_id: str) -> bool:
        """Delete a relationship by id."""
        rel = self._relationships.pop(relationship_id, None)
        if rel is None:
            return False
        self._outgoing.get(rel.source_id, set()).discard(relationship_id)
        self._incoming.get(rel.target_id, set()).discard(relationship_id)
        return True

    async def add_claim(self, claim: Claim) -> str:
        """Persist a claim and return its id."""
        cid = claim.id or str(uuid.uuid4())
        claim.id = cid
        self._claims[cid] = claim
        return cid

    async def get_claims(
        self,
        entity_id: str,
        *,
        predicate: str | None = None,
    ) -> list[Claim]:
        """Return claims about an entity, optionally filtered by predicate."""
        results: list[Claim] = []
        for claim in self._claims.values():
            if claim.subject_id != entity_id:
                continue
            if predicate is not None and claim.predicate != predicate:
                continue
            results.append(claim)
        return results

    async def search_entities(
        self,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> list[KnowledgeEntity]:
        """Search entities by label or property values."""
        lower_q = query.lower()
        matches: list[KnowledgeEntity] = []

        for entity in self._entities.values():
            if entity_type is not None and entity.entity_type != entity_type:
                continue

            # Match against label.
            if lower_q in entity.label.lower():
                matches.append(entity)
                continue

            # Match against property values.
            for val in entity.properties.values():
                if lower_q in str(val).lower():
                    matches.append(entity)
                    break

        # Sort by label for determinism, then truncate.
        matches.sort(key=lambda e: e.label)
        return matches[:limit]

    # -- Graph traversal ---------------------------------------------------

    async def bfs(
        self,
        start_id: str,
        *,
        max_depth: int = 3,
        relation_type: str | None = None,
    ) -> list[str]:
        """Breadth-first traversal from *start_id*.

        Returns entity ids in BFS order (including *start_id*).
        """
        if start_id not in self._entities:
            return []

        visited: list[str] = []
        seen: set[str] = {start_id}
        queue: deque[tuple[str, int]] = deque([(start_id, 0)])

        while queue:
            node, depth = queue.popleft()
            visited.append(node)

            if depth >= max_depth:
                continue

            for rid in sorted(self._outgoing.get(node, set())):
                rel = self._relationships.get(rid)
                if rel is None:
                    continue
                if relation_type is not None and rel.relation_type != relation_type:
                    continue
                if rel.target_id not in seen:
                    seen.add(rel.target_id)
                    queue.append((rel.target_id, depth + 1))

        return visited

    async def dfs(
        self,
        start_id: str,
        *,
        max_depth: int = 3,
        relation_type: str | None = None,
    ) -> list[str]:
        """Depth-first traversal from *start_id*.

        Returns entity ids in DFS pre-order (including *start_id*).
        """
        if start_id not in self._entities:
            return []

        visited: list[str] = []
        seen: set[str] = set()

        def _visit(node: str, depth: int) -> None:
            if node in seen:
                return
            seen.add(node)
            visited.append(node)
            if depth >= max_depth:
                return
            for rid in sorted(self._outgoing.get(node, set())):
                rel = self._relationships.get(rid)
                if rel is None:
                    continue
                if relation_type is not None and rel.relation_type != relation_type:
                    continue
                _visit(rel.target_id, depth + 1)

        _visit(start_id, 0)
        return visited

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        *,
        max_depth: int = 10,
    ) -> list[str] | None:
        """Find a shortest path from *source_id* to *target_id* via BFS.

        Returns a list of entity ids from source to target (inclusive),
        or ``None`` if no path exists within *max_depth*.
        """
        if source_id not in self._entities or target_id not in self._entities:
            return None

        if source_id == target_id:
            return [source_id]

        # BFS with parent tracking.
        parent: dict[str, str] = {}
        seen: set[str] = {source_id}
        queue: deque[tuple[str, int]] = deque([(source_id, 0)])

        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for rid in sorted(self._outgoing.get(node, set())):
                neighbor = self._neighbor_from_edge(rid)
                if neighbor is None or neighbor in seen:
                    continue
                parent[neighbor] = node
                if neighbor == target_id:
                    return self._reconstruct_path(parent, source_id, target_id)
                seen.add(neighbor)
                queue.append((neighbor, depth + 1))

        return None

    async def get_subgraph(
        self,
        entity_ids: list[str],
        *,
        include_relationships: bool = True,
    ) -> SubgraphResult:
        """Extract the subgraph induced by the given entity ids."""
        entities = [self._entities[eid] for eid in entity_ids if eid in self._entities]

        relationships: list[KnowledgeRelationship] = []
        if include_relationships:
            id_set = set(entity_ids)
            for rel in self._relationships.values():
                if rel.source_id in id_set and rel.target_id in id_set:
                    relationships.append(rel)

        return SubgraphResult(
            entities=entities,
            relationships=relationships,
        )

    def _neighbor_from_edge(self, rid: str) -> str | None:
        rel = self._relationships.get(rid)
        return rel.target_id if rel is not None else None

    @staticmethod
    def _reconstruct_path(
        parent: dict[str, str], source_id: str, target_id: str
    ) -> list[str]:
        path = [target_id]
        cur = target_id
        while cur != source_id:
            cur = parent[cur]
            path.append(cur)
        path.reverse()
        return path

    # -- Utility -----------------------------------------------------------

    @property
    def entity_count(self) -> int:
        """Number of entities in the graph."""
        return len(self._entities)

    @property
    def relationship_count(self) -> int:
        """Number of relationships in the graph."""
        return len(self._relationships)

    @property
    def claim_count(self) -> int:
        """Number of claims in the graph."""
        return len(self._claims)
