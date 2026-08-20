"""Domain routers for the loom-ai REST server."""

from loom_ai.routers.consensus import _mount_consensus_routes
from loom_ai.routers.graph import _mount_graph_routes
from loom_ai.routers.llm import _mount_llm_routes
from loom_ai.routers.queue import _mount_queue_routes
from loom_ai.routers.resources import _mount_resources_routes
from loom_ai.routers.router_routes import _mount_router_routes
from loom_ai.routers.search import _mount_search_routes
from loom_ai.routers.secrets import _mount_secrets_routes
from loom_ai.routers.storage import _mount_storage_routes
from loom_ai.routers.tools import _mount_tools_routes

__all__ = [
    "_mount_consensus_routes",
    "_mount_graph_routes",
    "_mount_llm_routes",
    "_mount_queue_routes",
    "_mount_resources_routes",
    "_mount_router_routes",
    "_mount_search_routes",
    "_mount_secrets_routes",
    "_mount_storage_routes",
    "_mount_tools_routes",
]
