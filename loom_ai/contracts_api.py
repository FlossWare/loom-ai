"""REST API protocol contracts for loom-ai.

Every protocol uses ``typing.Protocol`` with ``@runtime_checkable`` for
structural subtyping -- no inheritance or ABC required.  All I/O methods
are async.  Nothing outside the standard library is imported.

Model types are resolved only during static type-checking via the
``TYPE_CHECKING`` guard so that this module carries zero runtime
dependencies beyond ``typing``.

This module covers three contract areas:

- **RequestLifecycle** -- validate, authorise, execute, respond (#8)
- **ErrorHandler** -- error handling and formatting (#8)
- **Middleware** -- pre/post request hooks (#8)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from loom_ai.models_api import (
        APIError,
        APIRequest,
        APIResponse,
        AuthContext,
        MiddlewareContext,
    )


# -- Request Lifecycle (#8) ------------------------------------------------


@runtime_checkable
class RequestLifecycle(Protocol):
    """Full lifecycle for processing a REST API request.

    Implementations receive a raw request, validate it, check
    authorisation, execute the business logic, and produce a response.
    """

    async def validate(self, request: APIRequest) -> None:
        """Validate the incoming request.

        Raises on invalid input (e.g. missing required fields, malformed
        body).  Returns ``None`` when valid.
        """
        ...

    async def authorize(self, request: APIRequest) -> AuthContext:
        """Authenticate and authorise the request.

        Returns an ``AuthContext`` describing the caller's identity and
        permissions.
        """
        ...

    async def execute(self, request: APIRequest, auth: AuthContext) -> Any:
        """Execute the core business logic for the request."""
        ...

    async def respond(self, result: Any, *, request_id: str = "") -> APIResponse:
        """Transform an execution result into an ``APIResponse``."""
        ...


# -- Error Handling (#8) ---------------------------------------------------


@runtime_checkable
class ErrorHandler(Protocol):
    """Centralised error handling and formatting for the API layer."""

    async def handle(self, error: Exception, *, request_id: str = "") -> APIError:
        """Convert an exception into a structured ``APIError``."""
        ...

    async def format_error(self, api_error: APIError) -> APIResponse:
        """Render an ``APIError`` as an ``APIResponse``."""
        ...


# -- Middleware (#8) -------------------------------------------------------


@runtime_checkable
class Middleware(Protocol):
    """Hook that wraps request processing.

    ``before_request`` runs before business logic; ``after_request``
    runs after the response is built (even on error paths).
    """

    async def before_request(self, context: MiddlewareContext) -> MiddlewareContext:
        """Inspect or modify the context before execution.

        Returning a context with ``aborted=True`` short-circuits the
        lifecycle and the response set on the context is returned
        immediately.
        """
        ...

    async def after_request(self, context: MiddlewareContext) -> MiddlewareContext:
        """Inspect or modify the context after execution."""
        ...
