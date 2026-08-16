"""Protocol conformance tests for Phase 4 knowledge graph contracts.

Verifies that concrete stub implementations satisfy each protocol via
``isinstance`` checks (enabled by ``@runtime_checkable``), and that
the data models can be constructed with expected defaults.
"""

from __future__ import annotations

from loom_ai.contracts_phase4 import (
    BeliefManager,
    ExternalGraphAdapter,
    GraphRetriever,
    KnowledgeGraph,
    TemporalKnowledgeStore,
)
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
    Provenance,
    SubgraphResult,
    TemporalScope,
)

# ── Stub implementations ───────────────────────────────────────────────


class StubKnowledgeGraph:
    """Minimal stub satisfying the KnowledgeGraph protocol."""

    async def add_entity(self, entity):
        return entity.id

    async def get_entity(self, entity_id):
        return None

    async def update_entity(self, entity_id, *, properties=None, metadata=None):
        pass

    async def delete_entity(self, entity_id):
        return False

    async def add_relationship(self, relationship):
        return relationship.id

    async def get_relationships(
        self, entity_id, *, relation_type=None, direction="outgoing"
    ):
        return []

    async def delete_relationship(self, relationship_id):
        return False

    async def add_claim(self, claim):
        return claim.id

    async def get_claims(self, entity_id, *, predicate=None):
        return []

    async def search_entities(self, query, *, entity_type=None, limit=10):
        return []


class StubTemporalKnowledgeStore:
    """Minimal stub satisfying the TemporalKnowledgeStore protocol."""

    async def get_claims_at(self, entity_id, *, timestamp, predicate=None):
        return []

    async def get_relationships_at(self, entity_id, *, timestamp, relation_type=None):
        return []

    async def supersede_claim(self, claim_id, new_claim):
        return new_claim.id

    async def retract_claim(self, claim_id):
        pass

    async def claim_history(self, claim_id):
        return []

    async def entity_timeline(self, entity_id, *, start="", end=""):
        return []


class StubGraphRetriever:
    """Minimal stub satisfying the GraphRetriever protocol."""

    async def retrieve(self, query, *, mode="hybrid", limit=10):
        return []

    async def retrieve_neighborhood(self, entity_id, *, depth=1, limit=20):
        return SubgraphResult()

    async def retrieve_path(self, source_id, target_id, *, max_depth=5):
        return SubgraphResult()

    async def retrieve_subgraph(self, entity_ids, *, include_relationships=True):
        return SubgraphResult()

    async def community_summaries(self, *, limit=10):
        return []


class StubExternalGraphAdapter:
    """Minimal stub satisfying the ExternalGraphAdapter protocol."""

    async def import_entities(self, entities, *, mapping=None):
        return ImportResult(entities_imported=len(entities))

    async def import_relationships(self, relationships, *, mapping=None):
        return ImportResult(relationships_imported=len(relationships))

    async def sync(self, source_system, *, since=""):
        return ImportResult(source_system=source_system)

    async def list_sources(self):
        return []

    async def set_mapping(self, mapping):
        pass


class StubBeliefManager:
    """Minimal stub satisfying the BeliefManager protocol."""

    async def add_evidence(self, evidence):
        return evidence.id

    async def get_evidence(self, claim_id, *, evidence_type=None):
        return []

    async def add_assertion(self, assertion):
        return assertion.id

    async def get_assertions(self, claim_id):
        return []

    async def detect_contradictions(self, entity_id, *, predicate=None):
        return []

    async def resolve_contradiction(self, contradiction_id, *, resolution):
        pass

    async def compute_consensus(self, claim_id):
        return Consensus(id="c-1", claim_id=claim_id, status="uncertain")

    async def update_confidence(self, claim_id, *, new_confidence, reason=""):
        pass


# ── Protocol conformance tests ─────────────────────────────────────────


def test_knowledge_graph_conformance():
    """StubKnowledgeGraph satisfies the KnowledgeGraph protocol."""
    assert isinstance(StubKnowledgeGraph(), KnowledgeGraph)


def test_temporal_knowledge_store_conformance():
    """StubTemporalKnowledgeStore satisfies the TemporalKnowledgeStore protocol."""
    assert isinstance(StubTemporalKnowledgeStore(), TemporalKnowledgeStore)


def test_graph_retriever_conformance():
    """StubGraphRetriever satisfies the GraphRetriever protocol."""
    assert isinstance(StubGraphRetriever(), GraphRetriever)


def test_external_graph_adapter_conformance():
    """StubExternalGraphAdapter satisfies the ExternalGraphAdapter protocol."""
    assert isinstance(StubExternalGraphAdapter(), ExternalGraphAdapter)


def test_belief_manager_conformance():
    """StubBeliefManager satisfies the BeliefManager protocol."""
    assert isinstance(StubBeliefManager(), BeliefManager)


# ── Dataclass construction tests ───────────────────────────────────────


def test_knowledge_entity_defaults():
    """KnowledgeEntity has expected default values."""
    entity = KnowledgeEntity(id="e-1", label="Python", entity_type="language")
    assert entity.id == "e-1"
    assert entity.label == "Python"
    assert entity.entity_type == "language"
    assert entity.properties == {}
    assert entity.metadata == {}
    assert entity.created_at == ""
    assert entity.updated_at == ""


def test_knowledge_relationship_defaults():
    """KnowledgeRelationship has expected default values."""
    rel = KnowledgeRelationship(
        id="r-1", source_id="e-1", target_id="e-2", relation_type="uses"
    )
    assert rel.source_id == "e-1"
    assert rel.target_id == "e-2"
    assert rel.confidence == 1.0
    assert rel.provenance is None
    assert rel.temporal is None


def test_provenance_construction():
    """Provenance can be constructed with required and optional fields."""
    prov = Provenance(source="arxiv:2401.1234", source_type="document")
    assert prov.source == "arxiv:2401.1234"
    assert prov.model == ""
    assert prov.metadata == {}


def test_temporal_scope_defaults():
    """TemporalScope starts with empty/false defaults."""
    ts = TemporalScope()
    assert ts.valid_from == ""
    assert ts.valid_until == ""
    assert ts.superseded_by is None
    assert ts.retracted is False


def test_claim_defaults():
    """Claim has expected default values."""
    claim = Claim(
        id="cl-1",
        subject_id="e-1",
        predicate="has_version",
        object_value="3.12",
    )
    assert claim.confidence == 1.0
    assert claim.object_id is None
    assert claim.provenance is None
    assert claim.temporal is None


def test_claim_with_provenance_and_temporal():
    """Claim can carry provenance and temporal scope."""
    prov = Provenance(source="model-output", source_type="model", model="gpt-4o")
    ts = TemporalScope(valid_from="2024-01-01", observed_at="2024-06-15")
    claim = Claim(
        id="cl-2",
        subject_id="e-1",
        predicate="is_maintained",
        object_value="true",
        confidence=0.9,
        provenance=prov,
        temporal=ts,
    )
    assert claim.provenance is not None
    assert claim.provenance.model == "gpt-4o"
    assert claim.temporal is not None
    assert claim.temporal.valid_from == "2024-01-01"


def test_evidence_construction():
    """Evidence can be constructed for supporting and contradicting types."""
    ev = Evidence(
        id="ev-1",
        claim_id="cl-1",
        content="Release notes confirm version 3.12",
        evidence_type="supporting",
        confidence=0.95,
    )
    assert ev.evidence_type == "supporting"
    assert ev.confidence == 0.95


def test_model_assertion_construction():
    """ModelAssertion captures a model's stance on a claim."""
    assertion = ModelAssertion(
        id="ma-1",
        claim_id="cl-1",
        model="claude-opus-4-6",
        confidence=0.85,
        reasoning="Based on official documentation",
    )
    assert assertion.model == "claude-opus-4-6"
    assert assertion.confidence == 0.85


def test_contradiction_defaults():
    """Contradiction starts unresolved with empty defaults."""
    c = Contradiction(id="ctr-1", claim_ids=["cl-1", "cl-2"])
    assert c.resolved is False
    assert c.resolution == ""
    assert c.severity == 0.0


def test_consensus_defaults():
    """Consensus starts with zero agreement."""
    con = Consensus(id="con-1", claim_id="cl-1")
    assert con.agreement_ratio == 0.0
    assert con.confidence == 0.0
    assert con.status == ""
    assert con.assertion_ids == []


def test_graph_retrieval_result_defaults():
    """GraphRetrievalResult has expected defaults."""
    r = GraphRetrievalResult(content="Python is...", score=0.92, source="wiki")
    assert r.entity_ids == []
    assert r.path == []
    assert r.provenance is None


def test_subgraph_result_defaults():
    """SubgraphResult starts empty."""
    sg = SubgraphResult()
    assert sg.entities == []
    assert sg.relationships == []
    assert sg.summary == ""


def test_community_summary_construction():
    """CommunitySummary captures cluster metadata."""
    cs = CommunitySummary(
        id="com-1",
        name="ML Frameworks",
        summary="Cluster of machine learning libraries",
        entity_count=15,
    )
    assert cs.entity_count == 15
    assert cs.entity_ids == []


def test_external_entity_construction():
    """ExternalEntity preserves source system identity."""
    ee = ExternalEntity(
        external_id="graphify:fn:main",
        source_system="graphify",
        entity_type="function",
        label="main",
    )
    assert ee.source_system == "graphify"
    assert ee.external_id == "graphify:fn:main"


def test_external_relationship_construction():
    """ExternalRelationship preserves external identifiers."""
    er = ExternalRelationship(
        external_id="graphify:rel:1",
        source_system="graphify",
        source_entity_id="graphify:fn:main",
        target_entity_id="graphify:fn:helper",
        relation_type="calls",
    )
    assert er.relation_type == "calls"


def test_import_result_defaults():
    """ImportResult starts at zero counts."""
    ir = ImportResult()
    assert ir.entities_imported == 0
    assert ir.relationships_imported == 0
    assert ir.entities_updated == 0
    assert ir.errors == []


def test_import_mapping_construction():
    """ImportMapping captures schema translation rules."""
    mapping = ImportMapping(
        source_system="graphify",
        entity_type_map={"function": "code_function", "class": "code_class"},
        relation_type_map={"calls": "invokes"},
    )
    assert mapping.source_system == "graphify"
    assert mapping.entity_type_map["function"] == "code_function"


# ── Async stub behavior tests ─────────────────────────────────────────


async def test_knowledge_graph_add_entity():
    """KnowledgeGraph stub returns entity id on add."""
    kg = StubKnowledgeGraph()
    entity = KnowledgeEntity(id="e-1", label="Test", entity_type="concept")
    result = await kg.add_entity(entity)
    assert result == "e-1"


async def test_knowledge_graph_get_entity_returns_none():
    """KnowledgeGraph stub returns None for missing entity."""
    kg = StubKnowledgeGraph()
    result = await kg.get_entity("nonexistent")
    assert result is None


async def test_temporal_store_get_claims_at():
    """TemporalKnowledgeStore returns empty list for point-in-time query."""
    store = StubTemporalKnowledgeStore()
    claims = await store.get_claims_at("e-1", timestamp="2024-01-01")
    assert claims == []


async def test_temporal_store_supersede_claim():
    """TemporalKnowledgeStore supersede returns new claim id."""
    store = StubTemporalKnowledgeStore()
    new_claim = Claim(
        id="cl-new", subject_id="e-1", predicate="version", object_value="4.0"
    )
    result = await store.supersede_claim("cl-old", new_claim)
    assert result == "cl-new"


async def test_graph_retriever_retrieve():
    """GraphRetriever returns empty results for stub."""
    retriever = StubGraphRetriever()
    results = await retriever.retrieve("test query")
    assert results == []


async def test_graph_retriever_neighborhood():
    """GraphRetriever neighborhood returns empty subgraph."""
    retriever = StubGraphRetriever()
    sg = await retriever.retrieve_neighborhood("e-1")
    assert isinstance(sg, SubgraphResult)
    assert sg.entities == []


async def test_external_adapter_import_entities():
    """ExternalGraphAdapter counts imported entities."""
    adapter = StubExternalGraphAdapter()
    entities = [
        ExternalEntity(
            external_id="ext-1",
            source_system="test",
            entity_type="node",
            label="A",
        ),
        ExternalEntity(
            external_id="ext-2",
            source_system="test",
            entity_type="node",
            label="B",
        ),
    ]
    result = await adapter.import_entities(entities)
    assert result.entities_imported == 2


async def test_external_adapter_list_sources():
    """ExternalGraphAdapter stub returns empty source list."""
    adapter = StubExternalGraphAdapter()
    sources = await adapter.list_sources()
    assert sources == []


async def test_belief_manager_add_evidence():
    """BeliefManager stub returns evidence id."""
    bm = StubBeliefManager()
    ev = Evidence(
        id="ev-1",
        claim_id="cl-1",
        content="supporting text",
        evidence_type="supporting",
    )
    result = await bm.add_evidence(ev)
    assert result == "ev-1"


async def test_belief_manager_compute_consensus():
    """BeliefManager stub returns uncertain consensus."""
    bm = StubBeliefManager()
    consensus = await bm.compute_consensus("cl-1")
    assert isinstance(consensus, Consensus)
    assert consensus.claim_id == "cl-1"
    assert consensus.status == "uncertain"


async def test_belief_manager_detect_contradictions():
    """BeliefManager stub returns empty contradiction list."""
    bm = StubBeliefManager()
    contradictions = await bm.detect_contradictions("e-1")
    assert contradictions == []
