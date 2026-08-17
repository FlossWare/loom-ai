"""Locust load test definitions for the loom-ai FastAPI server.

Targets the /health, /ready, and /llm/chat endpoints.  Requires a
running loom-ai server (``python -m loom_ai.server``).

Install with:  pip install flossware-loom-ai[loadtest]
Run with:      locust -f tests/loadtest/locustfile.py
"""

from __future__ import annotations

from locust import HttpUser, between, task


class HealthUser(HttpUser):
    """Simulates lightweight probe traffic against liveness/readiness."""

    wait_time = between(0.1, 0.5)

    @task(3)
    def health(self):
        self.client.get("/health")

    @task(2)
    def ready(self):
        self.client.get("/ready")

    @task(1)
    def chat(self):
        self.client.post(
            "/llm/chat",
            json={
                "messages": [{"role": "user", "content": "ping"}],
                "temperature": 0.0,
            },
        )
