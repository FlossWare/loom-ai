"""Tests for the configuration validation system."""

from __future__ import annotations

import pytest

from loom_ai.config_validator import (
    ALL_FIELDS,
    Environment,
    FieldSpec,
    LoomConfigValidator,
    ValidationError,
    ValidationResult,
    format_errors,
    validate_env,
)


# ── FieldSpec ────────────────────────────────────────────────────────────


class TestFieldSpec:
    def test_defaults(self):
        fs = FieldSpec(name="FOO", value_type=str)
        assert fs.choices == ()
        assert fs.default is None
        assert fs.required is False

    def test_with_choices(self):
        fs = FieldSpec(name="X", value_type=str, choices=("a", "b"))
        assert fs.choices == ("a", "b")


# ── ValidationResult ────────────────────────────────────────────────────


class TestValidationResult:
    def test_valid_result(self):
        r = ValidationResult(valid=True)
        assert r.valid is True
        assert r.errors == []
        assert r.warnings == []
        assert r.resolved == {}

    def test_invalid_result(self):
        err = ValidationError(field="X", message="bad")
        r = ValidationResult(valid=False, errors=[err])
        assert r.valid is False
        assert len(r.errors) == 1


# ── Choice validation ───────────────────────────────────────────────────


class TestChoiceValidation:
    def test_valid_storage_choices(self):
        for val in ("memory", "postgresql"):
            result = validate_env(env={"LOOM_STORAGE": val})
            storage_errors = [e for e in result.errors if e.field == "LOOM_STORAGE"]
            assert storage_errors == [], f"{val!r} should be accepted"

    def test_invalid_storage_choice(self):
        result = validate_env(env={"LOOM_STORAGE": "sqlite"})
        assert not result.valid
        errors = [e for e in result.errors if e.field == "LOOM_STORAGE"]
        assert len(errors) == 1
        assert "sqlite" in errors[0].message

    def test_valid_queue_choices(self):
        for val in ("memory", "redis"):
            result = validate_env(env={"LOOM_QUEUE": val})
            queue_errors = [e for e in result.errors if e.field == "LOOM_QUEUE"]
            assert queue_errors == [], f"{val!r} should be accepted"

    def test_invalid_queue_choice(self):
        result = validate_env(env={"LOOM_QUEUE": "kafka"})
        errors = [e for e in result.errors if e.field == "LOOM_QUEUE"]
        assert len(errors) == 1
        assert "kafka" in errors[0].message

    def test_valid_secrets_choices(self):
        for val in ("env", "dotenv", "postgresql"):
            result = validate_env(env={"LOOM_SECRETS": val})
            errors = [e for e in result.errors if e.field == "LOOM_SECRETS"]
            assert errors == [], f"{val!r} should be accepted"

    def test_invalid_secrets_choice(self):
        result = validate_env(env={"LOOM_SECRETS": "vault"})
        errors = [e for e in result.errors if e.field == "LOOM_SECRETS"]
        assert len(errors) == 1

    def test_valid_embedding_choices(self):
        for val in ("noop", "openai", "litellm"):
            result = validate_env(env={"LOOM_EMBEDDING": val})
            errors = [e for e in result.errors if e.field == "LOOM_EMBEDDING"]
            assert errors == [], f"{val!r} should be accepted"

    def test_invalid_embedding_choice(self):
        result = validate_env(env={"LOOM_EMBEDDING": "huggingface"})
        errors = [e for e in result.errors if e.field == "LOOM_EMBEDDING"]
        assert len(errors) == 1

    def test_valid_search_choices(self):
        for val in ("memory", "postgresql"):
            result = validate_env(env={"LOOM_SEARCH": val})
            errors = [e for e in result.errors if e.field == "LOOM_SEARCH"]
            assert errors == []

    def test_valid_graph_choices(self):
        for val in ("disabled", "memory", "orientdb"):
            result = validate_env(env={"LOOM_GRAPH": val})
            errors = [e for e in result.errors if e.field == "LOOM_GRAPH"]
            assert errors == []

    def test_valid_tools_choices(self):
        for val in ("disabled", "memory"):
            result = validate_env(env={"LOOM_TOOLS": val})
            errors = [e for e in result.errors if e.field == "LOOM_TOOLS"]
            assert errors == []

    def test_valid_resources_choices(self):
        for val in ("disabled", "memory"):
            result = validate_env(env={"LOOM_RESOURCES": val})
            errors = [e for e in result.errors if e.field == "LOOM_RESOURCES"]
            assert errors == []


# ── Defaults ────────────────────────────────────────────────────────────


class TestDefaults:
    def test_dev_defaults_all_memory(self):
        result = validate_env(Environment.DEV, env={})
        assert result.valid
        assert result.resolved["LOOM_STORAGE"] == "memory"
        assert result.resolved["LOOM_QUEUE"] == "memory"
        assert result.resolved["LOOM_SECRETS"] == "env"
        assert result.resolved["LOOM_EMBEDDING"] == "noop"
        assert result.resolved["LOOM_SEARCH"] == "memory"
        assert result.resolved["LOOM_GRAPH"] == "disabled"

    def test_test_defaults_all_memory(self):
        result = validate_env(Environment.TEST, env={})
        assert result.valid
        assert result.resolved["LOOM_STORAGE"] == "memory"
        assert result.resolved["LOOM_QUEUE"] == "memory"

    def test_prod_defaults_external_backends(self):
        result = validate_env(Environment.PROD, env={})
        assert result.valid
        assert result.resolved["LOOM_STORAGE"] == "postgresql"
        assert result.resolved["LOOM_QUEUE"] == "redis"
        assert result.resolved["LOOM_SEARCH"] == "postgresql"
        assert result.resolved["LOOM_SECRETS"] == "postgresql"
        assert result.resolved["LOOM_EMBEDDING"] == "openai"

    def test_explicit_value_overrides_default(self):
        result = validate_env(
            Environment.PROD,
            env={"LOOM_STORAGE": "memory"},
        )
        assert result.resolved["LOOM_STORAGE"] == "memory"

    def test_defaults_for_dev(self):
        v = LoomConfigValidator(Environment.DEV)
        d = v.defaults_for()
        assert d["LOOM_STORAGE"] == "memory"
        assert d["LOOM_PORT"] == "5000"

    def test_defaults_for_prod(self):
        v = LoomConfigValidator(Environment.DEV)
        d = v.defaults_for(Environment.PROD)
        assert d["LOOM_STORAGE"] == "postgresql"
        assert d["LOOM_QUEUE"] == "redis"


# ── Type validation ─────────────────────────────────────────────────────


class TestTypeValidation:
    def test_port_valid_integer(self):
        result = validate_env(env={"LOOM_PORT": "8080"})
        errors = [e for e in result.errors if e.field == "LOOM_PORT"]
        assert errors == []

    def test_port_non_integer_rejected(self):
        result = validate_env(env={"LOOM_PORT": "abc"})
        errors = [e for e in result.errors if e.field == "LOOM_PORT"]
        assert len(errors) == 1
        assert "expected integer" in errors[0].message

    def test_port_float_string_rejected(self):
        result = validate_env(env={"LOOM_PORT": "80.5"})
        errors = [e for e in result.errors if e.field == "LOOM_PORT"]
        assert len(errors) == 1

    def test_port_range_low_boundary(self):
        result = validate_env(env={"LOOM_PORT": "1"})
        errors = [e for e in result.errors if e.field == "LOOM_PORT"]
        assert errors == []

    def test_port_range_high_boundary(self):
        result = validate_env(env={"LOOM_PORT": "65535"})
        errors = [e for e in result.errors if e.field == "LOOM_PORT"]
        assert errors == []

    def test_port_zero_rejected(self):
        result = validate_env(env={"LOOM_PORT": "0"})
        errors = [e for e in result.errors if e.field == "LOOM_PORT"]
        assert len(errors) == 1
        assert "outside valid range" in errors[0].message

    def test_port_negative_rejected(self):
        result = validate_env(env={"LOOM_PORT": "-1"})
        errors = [e for e in result.errors if e.field == "LOOM_PORT"]
        assert len(errors) == 1

    def test_port_too_large_rejected(self):
        result = validate_env(env={"LOOM_PORT": "70000"})
        errors = [e for e in result.errors if e.field == "LOOM_PORT"]
        assert len(errors) == 1


# ── Dependencies ────────────────────────────────────────────────────────


class TestDependencies:
    def test_dotenv_empty_file_path_rejected(self):
        result = validate_env(
            env={
                "LOOM_SECRETS": "dotenv",
                "LOOM_SECRETS_FILE": "",
            }
        )
        errors = [e for e in result.errors if e.field == "LOOM_SECRETS_FILE"]
        assert len(errors) == 1
        assert "non-empty" in errors[0].message

    def test_dotenv_with_file_path_accepted(self):
        result = validate_env(
            env={
                "LOOM_SECRETS": "dotenv",
                "LOOM_SECRETS_FILE": "/tmp/.env",
            }
        )
        errors = [e for e in result.errors if e.field == "LOOM_SECRETS_FILE"]
        assert errors == []

    def test_dotenv_default_file_path_accepted(self):
        result = validate_env(env={"LOOM_SECRETS": "dotenv"})
        errors = [e for e in result.errors if e.field == "LOOM_SECRETS_FILE"]
        assert errors == []

    def test_empty_llm_base_url_rejected(self):
        result = validate_env(env={"LOOM_LLM_BASE_URL": ""})
        errors = [e for e in result.errors if e.field == "LOOM_LLM_BASE_URL"]
        assert len(errors) == 1
        assert "non-empty URL" in errors[0].message

    def test_llm_base_url_accepted(self):
        result = validate_env(env={"LOOM_LLM_BASE_URL": "http://localhost:8080"})
        errors = [e for e in result.errors if e.field == "LOOM_LLM_BASE_URL"]
        assert errors == []


# ── Environment warnings ────────────────────────────────────────────────


class TestEnvironmentWarnings:
    def test_prod_memory_storage_warns(self):
        result = validate_env(
            Environment.PROD,
            env={"LOOM_STORAGE": "memory"},
        )
        assert any("LOOM_STORAGE" in w and "production" in w for w in result.warnings)

    def test_prod_memory_queue_warns(self):
        result = validate_env(
            Environment.PROD,
            env={"LOOM_QUEUE": "memory"},
        )
        assert any("LOOM_QUEUE" in w and "production" in w for w in result.warnings)

    def test_prod_env_secrets_warns(self):
        result = validate_env(
            Environment.PROD,
            env={"LOOM_SECRETS": "env"},
        )
        assert any("LOOM_SECRETS" in w and "production" in w for w in result.warnings)

    def test_prod_memory_search_warns(self):
        result = validate_env(
            Environment.PROD,
            env={"LOOM_SEARCH": "memory"},
        )
        assert any("LOOM_SEARCH" in w and "production" in w for w in result.warnings)

    def test_dev_memory_storage_no_warning(self):
        result = validate_env(
            Environment.DEV,
            env={"LOOM_STORAGE": "memory"},
        )
        assert not any("production" in w for w in result.warnings)

    def test_test_memory_storage_no_warning(self):
        result = validate_env(
            Environment.TEST,
            env={"LOOM_STORAGE": "memory"},
        )
        assert not any("production" in w for w in result.warnings)

    def test_prod_postgresql_storage_no_warning(self):
        result = validate_env(
            Environment.PROD,
            env={"LOOM_STORAGE": "postgresql"},
        )
        assert not any("LOOM_STORAGE" in w for w in result.warnings)


# ── Required fields ─────────────────────────────────────────────────────


class TestRequiredFields:
    def test_required_field_missing(self):
        spec = FieldSpec(name="MUST_HAVE", value_type=str, required=True)
        v = LoomConfigValidator(fields=(spec,))
        result = v.validate(env={})
        assert not result.valid
        errors = [e for e in result.errors if e.field == "MUST_HAVE"]
        assert len(errors) == 1
        assert "required" in errors[0].message

    def test_required_field_present(self):
        spec = FieldSpec(name="MUST_HAVE", value_type=str, required=True)
        v = LoomConfigValidator(fields=(spec,))
        result = v.validate(env={"MUST_HAVE": "value"})
        assert result.valid


# ── Custom fields ───────────────────────────────────────────────────────


class TestCustomFields:
    def test_custom_field_set(self):
        spec = FieldSpec(
            name="CUSTOM",
            value_type=str,
            choices=("x", "y"),
            default="x",
        )
        v = LoomConfigValidator(fields=(spec,))
        result = v.validate(env={})
        assert result.valid
        assert result.resolved["CUSTOM"] == "x"

    def test_custom_field_invalid(self):
        spec = FieldSpec(
            name="CUSTOM",
            value_type=str,
            choices=("x", "y"),
        )
        v = LoomConfigValidator(fields=(spec,))
        result = v.validate(env={"CUSTOM": "z"})
        assert not result.valid


# ── LoomConfigValidator ─────────────────────────────────────────────────


class TestLoomConfigValidator:
    def test_environment_property(self):
        v = LoomConfigValidator(Environment.PROD)
        assert v.environment == Environment.PROD

    def test_empty_env_valid_for_dev(self):
        v = LoomConfigValidator(Environment.DEV)
        result = v.validate(env={})
        assert result.valid

    def test_all_fields_covered(self):
        names = {f.name for f in ALL_FIELDS}
        expected = {
            "LOOM_STORAGE",
            "LOOM_QUEUE",
            "LOOM_SECRETS",
            "LOOM_EMBEDDING",
            "LOOM_SEARCH",
            "LOOM_GRAPH",
            "LOOM_TOOLS",
            "LOOM_RESOURCES",
            "LOOM_LLM_BASE_URL",
            "LOOM_LLM_API_KEY",
            "LOOM_LLM_MODEL",
            "LOOM_LLM_PROVIDER",
            "LOOM_SECRETS_FILE",
            "LOOM_SECRETS_PREFIX",
            "LOOM_PORT",
            "LOOM_API_KEY",
        }
        assert names == expected

    def test_multiple_errors_reported(self):
        result = validate_env(
            env={
                "LOOM_STORAGE": "bad",
                "LOOM_QUEUE": "bad",
                "LOOM_PORT": "abc",
            }
        )
        assert not result.valid
        assert len(result.errors) >= 3

    def test_resolved_includes_explicit_and_defaults(self):
        result = validate_env(
            Environment.DEV,
            env={"LOOM_STORAGE": "postgresql"},
        )
        assert result.resolved["LOOM_STORAGE"] == "postgresql"
        assert result.resolved["LOOM_QUEUE"] == "memory"


# ── validate_env convenience ────────────────────────────────────────────


class TestValidateEnv:
    def test_returns_validation_result(self):
        result = validate_env(env={})
        assert isinstance(result, ValidationResult)

    def test_defaults_to_dev(self):
        result = validate_env(env={})
        assert result.valid
        assert result.resolved.get("LOOM_STORAGE") == "memory"


# ── format_errors ───────────────────────────────────────────────────────


class TestFormatErrors:
    def test_valid_config_message(self):
        result = ValidationResult(valid=True)
        assert format_errors(result) == "Configuration is valid."

    def test_error_message_includes_field(self):
        result = ValidationResult(
            valid=False,
            errors=[ValidationError(field="LOOM_PORT", message="bad value")],
        )
        text = format_errors(result)
        assert "LOOM_PORT" in text
        assert "bad value" in text

    def test_error_message_includes_value(self):
        result = ValidationResult(
            valid=False,
            errors=[
                ValidationError(field="X", message="wrong", value="abc"),
            ],
        )
        text = format_errors(result)
        assert "'abc'" in text

    def test_warnings_included(self):
        result = ValidationResult(
            valid=False,
            errors=[ValidationError(field="X", message="err")],
            warnings=["something to watch"],
        )
        text = format_errors(result)
        assert "Warnings:" in text
        assert "something to watch" in text

    def test_no_warnings_when_valid(self):
        result = ValidationResult(valid=True, warnings=["w"])
        assert "Warnings" not in format_errors(result)


# ── Environment enum ────────────────────────────────────────────────────


class TestEnvironment:
    def test_values(self):
        assert Environment.DEV.value == "dev"
        assert Environment.PROD.value == "prod"
        assert Environment.TEST.value == "test"

    def test_from_string(self):
        assert Environment("dev") == Environment.DEV
        assert Environment("prod") == Environment.PROD
        assert Environment("test") == Environment.TEST

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            Environment("staging")
