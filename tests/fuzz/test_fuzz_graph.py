"""Property-based fuzz tests for GraphBackend (MemoryGraphBackend).

Uses Hypothesis to generate edge-case inputs and verifies that graph
operations never crash with valid-typed but unusual inputs, maintain
idempotency for add_node, and handle concurrent mutations without
corruption.
"""

from __future__ import annotations

import asyncio

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from loom_ai.backends.memory import MemoryGraphBackend
from loom_ai.models import GraphEdge, GraphNode


def _run(coro):
    return asyncio.run(coro)


FUZZ_TEXT = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "M", "N", "P", "S", "Z")),
    min_size=0,
    max_size=5000,
)

FUZZ_ID = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=200,
)

FUZZ_LABEL = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "N", "P")),
    min_size=1,
    max_size=100,
)


class TestGraphFuzz:
    @given(node_id=FUZZ_ID, label=FUZZ_LABEL)
    @settings(max_examples=100, deadline=None)
    def test_add_and_get_node_never_crashes(self, node_id, label):
        backend = MemoryGraphBackend()
        node = GraphNode(id=node_id, label=label, properties={})
        result_id = _run(backend.add_node(node))
        assert result_id == node_id

        retrieved = _run(backend.get_node(node_id))
        assert retrieved is not None
        assert retrieved.label == label

    @given(node_id=FUZZ_ID, label=FUZZ_LABEL)
    @settings(max_examples=50, deadline=None)
    def test_add_node_is_idempotent(self, node_id, label):
        backend = MemoryGraphBackend()
        node = GraphNode(id=node_id, label=label, properties={})
        _run(backend.add_node(node))
        _run(backend.add_node(node))

        retrieved = _run(backend.get_node(node_id))
        assert retrieved is not None

    @given(node_id=FUZZ_ID)
    @settings(max_examples=50, deadline=None)
    def test_get_missing_node_returns_none(self, node_id):
        backend = MemoryGraphBackend()
        assert _run(backend.get_node(node_id)) is None

    @given(node_id=FUZZ_ID)
    @settings(max_examples=50, deadline=None)
    def test_delete_missing_node_returns_false(self, node_id):
        backend = MemoryGraphBackend()
        assert _run(backend.delete_node(node_id)) is False

    @given(node_id=FUZZ_ID, label=FUZZ_LABEL)
    @settings(max_examples=50, deadline=None)
    def test_add_delete_roundtrip(self, node_id, label):
        backend = MemoryGraphBackend()
        node = GraphNode(id=node_id, label=label, properties={})
        _run(backend.add_node(node))
        assert _run(backend.delete_node(node_id)) is True
        assert _run(backend.get_node(node_id)) is None

    @given(
        n1_id=FUZZ_ID,
        n2_id=FUZZ_ID,
        edge_id=FUZZ_ID,
        edge_label=FUZZ_LABEL,
    )
    @settings(max_examples=50, deadline=None)
    def test_add_edge_between_fuzz_nodes(self, n1_id, n2_id, edge_id, edge_label):
        assume(n1_id != n2_id)
        backend = MemoryGraphBackend()
        _run(backend.add_node(GraphNode(id=n1_id, label="A", properties={})))
        _run(backend.add_node(GraphNode(id=n2_id, label="B", properties={})))

        edge = GraphEdge(
            id=edge_id, source=n1_id, target=n2_id, label=edge_label
        )
        result_id = _run(backend.add_edge(edge))
        assert result_id == edge_id

        neighbors = _run(backend.get_neighbors(n1_id))
        assert any(n.id == n2_id for n in neighbors)

    @given(edge_id=FUZZ_ID, edge_label=FUZZ_LABEL)
    @settings(max_examples=50, deadline=None)
    def test_add_edge_missing_source_raises(self, edge_id, edge_label):
        backend = MemoryGraphBackend()
        _run(backend.add_node(GraphNode(id="target", label="T", properties={})))

        edge = GraphEdge(
            id=edge_id, source="no-such-node", target="target", label=edge_label
        )
        with pytest.raises(ValueError):  # NOSONAR — single invocation: _run is a sync wrapper
            _run(backend.add_edge(edge))

    @given(node_id=FUZZ_ID)
    @settings(max_examples=50, deadline=None)
    def test_get_neighbors_on_isolated_node(self, node_id):
        backend = MemoryGraphBackend()
        _run(backend.add_node(GraphNode(id=node_id, label="Isolated", properties={})))

        neighbors = _run(backend.get_neighbors(node_id))
        assert neighbors == []

    @given(node_id=FUZZ_ID)
    @settings(max_examples=50, deadline=None)
    def test_traverse_on_isolated_node(self, node_id):
        backend = MemoryGraphBackend()
        _run(backend.add_node(GraphNode(id=node_id, label="Alone", properties={})))

        result = _run(backend.traverse(node_id, depth=3))
        assert result == []

    @given(edge_id=FUZZ_ID)
    @settings(max_examples=50, deadline=None)
    def test_delete_missing_edge_returns_false(self, edge_id):
        backend = MemoryGraphBackend()
        assert _run(backend.delete_edge(edge_id)) is False

    @given(
        props=st.dictionaries(
            keys=st.text(min_size=1, max_size=50),
            values=st.one_of(st.text(max_size=200), st.integers(), st.floats(allow_nan=False)),
            max_size=20,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_node_with_arbitrary_properties(self, props):
        backend = MemoryGraphBackend()
        node = GraphNode(id="prop-node", label="Props", properties=props)
        _run(backend.add_node(node))

        retrieved = _run(backend.get_node("prop-node"))
        assert retrieved is not None
        assert retrieved.properties == props


class TestGraphConcurrency:
    async def test_concurrent_add_nodes(self):
        backend = MemoryGraphBackend()
        nodes = [
            GraphNode(id=f"cn-{i}", label="Conc", properties={})
            for i in range(50)
        ]

        await asyncio.gather(*(backend.add_node(n) for n in nodes))

        for i in range(50):
            assert await backend.get_node(f"cn-{i}") is not None

    async def test_concurrent_add_and_delete_nodes(self):
        backend = MemoryGraphBackend()
        for i in range(20):
            await backend.add_node(
                GraphNode(id=f"cad-{i}", label="T", properties={})
            )

        async def add_more():
            for i in range(20, 40):
                await backend.add_node(
                    GraphNode(id=f"cad-{i}", label="T", properties={})
                )

        async def delete_some():
            for i in range(10):
                await backend.delete_node(f"cad-{i}")

        await asyncio.gather(add_more(), delete_some())

        for i in range(20, 40):
            assert await backend.get_node(f"cad-{i}") is not None
        for i in range(10):
            assert await backend.get_node(f"cad-{i}") is None
