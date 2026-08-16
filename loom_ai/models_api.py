"""REST API data models for loom-ai.

All models are plain dataclasses with no imports outside the standard
library.  These models support the API protocol contracts defined in
``contracts_api.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class APIRequest:
    """Incoming REST API request representation."""

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    body: dict | None = None
    client_ip: str = ""
    request_id: str = ""


@dataclass
class APIResponse:
    """Outgoing REST API response representation."""

    status_code: int
    body: dict | None = None
    headers: dict[str, str] = field(default_factory=dict)
    request_id: str = ""


@dataclass
class AuthContext:
    """Authentication and authorisation context for a request."""

    authenticated: bool = False
    principal: str = ""
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class APIError:
    """Structured error detail returned by the API."""

    code: str
    message: str
    status_code: int = 500
    details: dict = field(default_factory=dict)
    request_id: str = ""


@dataclass
class MiddlewareContext:
    """Mutable context that middleware passes through the request chain."""

    request: APIRequest | None = None
    response: APIResponse | None = None
    auth: AuthContext | None = None
    metadata: dict = field(default_factory=dict)
    aborted: bool = False
