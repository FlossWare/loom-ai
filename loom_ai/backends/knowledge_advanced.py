"""In-memory backends for Phase 4 advanced knowledge graph protocols.

Classes
-------
InMemoryTemporalKnowledgeStore  -- TemporalKnowledgeStore protocol
InMemoryGraphRetriever          -- GraphRetriever protocol
InMemoryExternalGraphAdapter    -- ExternalGraphAdapter protocol
InMemoryBeliefManager           -- BeliefManager protocol
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loom_ai.models_phase4 import (
    Claim,
    CommunitySummary,
    Consensus,
    Contradiction,
    Evidence,
    ExternalEntity,
    ExternalRelationship,
    GraphRetrievalResult,
    ImportMapping,
    ImportResult,
    KnowledgeEntity,
    KnowledgeRelationship,
    ModelAssertion,
    SubgraphResult,
    TemporalScope,
)

if TYPE_CHECKING:
    from loom_ai.contracts_phase4 import KnowledgeGraph


# ── InMemoryTemporalKnowledgeStore ──────────────────────────────────────


class InMemoryTemporalKnowledgeStore:
    """Dict-backed temporal knowledge store with validity-window filtering."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}
        self._relationships: dict[str, KnowledgeRelationship] = {}
        self._supersessions: dict[str, str] = {}

    # -- non-protocol helpers for populating the store --------------------

    async def add_claim(self, claim: Claim) -> str:
        """Persist a claim and return its id."""
        cid = claim.id or str(uuid.uuid4())
        stored = replace(claim, id=cid)
        self._claims[cid] = stored
        return cid

    async def add_relationship(self, relationship: KnowledgeRelationship) -> str:
        """Persist a relationship and return its id."""
        rid = relationship.id or str(uuid.uuid4())
        stored = replace(relationship, id=rid)
        self._relationships[rid] = stored
        return rid

    # -- private helpers --------------------------------------------------

    def _claim_valid_at(self, claim: Claim, timestamp: str) -> bool:
        if claim.temporal is None:
            return True
        if claim.temporal.retracted:
            return False
        if claim.temporal.valid_from and timestamp < claim.temporal.valid_from:
            return False
        if claim.temporal.valid_until and timestamp > claim.temporal.valid_until:
            return False
        return True

    def _rel_valid_at(self, rel: KnowledgeRelationship, timestamp: str) -> bool:
        if rel.temporal is None:
            return True
        if rel.temporal.retracted:
            return False
        if rel.temporal.valid_from and timestamp < rel.temporal.valid_from:
            return False
        if rel.temporal.valid_until and timestamp > rel.temporal.valid_until:
            return False
        return True

    # -- TemporalKnowledgeStore protocol methods --------------------------

    async def get_claims_at(
        self,
        entity_id: str,
        *,
        timestamp: str,
        predicate: str | None = None,
    ) -> list[Claim]:
        """Return claims valid at *timestamp* for an entity."""
        results: list[Claim] = []
        for claim in self._claims.values():
            if claim.subject_id != entity_id:
                continue
            if predicate is not None and claim.predicate != predicate:
                continue
            if self._claim_valid_at(claim, timestamp):
                results.append(claim)
        return results

    async def get_relationships_at(
        self,
        entity_id: str,
        *,
        timestamp: str,
        relation_type: str | None = None,
    ) -> list[KnowledgeRelationship]:
        """Return relationships valid at *timestamp* for an entity."""
        results: list[KnowledgeRelationship] = []
        for rel in self._relationships.values():
            if rel.source_id != entity_id and rel.target_id != entity_id:
                continue
            if relation_type is not None and rel.relation_type != relation_type:
                continue
            if self._rel_valid_at(rel, timestamp):
                results.append(rel)
        return results

    async def supersede_claim(self, claim_id: str, new_claim: Claim) -> str:
        """Mark *claim_id* as superseded and persist *new_claim*."""
        old = self._claims.get(claim_id)
        if old is None:
            raise KeyError(f"Claim {claim_id} not found; cannot supersede.")

        new_id = new_claim.id or str(uuid.uuid4())
        stored = replace(new_claim, id=new_id)

        now = datetime.now(timezone.utc).isoformat()
        temporal = old.temporal or TemporalScope()
        if not temporal.valid_until or temporal.valid_until > now:
            temporal = replace(temporal, valid_until=now)
        temporal = replace(temporal, superseded_by=new_id)
        self._claims[claim_id] = replace(old, temporal=temporal)
        self._supersessions[claim_id] = new_id

        self._claims[new_id] = stored
        return new_id

    async def retract_claim(self, claim_id: str) -> None:
        """Mark a claim as retracted without deleting it."""
        claim = self._claims.get(claim_id)
        if claim is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        temporal = claim.temporal or TemporalScope()
        temporal = replace(temporal, retracted=True, retracted_at=now)
        self._claims[claim_id] = replace(claim, temporal=temporal)

    async def claim_history(self, claim_id: str) -> list[Claim]:
        """Return the full supersession chain, earliest to most recent."""
        reverse_map: dict[str, str] = {v: k for k, v in self._supersessions.items()}

        seen: set[str] = set()
        root = claim_id
        while root in reverse_map:
            if root in seen:
                break
            seen.add(root)
            root = reverse_map[root]

        chain: list[Claim] = []
        current: str | None = root
        seen.clear()
        while current is not None:
            if current in seen:
                break
            seen.add(current)
            claim = self._claims.get(current)
            if claim is not None:
                chain.append(claim)
            current = self._supersessions.get(current)
        return chain

    async def entity_timeline(
        self,
        entity_id: str,
        *,
        start: str = "",
        end: str = "",
    ) -> list[Claim]:
        """Return all claims about an entity within a time window."""
        results = [
            c
            for c in self._claims.values()
            if c.subject_id == entity_id and self._in_window(c, start, end)
        ]
        results.sort(key=lambda c: (c.temporal.valid_from if c.temporal else "") or "")
        return results

    @staticmethod
    def _in_window(claim: Claim, start: str, end: str) -> bool:
        vf = (claim.temporal.valid_from if claim.temporal else "") or ""
        vu = (claim.temporal.valid_until if claim.temporal else "") or ""
        if end and vf and vf > end:
            return False
        if start and vu and vu < start:
            return False
        return True


# ── InMemoryGraphRetriever ──────────────────────────────────────────────


class InMemoryGraphRetriever:
    """Graph-enhanced retriever backed by an injected KnowledgeGraph."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self._graph = graph

    async def retrieve(
        self,
        query: str,
        *,
        mode: str = "hybrid",
        limit: int = 10,
    ) -> list[GraphRetrievalResult]:
        """Retrieve knowledge relevant to *query*."""
        entities = await self._graph.search_entities(query, limit=limit)
        results: list[GraphRetrievalResult] = []
        for i, entity in enumerate(entities):
            results.append(
                GraphRetrievalResult(
                    content=entity.label,
                    score=1.0 / (1 + i),
                    source="knowledge_graph",
                    entity_ids=[entity.id],
                    metadata={"mode": mode},
                )
            )
        return results

    async def retrieve_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        limit: int = 20,
    ) -> SubgraphResult:
        """Return the neighborhood subgraph around an entity."""
        entities: list[KnowledgeEntity] = []
        relationships: list[KnowledgeRelationship] = []
        seen_rels: set[str] = set()
        visited: set[str] = {entity_id}
        queue: deque[tuple[str, int]] = deque([(entity_id, 0)])

        root = await self._graph.get_entity(entity_id)
        if root is not None:
            entities.append(root)

        while queue and len(entities) < limit:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            rels = await self._graph.get_relationships(current, direction="both")
            await self._collect_neighbors(
                rels,
                current,
                current_depth,
                entities,
                relationships,
                seen_rels,
                visited,
                queue,
                limit,
            )

        return SubgraphResult(entities=entities, relationships=relationships)

    async def _collect_neighbors(
        self,
        rels: list[KnowledgeRelationship],
        current: str,
        current_depth: int,
        entities: list[KnowledgeEntity],
        relationships: list[KnowledgeRelationship],
        seen_rels: set[str],
        visited: set[str],
        queue: deque[tuple[str, int]],
        limit: int,
    ) -> None:
        for rel in rels:
            if rel.id not in seen_rels:
                seen_rels.add(rel.id)
                relationships.append(rel)
            neighbor_id = rel.target_id if rel.source_id == current else rel.source_id
            if neighbor_id not in visited:
                visited.add(neighbor_id)
                entity = await self._graph.get_entity(neighbor_id)
                if entity is not None:
                    entities.append(entity)
                    if len(entities) >= limit:
                        return
                queue.append((neighbor_id, current_depth + 1))

    async def retrieve_path(
        self,
        source_id: str,
        target_id: str,
        *,
        max_depth: int = 5,
    ) -> SubgraphResult:
        """Find a path between two entities and return the subgraph."""
        if source_id == target_id:
            entity = await self._graph.get_entity(source_id)
            return SubgraphResult(
                entities=[entity] if entity else [],
                relationships=[],
            )

        visited: set[str] = {source_id}
        parent: dict[str, tuple[str, KnowledgeRelationship]] = {}
        queue: deque[tuple[str, int]] = deque([(source_id, 0)])
        found = False

        while queue and not found:
            current, current_depth = queue.popleft()
            if current_depth >= max_depth:
                continue

            rels = await self._graph.get_relationships(current, direction="both")
            for rel in rels:
                neighbor_id = (
                    rel.target_id if rel.source_id == current else rel.source_id
                )
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    parent[neighbor_id] = (current, rel)
                    if neighbor_id == target_id:
                        found = True
                        break
                    queue.append((neighbor_id, current_depth + 1))

        if not found:
            return SubgraphResult()

        path_ids: list[str] = [target_id]
        path_rels: list[KnowledgeRelationship] = []
        current_id = target_id
        while current_id in parent:
            prev_id, rel = parent[current_id]
            path_ids.append(prev_id)
            path_rels.append(rel)
            current_id = prev_id
        path_ids.reverse()
        path_rels.reverse()

        entities: list[KnowledgeEntity] = []
        for eid in path_ids:
            entity = await self._graph.get_entity(eid)
            if entity is not None:
                entities.append(entity)

        return SubgraphResult(entities=entities, relationships=path_rels)

    async def retrieve_subgraph(
        self,
        entity_ids: list[str],
        *,
        include_relationships: bool = True,
    ) -> SubgraphResult:
        """Extract the subgraph induced by the given entity ids."""
        entities: list[KnowledgeEntity] = []
        for eid in entity_ids:
            entity = await self._graph.get_entity(eid)
            if entity is not None:
                entities.append(entity)

        relationships: list[KnowledgeRelationship] = []
        if include_relationships:
            id_set = set(entity_ids)
            seen_rels: set[str] = set()
            for eid in entity_ids:
                rels = await self._graph.get_relationships(eid, direction="outgoing")
                for rel in rels:
                    if rel.target_id in id_set and rel.id not in seen_rels:
                        seen_rels.add(rel.id)
                        relationships.append(rel)

        return SubgraphResult(entities=entities, relationships=relationships)

    async def community_summaries(self, *, limit: int = 10) -> list[CommunitySummary]:
        """Return summaries for detected graph communities."""
        all_summaries: list[CommunitySummary] = []
        return all_summaries[:limit]


# ── InMemoryExternalGraphAdapter ────────────────────────────────────────


class InMemoryExternalGraphAdapter:
    """Adapter that maps external entities into an injected KnowledgeGraph."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self._graph = graph
        self._mappings: dict[str, ImportMapping] = {}
        # (source_system, external_id) -> internal_id
        self._entity_map: dict[tuple[str, str], str] = {}
        self._rel_map: dict[tuple[str, str], str] = {}
        self._sources: set[str] = set()

    def _apply_entity_mapping(
        self,
        ext: ExternalEntity,
        mapping: ImportMapping | None,
    ) -> tuple[str, dict]:
        """Return mapped (entity_type, properties)."""
        m = mapping or self._mappings.get(ext.source_system)
        entity_type = ext.entity_type
        props = dict(ext.properties)
        if m is not None:
            entity_type = m.entity_type_map.get(entity_type, entity_type)
            props = {m.property_map.get(k, k): v for k, v in props.items()}
        return entity_type, props

    def _apply_rel_mapping(
        self,
        ext: ExternalRelationship,
        mapping: ImportMapping | None,
    ) -> tuple[str, dict]:
        """Return mapped (relation_type, properties)."""
        m = mapping or self._mappings.get(ext.source_system)
        rel_type = ext.relation_type
        props = dict(ext.properties)
        if m is not None:
            rel_type = m.relation_type_map.get(rel_type, rel_type)
            props = {m.property_map.get(k, k): v for k, v in props.items()}
        return rel_type, props

    async def import_entities(
        self,
        entities: list[ExternalEntity],
        *,
        mapping: ImportMapping | None = None,
    ) -> ImportResult:
        """Import external entities into the knowledge graph."""
        imported = 0
        updated = 0
        errors: list[str] = []
        source_system = ""

        for ext in entities:
            source_system = ext.source_system
            self._sources.add(ext.source_system)
            entity_type, props = self._apply_entity_mapping(ext, mapping)

            key = (ext.source_system, ext.external_id)
            existing_id = self._entity_map.get(key)
            meta = {
                **ext.metadata,
                "source_system": ext.source_system,
                "external_id": ext.external_id,
            }

            if existing_id is not None:
                await self._graph.update_entity(
                    existing_id,
                    properties=props,
                    metadata=meta,
                )
                updated += 1
            else:
                entity = KnowledgeEntity(
                    id=str(uuid.uuid4()),
                    label=ext.label,
                    entity_type=entity_type,
                    properties=props,
                    metadata=meta,
                )
                eid = await self._graph.add_entity(entity)
                self._entity_map[key] = eid
                imported += 1

        return ImportResult(
            entities_imported=imported,
            entities_updated=updated,
            errors=errors,
            source_system=source_system,
        )

    async def import_relationships(
        self,
        relationships: list[ExternalRelationship],
        *,
        mapping: ImportMapping | None = None,
    ) -> ImportResult:
        """Import external relationships into the knowledge graph."""
        imported = 0
        updated = 0
        errors: list[str] = []
        source_system = ""

        for ext_rel in relationships:
            source_system = ext_rel.source_system
            self._sources.add(ext_rel.source_system)

            src_key = (ext_rel.source_system, ext_rel.source_entity_id)
            tgt_key = (ext_rel.source_system, ext_rel.target_entity_id)
            src_id = self._entity_map.get(src_key)
            tgt_id = self._entity_map.get(tgt_key)

            if src_id is None or tgt_id is None:
                errors.append(
                    f"Cannot resolve entities for relationship {ext_rel.external_id}"
                )
                continue

            rel_type, props = self._apply_rel_mapping(ext_rel, mapping)
            meta = {
                **ext_rel.metadata,
                "source_system": ext_rel.source_system,
                "external_id": ext_rel.external_id,
            }

            key = (ext_rel.source_system, ext_rel.external_id)
            existing_id = self._rel_map.get(key)

            if existing_id is not None:
                rel = KnowledgeRelationship(
                    id=existing_id,
                    source_id=src_id,
                    target_id=tgt_id,
                    relation_type=rel_type,
                    properties=props,
                    metadata=meta,
                )
                await self._graph.add_relationship(rel)
                updated += 1
            else:
                rel = KnowledgeRelationship(
                    id=str(uuid.uuid4()),
                    source_id=src_id,
                    target_id=tgt_id,
                    relation_type=rel_type,
                    properties=props,
                    metadata=meta,
                )
                rid = await self._graph.add_relationship(rel)
                self._rel_map[key] = rid
                imported += 1

        return ImportResult(
            relationships_imported=imported,
            relationships_updated=updated,
            errors=errors,
            source_system=source_system,
        )

    async def sync(
        self,
        source_system: str,
        *,
        since: str = "",
    ) -> ImportResult:
        """Perform incremental synchronization from *source_system*.

        When *since* is non-empty, only entities imported after that
        ISO-8601 timestamp would be re-synced (no-op for in-memory).
        """
        self._sources.add(source_system)
        entities_imported = 0
        if since:
            for (src, _eid), _iid in self._entity_map.items():
                if src == source_system:
                    entities_imported += 1
        return ImportResult(
            source_system=source_system,
            entities_imported=entities_imported,
        )

    async def list_sources(self) -> list[str]:
        """Return the names of registered external source systems."""
        return sorted(self._sources)

    async def set_mapping(self, mapping: ImportMapping) -> None:
        """Register or update a mapping for a source system."""
        self._mappings[mapping.source_system] = mapping


# ── InMemoryBeliefManager ──────────────────────────────────────────────


class InMemoryBeliefManager:
    """Dict-backed belief, evidence, contradiction, and consensus manager."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}
        self._evidence: dict[str, Evidence] = {}
        self._assertions: dict[str, ModelAssertion] = {}
        self._contradictions: dict[str, Contradiction] = {}

    async def add_claim(self, claim: Claim) -> str:
        """Persist a claim and return its id (non-protocol utility)."""
        cid = claim.id or str(uuid.uuid4())
        stored = replace(claim, id=cid)
        self._claims[cid] = stored
        return cid

    # -- BeliefManager protocol methods -----------------------------------

    async def add_evidence(self, evidence: Evidence) -> str:
        """Attach evidence to a claim and return the evidence id."""
        eid = evidence.id or str(uuid.uuid4())
        stored = replace(evidence, id=eid)
        self._evidence[eid] = stored
        return eid

    async def get_evidence(
        self,
        claim_id: str,
        *,
        evidence_type: str | None = None,
    ) -> list[Evidence]:
        """Return evidence for a claim."""
        results: list[Evidence] = []
        for ev in self._evidence.values():
            if ev.claim_id != claim_id:
                continue
            if evidence_type is not None and ev.evidence_type != evidence_type:
                continue
            results.append(ev)
        return results

    async def add_assertion(self, assertion: ModelAssertion) -> str:
        """Record a model assertion about a claim and return its id."""
        aid = assertion.id or str(uuid.uuid4())
        stored = replace(assertion, id=aid)
        self._assertions[aid] = stored
        return aid

    async def get_assertions(self, claim_id: str) -> list[ModelAssertion]:
        """Return all model assertions for a claim."""
        return [a for a in self._assertions.values() if a.claim_id == claim_id]

    async def detect_contradictions(
        self,
        entity_id: str,
        *,
        predicate: str | None = None,
    ) -> list[Contradiction]:
        """Detect contradictions among claims about an entity."""
        entity_claims = [
            c
            for c in self._claims.values()
            if c.subject_id == entity_id
            and (predicate is None or c.predicate == predicate)
        ]

        by_predicate: dict[str, list[Claim]] = {}
        for claim in entity_claims:
            by_predicate.setdefault(claim.predicate, []).append(claim)

        contradictions: list[Contradiction] = []
        for pred, claims in by_predicate.items():
            value_groups: dict[str, list[Claim]] = {}
            for c in claims:
                value_groups.setdefault(c.object_value, []).append(c)

            if len(value_groups) < 2:
                continue

            claim_ids = [c.id for c in claims]
            claim_id_set = frozenset(claim_ids)

            # Reuse an existing unresolved contradiction for the same claims.
            existing = next(
                (
                    c
                    for c in self._contradictions.values()
                    if frozenset(c.claim_ids) == claim_id_set and not c.resolved
                ),
                None,
            )
            if existing is not None:
                contradictions.append(existing)
                continue

            max_group = max(len(v) for v in value_groups.values())
            values = list(value_groups.keys())
            contradiction = Contradiction(
                id=str(uuid.uuid4()),
                claim_ids=claim_ids,
                description=f"Conflicting values for '{pred}': {values}",
                severity=1.0 - (max_group / len(claims)),
            )
            self._contradictions[contradiction.id] = contradiction
            contradictions.append(contradiction)

        return contradictions

    async def resolve_contradiction(
        self, contradiction_id: str, *, resolution: str
    ) -> None:
        """Mark a contradiction as resolved with an explanation."""
        contradiction = self._contradictions.get(contradiction_id)
        if contradiction is not None:
            contradiction.resolved = True
            contradiction.resolution = resolution

    async def compute_consensus(self, claim_id: str) -> Consensus:
        """Derive consensus from model assertions for a claim."""
        assertions = [a for a in self._assertions.values() if a.claim_id == claim_id]

        if not assertions:
            return Consensus(
                id=str(uuid.uuid4()),
                claim_id=claim_id,
                status="uncertain",
            )

        supporting = sum(1 for a in assertions if a.confidence >= 0.5)
        ratio = supporting / len(assertions)
        avg_confidence = sum(a.confidence for a in assertions) / len(assertions)

        if ratio >= 0.8:
            status = "agreed"
        elif ratio <= 0.3:
            status = "disputed"
        else:
            status = "uncertain"

        return Consensus(
            id=str(uuid.uuid4()),
            claim_id=claim_id,
            assertion_ids=[a.id for a in assertions],
            agreement_ratio=ratio,
            confidence=avg_confidence,
            status=status,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    async def update_confidence(
        self,
        claim_id: str,
        *,
        new_confidence: float,
        reason: str = "",
    ) -> None:
        """Update the confidence score on a claim."""
        claim = self._claims.get(claim_id)
        if claim is not None:
            claim.confidence = new_confidence
            if reason:
                claim.metadata["confidence_reason"] = reason
