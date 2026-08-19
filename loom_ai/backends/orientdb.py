"""OrientDB graph backend (requires ``pyorient`` extra).

Wraps the OrientDB Python driver behind the
:class:`~loom_ai.contracts_phase4.KnowledgeGraph` protocol, providing
persistent graph storage with the OrientDB multi-model database.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import TYPE_CHECKING

try:
    import pyorient  # type: ignore[import-untyped]
except ImportError as _exc:
    raise ImportError(
        "OrientDB graph requires the 'pyorient' package.  "
        "Install with: pip install flossware-loom-ai[orientdb]"
    ) from _exc

if TYPE_CHECKING:
    from loom_ai.models import GraphEdge, GraphNode

_SAFE_ID = re.compile(r"^[\w.-]+$")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _safe_id(value: str) -> str:
    if not _SAFE_ID.match(value):
        raise ValueError(f"unsafe graph identifier: {value!r}")
    return value


class OrientDBGraphBackend:
    """OrientDB-backed knowledge graph.

    Satisfies :class:`~loom_ai.contracts_phase4.KnowledgeGraph` via structural
    subtyping.
    """

    def __init__(self, client: object, *, db_name: str = "loom") -> None:
        self._client = client
        self._db_name = db_name

    @classmethod
    async def from_env(cls) -> OrientDBGraphBackend:
        host = os.environ.get("LOOM_ORIENTDB_HOST", "localhost")
        port = int(os.environ.get("LOOM_ORIENTDB_PORT", "2424"))
        user = os.environ.get("LOOM_ORIENTDB_USER", "root")
        password = os.environ.get("LOOM_ORIENTDB_PASSWORD", "")
        db_name = os.environ.get("LOOM_ORIENTDB_DB", "loom")

        def _connect() -> object:
            client = pyorient.OrientDB(host, port)
            client.connect(user, password)
            if not client.db_exists(db_name):
                client.db_create(db_name, pyorient.DB_TYPE_GRAPH)
            client.db_open(db_name, user, password)
            return client

        client = await asyncio.to_thread(_connect)
        return cls(client, db_name=db_name)

    async def add_node(self, entity: GraphNode) -> str:
        label = _escape(entity.label)
        etype = _escape(entity.entity_type)
        cmd = (
            f"INSERT INTO KnowledgeEntity SET label = '{label}', "
            f"entity_type = '{etype}'"
        )
        result = await asyncio.to_thread(self._client.command, cmd)
        rid = str(result[0]._rid) if result else entity.id or ""
        return rid

    async def get_node(self, node_id: str) -> GraphNode | None:
        from loom_ai.models import GraphNode

        rid = _safe_id(node_id)
        result = await asyncio.to_thread(
            self._client.command, f"SELECT FROM {rid}"
        )
        if not result:
            return None
        row = result[0]
        return GraphNode(
            id=str(row._rid),
            label=getattr(row, "label", ""),
            entity_type=getattr(row, "entity_type", ""),
            properties={},
        )

    async def get_neighbors(
        self, node_id: str, *, edge_label: str | None = None
    ) -> list[GraphNode]:
        from loom_ai.models import GraphNode

        rid = _safe_id(node_id)
        if edge_label:
            el = _escape(edge_label)
            query = f"SELECT expand(out('{el}')) FROM {rid}"
        else:
            query = f"SELECT expand(out()) FROM {rid}"
        result = await asyncio.to_thread(self._client.command, query)
        nodes: list[GraphNode] = []
        for row in result or []:
            nodes.append(
                GraphNode(
                    id=str(row._rid),
                    label=getattr(row, "label", ""),
                    entity_type=getattr(row, "entity_type", ""),
                    properties={},
                )
            )
        return nodes

    async def add_edge(self, edge: GraphEdge) -> str:
        src = _safe_id(edge.source)
        tgt = _safe_id(edge.target)
        label = _escape(edge.label)
        cmd = f"CREATE EDGE {label} FROM {src} TO {tgt}"
        result = await asyncio.to_thread(self._client.command, cmd)
        return str(result[0]._rid) if result else edge.id or ""

    async def close(self) -> None:
        await asyncio.to_thread(self._client.close)
