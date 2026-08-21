"""Security capabilities with audit trail (#814).

Defines an explicit capability model that binds each
privileged operation to an approved workspace and set of
constraints.  Every check emits a structured audit event
via :class:`~loom_ai.backends.security.AuditLogger`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from loom_ai.backends.security import (
    AuditLogger,
    SecretsMask,
)


class Capability(str, Enum):
    """Privileged operations the agent may perform."""

    FS_READ = "fs_read"
    FS_WRITE = "fs_write"
    SUBPROCESS = "subprocess"
    GIT_READ = "git_read"
    GIT_WRITE = "git_write"
    GITHUB_READ = "github_read"
    GITHUB_WRITE = "github_write"
    NETWORK = "network"
    SECRET_READ = "secret_read"


@dataclass(frozen=True)
class SubprocessPolicy:
    """Subprocess execution constraints."""

    allowed_commands: frozenset[str]
    max_timeout: int = 300
    max_output_bytes: int = 1_000_000


@dataclass(frozen=True)
class CapabilityGrant:
    """A single granted capability bound to a workspace."""

    capability: Capability
    workspace: str
    constraints: dict[str, Any]
    granted_by: str
    expires_at: str = ""


class CapabilityGuard:
    """Validates and audits privileged operations."""

    def __init__(
        self,
        audit_logger: AuditLogger,
    ) -> None:
        self._audit = audit_logger
        self._grants: dict[tuple[str, Capability], CapabilityGrant] = {}

    def grant(
        self,
        cap: Capability,
        workspace: str | Path,
        constraints: dict[str, Any],
        granted_by: str,
        expires_at: str = "",
    ) -> CapabilityGrant:
        """Add a capability grant for a workspace."""
        resolved = str(Path(workspace).resolve())
        g = CapabilityGrant(
            capability=cap,
            workspace=resolved,
            constraints=constraints,
            granted_by=granted_by,
            expires_at=expires_at,
        )
        self._grants[(resolved, cap)] = g
        return g

    def check(
        self,
        cap: Capability,
        workspace: str | Path,
        **ctx: Any,
    ) -> bool:
        """Check whether *cap* is allowed for *workspace*."""
        resolved = str(Path(workspace).resolve())
        g = self._grants.get((resolved, cap))

        if g is None:
            self._log(
                cap,
                resolved,
                ctx,
                "denied",
                "no valid grant",
            )
            return False

        if self._is_expired(g.expires_at):
            self._log(
                cap,
                resolved,
                ctx,
                "denied",
                "grant expired",
            )
            return False

        ok = self._validate(cap, resolved, g, ctx)
        outcome = "allowed" if ok else "denied"
        detail = "" if ok else self._denial_reason(cap, ctx)
        self._log(cap, resolved, ctx, outcome, detail)
        return ok

    def require(
        self,
        cap: Capability,
        workspace: str | Path,
        **ctx: Any,
    ) -> None:
        """Like :meth:`check` but raises on denial."""
        if not self.check(cap, workspace, **ctx):
            raise PermissionError(f"Capability {cap.value} denied for {workspace}")

    # -- internals -------------------------------------------

    @staticmethod
    def _is_expired(expires_at: str) -> bool:
        if not expires_at:
            return False
        exp = datetime.fromisoformat(expires_at)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp < datetime.now(timezone.utc)

    def _validate(
        self,
        cap: Capability,
        workspace: str,
        grant: CapabilityGrant,
        ctx: dict[str, Any],
    ) -> bool:
        if cap == Capability.SUBPROCESS:
            return self._check_subprocess(grant, ctx)
        if cap in (Capability.FS_READ, Capability.FS_WRITE):
            return self._check_fs(workspace, ctx)
        if cap == Capability.GITHUB_WRITE:
            return self._check_github(grant, ctx)
        return True

    @staticmethod
    def _check_subprocess(
        grant: CapabilityGrant,
        ctx: dict[str, Any],
    ) -> bool:
        allowed = grant.constraints.get(
            "allowed_cmds",
            [],
        )
        cmd = ctx.get("cmd", "")
        return cmd in allowed

    @staticmethod
    def _check_fs(
        workspace: str,
        ctx: dict[str, Any],
    ) -> bool:
        path = ctx.get("path", "")
        if not path:
            return True
        ws = Path(workspace)
        target = (ws / path).resolve()
        if not target.is_relative_to(ws):
            return False
        current = ws
        for part in Path(path).parts:
            current = current / part
            if current.is_symlink():
                link_dst = current.resolve()
                if not link_dst.is_relative_to(ws):
                    return False
        return True

    @staticmethod
    def _check_github(
        grant: CapabilityGrant,
        ctx: dict[str, Any],
    ) -> bool:
        allowed = grant.constraints.get(
            "allowed_repos",
            [],
        )
        repo = ctx.get("repo", "")
        return repo in allowed

    @staticmethod
    def _denial_reason(
        cap: Capability,
        ctx: dict[str, Any],
    ) -> str:
        if cap == Capability.SUBPROCESS:
            return f"cmd not allowed: {ctx.get('cmd')}"
        if cap in (Capability.FS_READ, Capability.FS_WRITE):
            return f"path denied: {ctx.get('path')}"
        if cap == Capability.GITHUB_WRITE:
            return f"repo not allowed: {ctx.get('repo')}"
        return "denied"

    def _log(
        self,
        cap: Capability,
        workspace: str,
        ctx: dict[str, Any],
        outcome: str,
        detail: str = "",
    ) -> None:
        safe_ctx = dict(ctx)
        if cap == Capability.SECRET_READ:
            safe_ctx.pop("value", None)
        self._audit.log(
            actor="capability_guard",
            action=cap.value,
            resource=workspace,
            detail=detail,
            outcome=outcome,
        )


class SecretGuard:
    """Wraps secret access with redaction and audit."""

    def __init__(
        self,
        audit_logger: AuditLogger,
        secrets_mask: SecretsMask | None = None,
        getter: Any = None,
    ) -> None:
        self._audit = audit_logger
        self._mask = secrets_mask or SecretsMask()
        self._getter = getter or os.environ.get
        self._accessed: set[str] = set()

    def get(self, name: str) -> str:
        """Retrieve a secret by name."""
        value = self._getter(name, "")
        if not value:
            self._audit.log(
                actor="secret_guard",
                action="secret_read",
                resource=name,
                detail="not found",
                outcome="denied",
            )
            raise KeyError(f"Secret not found: {name}")
        self._accessed.add(name)
        self._audit.log(
            actor="secret_guard",
            action="secret_read",
            resource=name,
            outcome="allowed",
        )
        return value

    def redact(self, text: str) -> str:
        """Redact known secret patterns from text."""
        return self._mask.redact(text)

    @property
    def accessed(self) -> frozenset[str]:
        """Names of secrets accessed this session."""
        return frozenset(self._accessed)
