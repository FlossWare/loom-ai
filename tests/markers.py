from __future__ import annotations

BACKEND_GROUPS: dict[str, list[str]] = {
    "postgresql": [
        "tests/test_postgresql.py",
    ],
    "redis": [
        "tests/test_redis_queue.py",
    ],
    "server": [
        "tests/test_server_auth.py",
        "tests/test_server_port.py",
        "tests/test_server_responses.py",
        "tests/test_server_secrets.py",
        "tests/test_server_validation.py",
        "tests/test_queue_validation.py",
    ],
    "openai": [
        "tests/test_model_router.py",
        "tests/test_provider_health.py",
    ],
    "litellm": [
        "tests/test_resilience.py",
    ],
    "orientdb": [
        "tests/test_graph.py",
    ],
}

ALL_BACKEND_FILES: set[str] = set()
for _files in BACKEND_GROUPS.values():
    ALL_BACKEND_FILES.update(_files)
