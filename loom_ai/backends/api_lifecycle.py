"""In-memory API lifecycle and execution backend implementations for loom-ai.

All classes use only the standard library -- zero external dependencies.
Suitable for testing, local development, and the 'crush' deployment
profile.  All data is lost on process exit.

Classes
-------
InMemoryRequestLifecycle   -- pass-through validate/authorize/execute/respond pipeline
InMemoryErrorHandler       -- exception-type to status-code mapping
PassthroughMiddleware      -- returns context unchanged
NoopExecutionStep          -- no-op execution step
LoggingExecutionObserver   -- records lifecycle events to an internal list
"""

from __future__ import annotations

import uuid
from typing import Any

from loom_ai.models_api import (
    APIError,
    APIRequest,
    APIResponse,
    AuthContext,
    MiddlewareContext,
)
from loom_ai.models_execution import (
    ExecutionContext,
    ExecutionResult,
    StepResult,
    StepStatus,
)

# ============================================================================
# RequestLifecycle
# ============================================================================


class InMemoryRequestLifecycle:
    """Pass-through request lifecycle: validate, authorize, execute, respond."""

    async def validate(self, request: APIRequest) -> None:
        if not request.path:
            raise ValueError("Request path must not be empty")

    async def authorize(self, request: APIRequest) -> AuthContext:
        headers = request.headers or {}
        token = headers.get("Authorization", "") or headers.get("authorization", "")
        if token:
            return AuthContext(
                authenticated=True,
                principal=token,
                roles=["user"],
            )
        return AuthContext(authenticated=False)

    async def execute(self, request: APIRequest, auth: AuthContext) -> Any:
        return {
            "method": request.method,
            "path": request.path,
            "authenticated": auth.authenticated,
        }

    async def respond(self, result: Any, *, request_id: str = "") -> APIResponse:
        return APIResponse(
            status_code=200,
            body=(
                {"data": result} if isinstance(result, dict) else {"data": str(result)}
            ),
            request_id=request_id,
        )


# ============================================================================
# ErrorHandler
# ============================================================================


_DEFAULT_ERROR_MAP: dict[type, tuple[int, str]] = {
    ValueError: (400, "bad_request"),
    KeyError: (404, "not_found"),
    PermissionError: (403, "forbidden"),
    NotImplementedError: (501, "not_implemented"),
}


class InMemoryErrorHandler:
    """Maps exception types to status codes and formats as APIError."""

    def __init__(self, error_map: dict[type, tuple[int, str]] | None = None) -> None:
        self._error_map = error_map or dict(_DEFAULT_ERROR_MAP)

    async def handle(self, error: Exception, *, request_id: str = "") -> APIError:
        for exc_type, (status, code) in self._error_map.items():
            if isinstance(error, exc_type):
                return APIError(
                    code=code,
                    message=str(error),
                    status_code=status,
                    request_id=request_id,
                )
        return APIError(
            code="internal_error",
            message=str(error),
            status_code=500,
            request_id=request_id,
        )

    async def format_error(self, api_error: APIError) -> APIResponse:
        return APIResponse(
            status_code=api_error.status_code,
            body={
                "error": {
                    "code": api_error.code,
                    "message": api_error.message,
                    "request_id": api_error.request_id,
                }
            },
            request_id=api_error.request_id,
        )


# ============================================================================
# Middleware
# ============================================================================


class PassthroughMiddleware:
    """Middleware that returns the context unchanged."""

    async def before_request(self, context: MiddlewareContext) -> MiddlewareContext:
        return context

    async def after_request(self, context: MiddlewareContext) -> MiddlewareContext:
        return context


# ============================================================================
# ExecutionStep
# ============================================================================


class NoopExecutionStep:
    """Execution step that does nothing and returns success."""

    def __init__(self, step_id: str = "") -> None:
        self._step_id = step_id or str(uuid.uuid4())

    async def execute(self, context: ExecutionContext) -> StepResult:
        return StepResult(
            step_id=self._step_id,
            status=StepStatus.SUCCESS,
        )


# ============================================================================
# ExecutionObserver
# ============================================================================


class LoggingExecutionObserver:
    """Records execution lifecycle events to an internal list."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def on_step_start(self, step_id: str, context: ExecutionContext) -> None:
        self.events.append(
            {
                "type": "step_start",
                "step_id": step_id,
                "execution_id": context.execution_id,
            }
        )

    async def on_step_complete(self, step_id: str, result: StepResult) -> None:
        self.events.append(
            {
                "type": "step_complete",
                "step_id": step_id,
                "status": result.status.value,
            }
        )

    async def on_step_error(self, step_id: str, error: Exception) -> None:
        self.events.append(
            {
                "type": "step_error",
                "step_id": step_id,
                "error": str(error),
            }
        )

    async def on_execution_complete(self, result: ExecutionResult) -> None:
        self.events.append(
            {
                "type": "execution_complete",
                "execution_id": result.execution_id,
                "status": result.status.value,
            }
        )
