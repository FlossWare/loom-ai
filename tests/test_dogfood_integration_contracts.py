from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from loom_ai.demo_agent import DemoAgent
from loom_ai.git_transaction import GitTransaction


@pytest.mark.asyncio
async def test_postgresql_configuration_does_not_fallback_to_memory(monkeypatch):
    monkeypatch.setenv("LOOM_STORAGE", "postgresql")
    with patch(
        "loom_ai.backends.postgresql.get_shared_pool",
        new=AsyncMock(side_effect=RuntimeError("postgres unavailable")),
    ):
        with pytest.raises(RuntimeError, match="postgres unavailable"):
            await DemoAgent._build_session_manager()


@pytest.mark.asyncio
async def test_git_transaction_requires_verification_before_push(tmp_path):
    tx = GitTransaction(str(tmp_path))
    tx._snapshot = object()  # only exercise the publication guard
    tx._committed = True
    with pytest.raises(RuntimeError, match="Verification"):
        await tx.push()


@pytest.mark.asyncio
async def test_git_transaction_requires_verification_before_pr(tmp_path):
    tx = GitTransaction(str(tmp_path))
    tx._snapshot = object()
    tx._pushed = True
    with pytest.raises(RuntimeError, match="Verification"):
        await tx.create_pr("title", "body")
