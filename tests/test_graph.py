"""Tests for the in-memory knowledge graph backend."""

from loom_ai.backends.graph import InMemoryKnowledgeGraph, orientdb_available
from loom_ai.contracts_phase4 import KnowledgeGraph
from loom_ai.models_phase4 import (
    Claim,
    KnowledgeEntity,
    KnowledgeRelationship,
    SubgraphResult,
)

# ── Protocol conformance ─────────────────────────────────────────────────


def test_satisfies_knowledge_graph_protocol():
    """InMemoryKnowledgeGraph satisfies the KnowledgeGraph protocol."""
    assert isinstance(InMemoryKnowledgeGraph(), KnowledgeGraph)


# ── OrientDB guard ───────────────────────────────────────────────────────


def test_orientdb_available_returns_bool():
    """orientdb_available returns a bool (likely False in test env)."""
    result = orientdb_available()
    assert isinstance(result, bool)


# ── Entity operations ────────────────────────────────────────────────────


async def test_add_and_get_entity():
    """Adding an entity allows retrieval by id."""
    g = InMemoryKnowledgeGraph()
    entity = KnowledgeEntity(id="e-1", label="Python", entity_type="language")
    eid = await g.add_entity(entity)
    assert eid == "e-1"
    assert g.entity_count == 1

    result = await g.get_entity("e-1")
    assert result is not None
    assert result.label == "Python"
    assert result.entity_type == "language"


async def test_get_missing_entity():
    """Getting a non-existent entity returns None."""
    g = InMemoryKnowledgeGraph()
    assert await g.get_entity("missing") is None


async def test_update_entity_properties():
    """update_entity merges new properties."""
    g = InMemoryKnowledgeGraph()
    entity = KnowledgeEntity(
        id="e-1",
        label="Python",
        entity_type="language",
        properties={"version": "3.12"},
    )
    await g.add_entity(entity)
    await g.update_entity("e-1", properties={"version": "3.13", "typed": True})

    updated = await g.get_entity("e-1")
    assert updated is not None
    assert updated.properties["version"] == "3.13"
    assert updated.properties["typed"] is True


async def test_update_entity_metadata():
    """update_entity merges new metadata."""
    g = InMemoryKnowledgeGraph()
    entity = KnowledgeEntity(id="e-1", label="X", entity_type="t")
    await g.add_entity(entity)
    await g.update_entity("e-1", metadata={"source": "test"})

    updated = await g.get_entity("e-1")
    assert updated is not None
    assert updated.metadata["source"] == "test"


async def test_update_nonexistent_entity():
    """Updating a missing entity is a no-op."""
    g = InMemoryKnowledgeGraph()
    await g.update_entity("missing", properties={"x": 1})
    assert g.entity_count == 0


async def test_delete_entity():
    """Deleting an entity removes it and its relationships."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="A", entity_type="t"))
    await g.add_entity(KnowledgeEntity(id="e-2", label="B", entity_type="t"))
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-1", source_id="e-1", target_id="e-2", relation_type="knows"
        )
    )

    deleted = await g.delete_entity("e-1")
    assert deleted is True
    assert g.entity_count == 1
    assert g.relationship_count == 0
    assert await g.get_entity("e-1") is None


async def test_delete_entity_removes_claims():
    """Deleting an entity removes its claims."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="A", entity_type="t"))
    await g.add_claim(
        Claim(id="c-1", subject_id="e-1", predicate="is", object_value="good")
    )
    assert g.claim_count == 1
    await g.delete_entity("e-1")
    assert g.claim_count == 0


async def test_delete_nonexistent_entity():
    """Deleting a non-existent entity returns False."""
    g = InMemoryKnowledgeGraph()
    assert await g.delete_entity("missing") is False


# ── Relationship operations ──────────────────────────────────────────────


async def test_add_and_get_relationship():
    """Adding a relationship allows retrieval by entity."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="A", entity_type="t"))
    await g.add_entity(KnowledgeEntity(id="e-2", label="B", entity_type="t"))

    rid = await g.add_relationship(
        KnowledgeRelationship(
            id="r-1", source_id="e-1", target_id="e-2", relation_type="uses"
        )
    )
    assert rid == "r-1"
    assert g.relationship_count == 1

    rels = await g.get_relationships("e-1", direction="outgoing")
    assert len(rels) == 1
    assert rels[0].relation_type == "uses"


async def test_get_relationships_incoming():
    """Get incoming relationships for an entity."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="A", entity_type="t"))
    await g.add_entity(KnowledgeEntity(id="e-2", label="B", entity_type="t"))
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-1", source_id="e-1", target_id="e-2", relation_type="uses"
        )
    )

    rels = await g.get_relationships("e-2", direction="incoming")
    assert len(rels) == 1
    assert rels[0].source_id == "e-1"


async def test_get_relationships_both():
    """Get both incoming and outgoing relationships."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="A", entity_type="t"))
    await g.add_entity(KnowledgeEntity(id="e-2", label="B", entity_type="t"))
    await g.add_entity(KnowledgeEntity(id="e-3", label="C", entity_type="t"))
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-1", source_id="e-1", target_id="e-2", relation_type="uses"
        )
    )
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-2", source_id="e-3", target_id="e-2", relation_type="needs"
        )
    )

    rels = await g.get_relationships("e-2", direction="both")
    assert len(rels) == 2


async def test_get_relationships_filter_by_type():
    """Filter relationships by relation_type."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="A", entity_type="t"))
    await g.add_entity(KnowledgeEntity(id="e-2", label="B", entity_type="t"))
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-1", source_id="e-1", target_id="e-2", relation_type="uses"
        )
    )
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-2", source_id="e-1", target_id="e-2", relation_type="imports"
        )
    )

    rels = await g.get_relationships("e-1", relation_type="uses")
    assert len(rels) == 1
    assert rels[0].relation_type == "uses"


async def test_delete_relationship():
    """Deleting a relationship removes it from the graph."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="A", entity_type="t"))
    await g.add_entity(KnowledgeEntity(id="e-2", label="B", entity_type="t"))
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-1", source_id="e-1", target_id="e-2", relation_type="uses"
        )
    )

    deleted = await g.delete_relationship("r-1")
    assert deleted is True
    assert g.relationship_count == 0

    rels = await g.get_relationships("e-1")
    assert len(rels) == 0


async def test_delete_nonexistent_relationship():
    """Deleting a non-existent relationship returns False."""
    g = InMemoryKnowledgeGraph()
    assert await g.delete_relationship("missing") is False


async def test_replace_relationship_cleans_old_adjacency():
    """Reusing an edge ID with new source/target removes stale adjacency."""
    g = InMemoryKnowledgeGraph()
    for label in "ABCD":
        await g.add_entity(
            KnowledgeEntity(id=f"e-{label}", label=label, entity_type="n")
        )

    # Original edge: A -> B
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-1", source_id="e-A", target_id="e-B", relation_type="x"
        )
    )
    assert len(await g.get_relationships("e-A", direction="outgoing")) == 1
    assert len(await g.get_relationships("e-B", direction="incoming")) == 1

    # Replace same ID with C -> D
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-1", source_id="e-C", target_id="e-D", relation_type="x"
        )
    )

    # A must no longer have outgoing r-1
    assert len(await g.get_relationships("e-A", direction="outgoing")) == 0
    # B must no longer have incoming r-1
    assert len(await g.get_relationships("e-B", direction="incoming")) == 0
    # C -> D should be present
    assert len(await g.get_relationships("e-C", direction="outgoing")) == 1
    assert len(await g.get_relationships("e-D", direction="incoming")) == 1
    # Only one relationship total
    assert g.relationship_count == 1


# ── Claim operations ─────────────────────────────────────────────────────


async def test_add_and_get_claims():
    """Adding claims allows retrieval by entity id."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="Python", entity_type="lang"))
    cid = await g.add_claim(
        Claim(
            id="c-1",
            subject_id="e-1",
            predicate="has_version",
            object_value="3.12",
        )
    )
    assert cid == "c-1"

    claims = await g.get_claims("e-1")
    assert len(claims) == 1
    assert claims[0].predicate == "has_version"


async def test_get_claims_filter_by_predicate():
    """Filter claims by predicate."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="Python", entity_type="lang"))
    await g.add_claim(
        Claim(id="c-1", subject_id="e-1", predicate="has_version", object_value="3.12")
    )
    await g.add_claim(
        Claim(id="c-2", subject_id="e-1", predicate="is_typed", object_value="yes")
    )

    claims = await g.get_claims("e-1", predicate="has_version")
    assert len(claims) == 1
    assert claims[0].id == "c-1"


async def test_get_claims_empty():
    """Getting claims for entity with none returns empty."""
    g = InMemoryKnowledgeGraph()
    claims = await g.get_claims("missing")
    assert claims == []


# ── Entity search ────────────────────────────────────────────────────────


async def test_search_entities_by_label():
    """Search finds entities by label substring."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="Python", entity_type="lang"))
    await g.add_entity(KnowledgeEntity(id="e-2", label="Java", entity_type="lang"))
    await g.add_entity(KnowledgeEntity(id="e-3", label="PyTorch", entity_type="lib"))

    results = await g.search_entities("py")
    assert len(results) == 2
    labels = {e.label for e in results}
    assert "Python" in labels
    assert "PyTorch" in labels


async def test_search_entities_by_type():
    """Search filters by entity_type."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="Python", entity_type="lang"))
    await g.add_entity(KnowledgeEntity(id="e-2", label="PyTorch", entity_type="lib"))

    results = await g.search_entities("py", entity_type="lang")
    assert len(results) == 1
    assert results[0].label == "Python"


async def test_search_entities_by_property():
    """Search matches against property values."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(
        KnowledgeEntity(
            id="e-1",
            label="Proj",
            entity_type="project",
            properties={"language": "python"},
        )
    )

    results = await g.search_entities("python")
    assert len(results) == 1


async def test_search_entities_limit():
    """Search respects the limit parameter."""
    g = InMemoryKnowledgeGraph()
    for i in range(20):
        await g.add_entity(
            KnowledgeEntity(id=f"e-{i}", label=f"Item {i}", entity_type="t")
        )

    results = await g.search_entities("item", limit=5)
    assert len(results) == 5


async def test_search_entities_no_match():
    """Search returns empty for non-matching query."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-1", label="Python", entity_type="lang"))

    results = await g.search_entities("xyzzy")
    assert results == []


# ── BFS traversal ────────────────────────────────────────────────────────


async def _build_chain_graph() -> InMemoryKnowledgeGraph:
    """Build a linear chain: A -> B -> C -> D."""
    g = InMemoryKnowledgeGraph()
    for label in "ABCD":
        await g.add_entity(
            KnowledgeEntity(id=f"e-{label}", label=label, entity_type="node")
        )
    for src, tgt in [("A", "B"), ("B", "C"), ("C", "D")]:
        await g.add_relationship(
            KnowledgeRelationship(
                id=f"r-{src}{tgt}",
                source_id=f"e-{src}",
                target_id=f"e-{tgt}",
                relation_type="next",
            )
        )
    return g


async def test_bfs_traversal():
    """BFS visits nodes in breadth-first order."""
    g = await _build_chain_graph()
    result = await g.bfs("e-A", max_depth=10)
    assert result == ["e-A", "e-B", "e-C", "e-D"]


async def test_bfs_max_depth():
    """BFS respects max_depth."""
    g = await _build_chain_graph()
    result = await g.bfs("e-A", max_depth=1)
    assert result == ["e-A", "e-B"]


async def test_bfs_missing_start():
    """BFS from a missing node returns empty."""
    g = InMemoryKnowledgeGraph()
    assert await g.bfs("missing") == []


async def test_bfs_filter_relation_type():
    """BFS can filter by relation_type."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-A", label="A", entity_type="n"))
    await g.add_entity(KnowledgeEntity(id="e-B", label="B", entity_type="n"))
    await g.add_entity(KnowledgeEntity(id="e-C", label="C", entity_type="n"))
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-1", source_id="e-A", target_id="e-B", relation_type="uses"
        )
    )
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-2", source_id="e-A", target_id="e-C", relation_type="imports"
        )
    )

    result = await g.bfs("e-A", relation_type="uses")
    assert result == ["e-A", "e-B"]


# ── DFS traversal ────────────────────────────────────────────────────────


async def test_dfs_traversal():
    """DFS visits nodes in depth-first order."""
    g = await _build_chain_graph()
    result = await g.dfs("e-A", max_depth=10)
    assert result == ["e-A", "e-B", "e-C", "e-D"]


async def test_dfs_max_depth():
    """DFS respects max_depth."""
    g = await _build_chain_graph()
    result = await g.dfs("e-A", max_depth=1)
    assert result == ["e-A", "e-B"]


async def test_dfs_missing_start():
    """DFS from a missing node returns empty."""
    g = InMemoryKnowledgeGraph()
    assert await g.dfs("missing") == []


async def test_dfs_branching():
    """DFS explores branches depth-first."""
    g = InMemoryKnowledgeGraph()
    await g.add_entity(KnowledgeEntity(id="e-A", label="A", entity_type="n"))
    await g.add_entity(KnowledgeEntity(id="e-B", label="B", entity_type="n"))
    await g.add_entity(KnowledgeEntity(id="e-C", label="C", entity_type="n"))
    await g.add_entity(KnowledgeEntity(id="e-D", label="D", entity_type="n"))
    # A -> B -> D, A -> C
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-1", source_id="e-A", target_id="e-B", relation_type="x"
        )
    )
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-2", source_id="e-A", target_id="e-C", relation_type="x"
        )
    )
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-3", source_id="e-B", target_id="e-D", relation_type="x"
        )
    )

    result = await g.dfs("e-A", max_depth=10)
    # DFS: A, then B (first outgoing), then D (B's child), then C
    assert result == ["e-A", "e-B", "e-D", "e-C"]


# ── Path finding ─────────────────────────────────────────────────────────


async def test_find_path():
    """find_path returns shortest path."""
    g = await _build_chain_graph()
    path = await g.find_path("e-A", "e-D")
    assert path == ["e-A", "e-B", "e-C", "e-D"]


async def test_find_path_same_node():
    """Path from a node to itself is just that node."""
    g = await _build_chain_graph()
    path = await g.find_path("e-A", "e-A")
    assert path == ["e-A"]


async def test_find_path_no_path():
    """find_path returns None when no path exists."""
    g = await _build_chain_graph()
    # D has no outgoing edges, so D -> A is unreachable.
    path = await g.find_path("e-D", "e-A")
    assert path is None


async def test_find_path_missing_node():
    """find_path returns None for missing nodes."""
    g = InMemoryKnowledgeGraph()
    assert await g.find_path("missing", "also-missing") is None


async def test_find_path_max_depth():
    """find_path respects max_depth."""
    g = await _build_chain_graph()
    # Path A->D is 3 hops, max_depth=2 should not find it.
    path = await g.find_path("e-A", "e-D", max_depth=2)
    assert path is None


async def test_find_path_shortest():
    """find_path returns the shortest path when multiple exist."""
    g = InMemoryKnowledgeGraph()
    for label in "ABCD":
        await g.add_entity(
            KnowledgeEntity(id=f"e-{label}", label=label, entity_type="n")
        )
    # Long path: A -> B -> C -> D
    # Short path: A -> D
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-1", source_id="e-A", target_id="e-B", relation_type="x"
        )
    )
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-2", source_id="e-B", target_id="e-C", relation_type="x"
        )
    )
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-3", source_id="e-C", target_id="e-D", relation_type="x"
        )
    )
    await g.add_relationship(
        KnowledgeRelationship(
            id="r-4", source_id="e-A", target_id="e-D", relation_type="x"
        )
    )

    path = await g.find_path("e-A", "e-D")
    assert path == ["e-A", "e-D"]


# ── Subgraph extraction ─────────────────────────────────────────────────


async def test_get_subgraph():
    """get_subgraph extracts induced subgraph."""
    g = await _build_chain_graph()
    sg = await g.get_subgraph(["e-A", "e-B"])
    assert isinstance(sg, SubgraphResult)
    assert len(sg.entities) == 2
    # Only the A->B relationship should be included.
    assert len(sg.relationships) == 1
    assert sg.relationships[0].source_id == "e-A"
    assert sg.relationships[0].target_id == "e-B"


async def test_get_subgraph_no_relationships():
    """get_subgraph can exclude relationships."""
    g = await _build_chain_graph()
    sg = await g.get_subgraph(["e-A", "e-B"], include_relationships=False)
    assert len(sg.entities) == 2
    assert len(sg.relationships) == 0


async def test_get_subgraph_missing_ids():
    """get_subgraph skips missing entity ids."""
    g = await _build_chain_graph()
    sg = await g.get_subgraph(["e-A", "missing"])
    assert len(sg.entities) == 1
    assert sg.entities[0].id == "e-A"
