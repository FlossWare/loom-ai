"""Conformance tests for GraphBackend implementations.

Any backend that satisfies the GraphBackend protocol should pass all
tests in this module.  Override the ``graph_backend`` fixture in a
downstream ``conftest.py`` to plug in a different implementation.
"""

from __future__ import annotations

import pytest

from loom_ai import GraphEdge, GraphNode


async def test_add_and_get_node(graph_backend):
    """Adding a node and getting it by id returns the same data."""
    node = GraphNode(id="n-1", label="Person", properties={"name": "Alice"})
    node_id = await graph_backend.add_node(node)

    assert node_id == "n-1"

    retrieved = await graph_backend.get_node("n-1")
    assert retrieved is not None
    assert retrieved.label == "Person"
    assert retrieved.properties["name"] == "Alice"


async def test_get_missing_node_returns_none(graph_backend):
    """Requesting a non-existent node returns None."""
    result = await graph_backend.get_node("does-not-exist")
    assert result is None


async def test_add_nodes_and_edge(graph_backend):
    """Adding two nodes and an edge between them succeeds."""
    n1 = GraphNode(id="a", label="City", properties={"name": "Paris"})
    n2 = GraphNode(id="b", label="City", properties={"name": "London"})
    await graph_backend.add_node(n1)
    await graph_backend.add_node(n2)

    edge = GraphEdge(id="e-ab", source="a", target="b", label="connected_to")
    edge_id = await graph_backend.add_edge(edge)
    assert edge_id == "e-ab"


async def test_query_neighbors(graph_backend):
    """get_neighbors returns nodes connected by edges."""
    n1 = GraphNode(id="x", label="A")
    n2 = GraphNode(id="y", label="B")
    n3 = GraphNode(id="z", label="C")
    await graph_backend.add_node(n1)
    await graph_backend.add_node(n2)
    await graph_backend.add_node(n3)

    await graph_backend.add_edge(
        GraphEdge(id="e-xy", source="x", target="y", label="knows")
    )
    await graph_backend.add_edge(
        GraphEdge(id="e-xz", source="x", target="z", label="knows")
    )

    neighbors = await graph_backend.get_neighbors("x")
    neighbor_ids = {n.id for n in neighbors}
    assert neighbor_ids == {"y", "z"}


async def test_query_neighbors_with_label_filter(graph_backend):
    """get_neighbors filtered by edge_label returns only matching edges."""
    n1 = GraphNode(id="f1", label="Person")
    n2 = GraphNode(id="f2", label="Person")
    n3 = GraphNode(id="f3", label="Person")
    await graph_backend.add_node(n1)
    await graph_backend.add_node(n2)
    await graph_backend.add_node(n3)

    await graph_backend.add_edge(
        GraphEdge(id="e-12", source="f1", target="f2", label="friend")
    )
    await graph_backend.add_edge(
        GraphEdge(id="e-13", source="f1", target="f3", label="colleague")
    )

    friends = await graph_backend.get_neighbors("f1", edge_label="friend")
    assert len(friends) == 1
    assert friends[0].id == "f2"


async def test_remove_node(graph_backend):
    """Deleting a node removes it and its incident edges."""
    n1 = GraphNode(id="rm-1", label="Temp")
    n2 = GraphNode(id="rm-2", label="Temp")
    await graph_backend.add_node(n1)
    await graph_backend.add_node(n2)
    await graph_backend.add_edge(
        GraphEdge(id="e-rm", source="rm-1", target="rm-2", label="link")
    )

    deleted = await graph_backend.delete_node("rm-1")
    assert deleted is True

    assert await graph_backend.get_node("rm-1") is None

    # The edge should also be removed, so rm-2 has no neighbors
    neighbors = await graph_backend.get_neighbors("rm-2")
    assert len(neighbors) == 0


async def test_remove_missing_node_returns_false(graph_backend):
    """Deleting a non-existent node returns False."""
    result = await graph_backend.delete_node("never-existed")
    assert result is False


async def test_traverse(graph_backend):
    """traverse performs BFS up to the specified depth."""
    for nid in ("t0", "t1", "t2", "t3"):
        await graph_backend.add_node(GraphNode(id=nid, label="Node"))

    await graph_backend.add_edge(
        GraphEdge(id="te-01", source="t0", target="t1", label="next")
    )
    await graph_backend.add_edge(
        GraphEdge(id="te-12", source="t1", target="t2", label="next")
    )
    await graph_backend.add_edge(
        GraphEdge(id="te-23", source="t2", target="t3", label="next")
    )

    # Depth 1: only immediate neighbor
    depth1 = await graph_backend.traverse("t0", depth=1)
    assert {n.id for n in depth1} == {"t1"}

    # Depth 2: two hops
    depth2 = await graph_backend.traverse("t0", depth=2)
    assert {n.id for n in depth2} == {"t1", "t2"}


async def test_add_edge_missing_source_raises(graph_backend):
    """Adding an edge with a non-existent source node raises ValueError."""
    n2 = GraphNode(id="target-only", label="Node")
    await graph_backend.add_node(n2)

    edge = GraphEdge(
        id="bad-e",
        source="no-source",
        target="target-only",
        label="link",
    )
    with pytest.raises(ValueError):
        await graph_backend.add_edge(edge)
