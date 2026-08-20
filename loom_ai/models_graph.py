"""Phase 4 data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  Phase 4 protocols reference these types for their method
signatures.

Phase 4 covers the Knowledge Graph domain:

- **KnowledgeEntity / KnowledgeRelationship** -- graph nodes and edges (#46)
- **Provenance** -- source attribution and lineage (#46)
- **TemporalScope** -- temporal validity semantics (#47)
- **Claim / Evidence / ModelAssertion** -- factual assertions (#46, #50)
- **Contradiction / Consensus** -- competing claims and agreement (#50)
- **GraphRetrievalResult / SubgraphResult / CommunitySummary** -- retrieval (#48)
- **ExternalEntity / ExternalRelationship / ImportResult** -- ingestion (#49)
- **ImportMapping** -- schema mapping for external graphs (#49)
"""

from __future__ import annotations

from dataclasses import dataclass, field

# -- Core knowledge graph entities (#46) -------------------------------------


@dataclass
class Provenance:
    """Source attribution and lineage for a knowledge artifact."""

    source: str
    source_type: str
    model: str = ""
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class TemporalScope:
    """Temporal validity window for a knowledge artifact.

    ``valid_from`` / ``valid_until`` denote when the fact is believed
    to be true.  ``observed_at`` records when it was first observed.
    """

    valid_from: str = ""
    valid_until: str = ""
    observed_at: str = ""
    superseded_by: str | None = None
    retracted: bool = False
    retracted_at: str = ""


@dataclass
class KnowledgeEntity:
    """A node in the knowledge graph representing a concept, thing, or agent."""

    id: str
    label: str
    entity_type: str
    properties: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class KnowledgeRelationship:
    """A directed edge between two entities in the knowledge graph."""

    id: str
    source_id: str
    target_id: str
    relation_type: str
    properties: dict = field(default_factory=dict)
    confidence: float = 1.0
    provenance: Provenance | None = None
    temporal: TemporalScope | None = None
    metadata: dict = field(default_factory=dict)
    created_at: str = ""


# -- Claims, evidence, and belief (#46, #50) ---------------------------------


@dataclass
class Claim:
    """A factual assertion in the knowledge graph.

    A claim relates a *subject* entity to either a literal value
    (``object_value``) or another entity (``object_id``) via a
    *predicate*.
    """

    id: str
    subject_id: str
    predicate: str
    object_value: str
    object_id: str | None = None
    confidence: float = 1.0
    provenance: Provenance | None = None
    temporal: TemporalScope | None = None
    metadata: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class Evidence:
    """A piece of evidence supporting or contradicting a claim."""

    id: str
    claim_id: str
    content: str
    evidence_type: str
    source: str = ""
    confidence: float = 1.0
    provenance: Provenance | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ModelAssertion:
    """An assertion produced by a specific LLM model about a claim."""

    id: str
    claim_id: str
    model: str
    confidence: float
    reasoning: str = ""
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class Contradiction:
    """A detected contradiction between two or more claims."""

    id: str
    claim_ids: list[str] = field(default_factory=list)
    description: str = ""
    severity: float = 0.0
    resolved: bool = False
    resolution: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class Consensus:
    """Multi-model consensus on a claim.

    ``status`` is one of ``"agreed"``, ``"disputed"``, or ``"uncertain"``.
    """

    id: str
    claim_id: str
    assertion_ids: list[str] = field(default_factory=list)
    agreement_ratio: float = 0.0
    confidence: float = 0.0
    status: str = ""
    metadata: dict = field(default_factory=dict)
    updated_at: str = ""


# -- Graph retrieval (#48) ---------------------------------------------------


@dataclass
class GraphRetrievalResult:
    """A single result from graph-enhanced retrieval."""

    content: str
    score: float
    source: str
    entity_ids: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)
    provenance: Provenance | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SubgraphResult:
    """A subgraph extracted from the knowledge graph."""

    entities: list[KnowledgeEntity] = field(default_factory=list)
    relationships: list[KnowledgeRelationship] = field(default_factory=list)
    summary: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class CommunitySummary:
    """Summary of a community or cluster within the knowledge graph."""

    id: str
    name: str
    summary: str
    entity_count: int = 0
    entity_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# -- External graph ingestion (#49) ------------------------------------------


@dataclass
class ExternalEntity:
    """An entity from an external graph system awaiting import."""

    external_id: str
    source_system: str
    entity_type: str
    label: str
    properties: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class ExternalRelationship:
    """A relationship from an external graph system awaiting import."""

    external_id: str
    source_system: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    properties: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class ImportResult:
    """Outcome of an external graph import operation."""

    entities_imported: int = 0
    relationships_imported: int = 0
    entities_updated: int = 0
    relationships_updated: int = 0
    errors: list[str] = field(default_factory=list)
    source_system: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ImportMapping:
    """Mapping rules from an external graph schema to the Loom knowledge model."""

    source_system: str
    entity_type_map: dict = field(default_factory=dict)
    relation_type_map: dict = field(default_factory=dict)
    property_map: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
