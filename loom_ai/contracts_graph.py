"""Phase 4 protocol contracts for loom-ai -- Knowledge Graph.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required.  All methods are
async.  Nothing outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.

Phase 4 covers five contract areas:

- **KnowledgeGraph** -- core knowledge graph operations (#46)
- **TemporalKnowledgeStore** -- temporal validity and historical queries (#47)
- **GraphRetriever** -- GraphRAG and hybrid knowledge retrieval (#48)
- **ExternalGraphAdapter** -- external graph and code graph ingestion (#49)
- **BeliefManager** -- belief, evidence, contradiction, and consensus (#50)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.models_graph import (
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
    )


# -- Knowledge Graph (#46) --------------------------------------------------


@runtime_checkable
class KnowledgeGraph(Protocol):
    """Core knowledge graph operations.

    Provides storage-independent access to entities, relationships,
    and claims with first-class provenance and confidence semantics.
    """

    async def add_entity(self, entity: KnowledgeEntity) -> str:
        """Persist an entity and return its id."""
        ...

    async def get_entity(self, entity_id: str) -> KnowledgeEntity | None:
        """Return an entity by id, or ``None`` if not found."""
        ...

    async def update_entity(
        self,
        entity_id: str,
        *,
        properties: dict | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Update properties and/or metadata on an existing entity."""
        ...

    async def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity and its incident relationships."""
        ...

    async def add_relationship(self, relationship: KnowledgeRelationship) -> str:
        """Persist a relationship and return its id."""
        ...

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
        ...

    async def delete_relationship(self, relationship_id: str) -> bool:
        """Delete a relationship by id."""
        ...

    async def add_claim(self, claim: Claim) -> str:
        """Persist a claim and return its id."""
        ...

    async def get_claims(
        self,
        entity_id: str,
        *,
        predicate: str | None = None,
    ) -> list[Claim]:
        """Return claims about an entity, optionally filtered by predicate."""
        ...

    async def search_entities(
        self,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> list[KnowledgeEntity]:
        """Search entities by label or property values."""
        ...


# -- Temporal Knowledge Store (#47) -----------------------------------------


@runtime_checkable
class TemporalKnowledgeStore(Protocol):
    """Temporal semantics for knowledge artifacts.

    Manages valid-from / valid-until windows, supersession, retraction,
    and point-in-time historical queries.
    """

    async def get_claims_at(
        self,
        entity_id: str,
        *,
        timestamp: str,
        predicate: str | None = None,
    ) -> list[Claim]:
        """Return claims valid at *timestamp* for an entity."""
        ...

    async def get_relationships_at(
        self,
        entity_id: str,
        *,
        timestamp: str,
        relation_type: str | None = None,
    ) -> list[KnowledgeRelationship]:
        """Return relationships valid at *timestamp* for an entity."""
        ...

    async def supersede_claim(self, claim_id: str, new_claim: Claim) -> str:
        """Mark *claim_id* as superseded and persist *new_claim*.

        Returns the new claim's id.
        """
        ...

    async def retract_claim(self, claim_id: str) -> None:
        """Mark a claim as retracted without deleting it."""
        ...

    async def claim_history(self, claim_id: str) -> list[Claim]:
        """Return the full supersession chain for a claim.

        Results are ordered from earliest to most recent.
        """
        ...

    async def entity_timeline(
        self,
        entity_id: str,
        *,
        start: str = "",
        end: str = "",
    ) -> list[Claim]:
        """Return all claims about an entity within a time window.

        If *start* or *end* are empty the boundary is open.
        """
        ...


# -- GraphRAG / Hybrid Retrieval (#48) --------------------------------------


@runtime_checkable
class GraphRetriever(Protocol):
    """Graph-enhanced retrieval combining vector, lexical, and graph structure.

    Supports entity-centric lookups, neighborhood expansion, path
    traversal, subgraph extraction, and community summaries.
    """

    async def retrieve(
        self,
        query: str,
        *,
        mode: str = "hybrid",
        limit: int = 10,
    ) -> list[GraphRetrievalResult]:
        """Retrieve knowledge relevant to *query*.

        *mode* is one of ``"local"``, ``"global"``, or ``"hybrid"``.
        """
        ...

    async def retrieve_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        limit: int = 20,
    ) -> SubgraphResult:
        """Return the neighborhood subgraph around an entity."""
        ...

    async def retrieve_path(
        self,
        source_id: str,
        target_id: str,
        *,
        max_depth: int = 5,
    ) -> SubgraphResult:
        """Find a path between two entities and return the subgraph."""
        ...

    async def retrieve_subgraph(
        self,
        entity_ids: list[str],
        *,
        include_relationships: bool = True,
    ) -> SubgraphResult:
        """Extract the subgraph induced by the given entity ids."""
        ...

    async def community_summaries(self, *, limit: int = 10) -> list[CommunitySummary]:
        """Return summaries for detected graph communities."""
        ...


# -- External Graph Ingestion (#49) -----------------------------------------


@runtime_checkable
class ExternalGraphAdapter(Protocol):
    """Adapter for importing external knowledge and code graphs.

    Implementations map external entities and relationships into the
    Loom knowledge model while preserving provenance and supporting
    incremental, idempotent synchronization.
    """

    async def import_entities(
        self,
        entities: list[ExternalEntity],
        *,
        mapping: ImportMapping | None = None,
    ) -> ImportResult:
        """Import external entities into the knowledge graph.

        *mapping* provides optional type and property translation rules.
        The operation is idempotent: re-importing the same external id
        updates rather than duplicates.
        """
        ...

    async def import_relationships(
        self,
        relationships: list[ExternalRelationship],
        *,
        mapping: ImportMapping | None = None,
    ) -> ImportResult:
        """Import external relationships into the knowledge graph."""
        ...

    async def sync(
        self,
        source_system: str,
        *,
        since: str = "",
    ) -> ImportResult:
        """Perform incremental synchronization from *source_system*.

        If *since* is provided, only changes after that timestamp are
        imported.
        """
        ...

    async def list_sources(self) -> list[str]:
        """Return the names of registered external source systems."""
        ...

    async def set_mapping(self, mapping: ImportMapping) -> None:
        """Register or update a mapping for a source system."""
        ...


# -- Belief, Evidence, Contradiction, Consensus (#50) -----------------------


@runtime_checkable
class BeliefManager(Protocol):
    """Manage knowledge claims, evidence, contradictions, and consensus.

    Supports explicit uncertainty: claims carry confidence scores,
    evidence can support or contradict, and consensus is derived from
    multiple model assertions rather than forced into binary truth.
    """

    async def add_evidence(self, evidence: Evidence) -> str:
        """Attach evidence to a claim and return the evidence id."""
        ...

    async def get_evidence(
        self,
        claim_id: str,
        *,
        evidence_type: str | None = None,
    ) -> list[Evidence]:
        """Return evidence for a claim.

        *evidence_type* filters to ``"supporting"`` or ``"contradicting"``.
        """
        ...

    async def add_assertion(self, assertion: ModelAssertion) -> str:
        """Record a model assertion about a claim and return its id."""
        ...

    async def get_assertions(self, claim_id: str) -> list[ModelAssertion]:
        """Return all model assertions for a claim."""
        ...

    async def detect_contradictions(
        self,
        entity_id: str,
        *,
        predicate: str | None = None,
    ) -> list[Contradiction]:
        """Detect contradictions among claims about an entity."""
        ...

    async def resolve_contradiction(
        self, contradiction_id: str, *, resolution: str
    ) -> None:
        """Mark a contradiction as resolved with an explanation."""
        ...

    async def compute_consensus(self, claim_id: str) -> Consensus:
        """Derive consensus from model assertions for a claim.

        Returns a ``Consensus`` object reflecting agreement ratio,
        confidence, and status.
        """
        ...

    async def update_confidence(
        self,
        claim_id: str,
        *,
        new_confidence: float,
        reason: str = "",
    ) -> None:
        """Update the confidence score on a claim as new evidence arrives."""
        ...
