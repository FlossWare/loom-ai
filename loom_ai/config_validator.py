"""Startup validation for LOOM_* environment configuration.

Validates backend selection, type constraints, and cross-field
dependencies before ``LoomConfig.from_env()`` is called.  Supports
environment-specific profiles (dev, prod, test) with different
defaults and required-field sets.

All validation is stdlib-only -- zero third-party dependencies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Environment(Enum):
    """Deployment environment profiles with distinct defaults."""

    DEV = "dev"
    PROD = "prod"
    TEST = "test"


@dataclass
class FieldSpec:
    """Specification for a single configuration field.

    Attributes
    ----------
    name:       Environment variable name (e.g. ``LOOM_STORAGE``).
    value_type: Expected Python type for the parsed value.
    choices:    Allowed string values.  Empty means any value accepted.
    default:    Default value when the env var is unset.
    required:   Whether the field must be explicitly set (no default).
    """

    name: str
    value_type: type
    choices: tuple[str, ...] = ()
    default: str | None = None
    required: bool = False


@dataclass
class ValidationError:
    """A single validation failure with enough context for a clear message."""

    field: str
    message: str
    value: Any = None


@dataclass
class ValidationResult:
    """Aggregate result of configuration validation."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    resolved: dict[str, str] = field(default_factory=dict)


_BACKEND_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        name="LOOM_STORAGE",
        value_type=str,
        choices=("memory", "postgresql"),
        default="memory",
    ),
    FieldSpec(
        name="LOOM_QUEUE",
        value_type=str,
        choices=("memory", "redis"),
        default="memory",
    ),
    FieldSpec(
        name="LOOM_SECRETS",
        value_type=str,
        choices=("env", "dotenv", "postgresql"),
        default="env",
    ),
    FieldSpec(
        name="LOOM_EMBEDDING",
        value_type=str,
        choices=("noop", "openai", "litellm"),
        default="noop",
    ),
    FieldSpec(
        name="LOOM_SEARCH",
        value_type=str,
        choices=("memory", "postgresql"),
        default="memory",
    ),
    FieldSpec(
        name="LOOM_GRAPH",
        value_type=str,
        choices=("disabled", "memory", "orientdb"),
        default="disabled",
    ),
    FieldSpec(
        name="LOOM_TOOLS",
        value_type=str,
        choices=("disabled", "memory"),
        default="disabled",
    ),
    FieldSpec(
        name="LOOM_RESOURCES",
        value_type=str,
        choices=("disabled", "memory"),
        default="disabled",
    ),
)

_LLM_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(name="LOOM_LLM_BASE_URL", value_type=str),
    FieldSpec(name="LOOM_LLM_API_KEY", value_type=str, default=""),
    FieldSpec(name="LOOM_LLM_MODEL", value_type=str, default="gpt-4o-mini"),
    FieldSpec(name="LOOM_LLM_PROVIDER", value_type=str, default="openai-compatible"),
)

_SECRETS_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(name="LOOM_SECRETS_FILE", value_type=str, default=".env"),
    FieldSpec(name="LOOM_SECRETS_PREFIX", value_type=str, default=""),
)

_SERVER_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(name="LOOM_PORT", value_type=int, default="5000"),
    FieldSpec(name="LOOM_API_KEY", value_type=str),
)

ALL_FIELDS: tuple[FieldSpec, ...] = (
    _BACKEND_FIELDS + _LLM_FIELDS + _SECRETS_FIELDS + _SERVER_FIELDS
)

_PROD_WARNINGS: dict[str, tuple[str, ...]] = {
    "LOOM_STORAGE": ("memory",),
    "LOOM_QUEUE": ("memory",),
    "LOOM_SEARCH": ("memory",),
    "LOOM_SECRETS": ("env",),
}

_ENV_DEFAULTS: dict[Environment, dict[str, str]] = {
    Environment.DEV: {
        "LOOM_STORAGE": "memory",
        "LOOM_QUEUE": "memory",
        "LOOM_SECRETS": "env",
        "LOOM_EMBEDDING": "noop",
        "LOOM_SEARCH": "memory",
        "LOOM_GRAPH": "disabled",
        "LOOM_TOOLS": "disabled",
        "LOOM_RESOURCES": "disabled",
    },
    Environment.TEST: {
        "LOOM_STORAGE": "memory",
        "LOOM_QUEUE": "memory",
        "LOOM_SECRETS": "env",
        "LOOM_EMBEDDING": "noop",
        "LOOM_SEARCH": "memory",
        "LOOM_GRAPH": "disabled",
        "LOOM_TOOLS": "disabled",
        "LOOM_RESOURCES": "disabled",
    },
    Environment.PROD: {
        "LOOM_STORAGE": "postgresql",
        "LOOM_QUEUE": "redis",
        "LOOM_SECRETS": "postgresql",
        "LOOM_EMBEDDING": "openai",
        "LOOM_SEARCH": "postgresql",
        "LOOM_GRAPH": "disabled",
        "LOOM_TOOLS": "disabled",
        "LOOM_RESOURCES": "disabled",
    },
}


def _field_map() -> dict[str, FieldSpec]:
    return {f.name: f for f in ALL_FIELDS}


def _parse_int(raw: str, field_name: str) -> tuple[int | None, ValidationError | None]:
    try:
        return int(raw), None
    except ValueError:
        return None, ValidationError(
            field=field_name,
            message=f"expected integer, got {raw!r}",
            value=raw,
        )


class LoomConfigValidator:
    """Validate LOOM_* environment variables before backend construction.

    Reads environment variables (or an explicit override dict), checks
    values against known choices, validates types, detects missing
    required fields, and warns about configurations unsuitable for the
    target environment profile.
    """

    def __init__(
        self,
        environment: Environment = Environment.DEV,
        *,
        fields: tuple[FieldSpec, ...] | None = None,
    ) -> None:
        self._environment = environment
        self._fields = fields if fields is not None else ALL_FIELDS

    @property
    def environment(self) -> Environment:
        return self._environment

    def _validate_field(
        self,
        spec: FieldSpec,
        raw: str | None,
        env_defaults: dict[str, str],
        errors: list[ValidationError],
        resolved: dict[str, str],
    ) -> None:
        if raw is None:
            if spec.required:
                errors.append(
                    ValidationError(
                        field=spec.name,
                        message="required but not set",
                    )
                )
            else:
                fallback = env_defaults.get(spec.name, spec.default)
                if fallback is not None:
                    resolved[spec.name] = fallback
            return

        if spec.choices and raw not in spec.choices:
            errors.append(
                ValidationError(
                    field=spec.name,
                    message=(
                        f"invalid value {raw!r}; "
                        f"valid options: {', '.join(spec.choices)}"
                    ),
                    value=raw,
                )
            )
            return

        if spec.value_type is int:
            _, err = _parse_int(raw, spec.name)
            if err is not None:
                errors.append(err)
                return

        resolved[spec.name] = raw

    def validate(
        self,
        env: dict[str, str] | None = None,
    ) -> ValidationResult:
        """Validate configuration from *env* (defaults to ``os.environ``)."""
        source = env if env is not None else dict(os.environ)
        errors: list[ValidationError] = []
        warnings: list[str] = []
        resolved: dict[str, str] = {}

        env_defaults = _ENV_DEFAULTS.get(self._environment, {})

        for spec in self._fields:
            self._validate_field(
                spec,
                source.get(spec.name),
                env_defaults,
                errors,
                resolved,
            )

        self._check_dependencies(resolved, source, errors)
        self._check_environment_warnings(resolved, warnings)
        self._check_port_range(resolved, errors)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            resolved=resolved,
        )

    def defaults_for(self, environment: Environment | None = None) -> dict[str, str]:
        """Return the default values for the given environment profile."""
        env = environment if environment is not None else self._environment
        result: dict[str, str] = {}
        env_defaults = _ENV_DEFAULTS.get(env, {})
        for spec in self._fields:
            val = env_defaults.get(spec.name, spec.default)
            if val is not None:
                result[spec.name] = val
        return result

    def _check_dependencies(
        self,
        resolved: dict[str, str],
        source: dict[str, str],
        errors: list[ValidationError],
    ) -> None:
        secrets = resolved.get("LOOM_SECRETS")
        if secrets == "dotenv":
            secrets_file = source.get("LOOM_SECRETS_FILE", ".env")
            if not secrets_file:
                errors.append(
                    ValidationError(
                        field="LOOM_SECRETS_FILE",
                        message=(
                            "LOOM_SECRETS=dotenv requires a non-empty "
                            "LOOM_SECRETS_FILE path"
                        ),
                    )
                )

        llm_url = resolved.get("LOOM_LLM_BASE_URL")
        if llm_url is not None and not llm_url:
            errors.append(
                ValidationError(
                    field="LOOM_LLM_BASE_URL",
                    message="must be a non-empty URL when set",
                )
            )

    def _check_environment_warnings(
        self,
        resolved: dict[str, str],
        warnings: list[str],
    ) -> None:
        if self._environment != Environment.PROD:
            return

        for field_name, flagged_values in _PROD_WARNINGS.items():
            value = resolved.get(field_name)
            if value in flagged_values:
                warnings.append(
                    f"{field_name}={value!r} is not recommended for production"
                )

    def _check_port_range(
        self,
        resolved: dict[str, str],
        errors: list[ValidationError],
    ) -> None:
        raw = resolved.get("LOOM_PORT")
        if raw is None:
            return
        try:
            port = int(raw)
        except ValueError:
            return
        if port < 1 or port > 65535:
            errors.append(
                ValidationError(
                    field="LOOM_PORT",
                    message=f"port {port} outside valid range 1-65535",
                    value=raw,
                )
            )


def validate_env(
    environment: Environment = Environment.DEV,
    env: dict[str, str] | None = None,
) -> ValidationResult:
    """Convenience function: validate LOOM_* configuration in one call."""
    return LoomConfigValidator(environment).validate(env)


def format_errors(result: ValidationResult) -> str:
    """Format validation errors as a human-readable multi-line string."""
    if result.valid:
        return "Configuration is valid."
    lines = ["Configuration errors:"]
    for err in result.errors:
        suffix = f" (got {err.value!r})" if err.value is not None else ""
        lines.append(f"  {err.field}: {err.message}{suffix}")
    if result.warnings:
        lines.append("Warnings:")
        for w in result.warnings:
            lines.append(f"  {w}")
    return "\n".join(lines)
