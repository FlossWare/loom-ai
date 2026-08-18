"""Benchmarks for MemoryGraphBackend operations."""

from __future__ import annotations

import asyncio

import pytest

from loom_ai.backends.memory import MemoryGraphBackend
from loom_ai.models import GraphEdge, GraphNode

SIZES = [10, 100, 1000]


def _make_node(i: int) -> GraphNode:
    return GraphNode(id=f"node-{i}", label="entity", properties={"index": i})


def _make_edge(i: int, source: str, target: str) -> GraphEdge:
    return GraphEdge(id=f"edge-{i}", source=source, target=target, label="relates_to")


@pytest.mark.parametrize("size", SIZES)
def test_add_node(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryGraphBackend()
    nodes = [_make_node(i) for i in range(size)]

    def run():
        for node in nodes:
            loop.run_until_complete(backend.add_node(node))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_add_edge(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryGraphBackend()
    hub = _make_node(0)
    loop.run_until_complete(backend.add_node(hub))
    for i in range(1, size + 1):
        loop.run_until_complete(backend.add_node(_make_node(i)))
    edges = [_make_edge(i, "node-0", f"node-{i}") for i in range(1, size + 1)]

    def run():
        for edge in edges:
            loop.run_until_complete(backend.add_edge(edge))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_get_neighbors(benchmark, size):
    loop = asyncio.new_event_loop()
    backend = MemoryGraphBackend()
    loop.run_until_complete(backend.add_node(_make_node(0)))
    for i in range(1, size + 1):
        loop.run_until_complete(backend.add_node(_make_node(i)))
        loop.run_until_complete(backend.add_edge(_make_edge(i, "node-0", f"node-{i}")))

    def run():
        loop.run_until_complete(backend.get_neighbors("node-0"))

    benchmark(run)
    loop.close()


@pytest.mark.parametrize("size", SIZES)
def test_traverse(benchmark, size):
    """Benchmark BFS traversal on a linear chain of nodes."""
    loop = asyncio.new_event_loop()
    backend = MemoryGraphBackend()
    for i in range(size):
        loop.run_until_complete(backend.add_node(_make_node(i)))
    for i in range(size - 1):
        loop.run_until_complete(
            backend.add_edge(_make_edge(i, f"node-{i}", f"node-{i + 1}"))
        )
    depth = min(size - 1, 5)

    def run():
        loop.run_until_complete(backend.traverse("node-0", depth=depth))

    benchmark(run)
    loop.close()
