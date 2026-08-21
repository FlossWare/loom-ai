"""Tests for version compatibility and migration."""

from __future__ import annotations

import pytest

from loom_ai.compat import (
    CompatibilityChecker,
    EmbeddingSpec,
    MigrationPlan,
    MigrationStep,
    SchemaVersion,
    VersionedRecord,
)


def test_schema_version_parse_str_roundtrip():
    v = SchemaVersion.parse("1.2.3")
    assert str(v) == "1.2.3"
    assert v == SchemaVersion(1, 2, 3)


def test_schema_version_parse_two_parts():
    v = SchemaVersion.parse("2.5")
    assert v == SchemaVersion(2, 5, 0)


def test_schema_version_ordering():
    assert SchemaVersion(1, 0, 0) < SchemaVersion(1, 1, 0)
    assert SchemaVersion(1, 1, 0) < SchemaVersion(1, 1, 1)
    assert SchemaVersion(1, 9, 9) < SchemaVersion(2, 0, 0)


def test_schema_version_compatible_same_major():
    assert SchemaVersion(1, 2, 3).is_compatible_with(
        SchemaVersion(1, 5, 0),
    )


def test_schema_version_incompatible_diff_major():
    assert not SchemaVersion(1, 0, 0).is_compatible_with(
        SchemaVersion(2, 0, 0),
    )


def test_schema_version_parse_invalid():
    with pytest.raises(ValueError):
        SchemaVersion.parse("invalid")


def test_schema_version_parse_whitespace():
    v = SchemaVersion.parse("  1.0.0  ")
    assert v == SchemaVersion(1, 0, 0)


def test_versioned_record_fields():
    r = VersionedRecord(
        schema_version="1.0.0",
        record_type="session",
        created_at="2026-01-01",
        data={"key": "val"},
    )
    assert r.schema_version == "1.0.0"
    assert r.record_type == "session"
    assert r.data == {"key": "val"}


def test_embedding_spec_compatible():
    a = EmbeddingSpec("all-MiniLM-L6-v2", 384)
    b = EmbeddingSpec("all-MiniLM-L6-v2", 384)
    assert a.is_compatible_with(b)


def test_embedding_spec_diff_dims():
    a = EmbeddingSpec("model", 128)
    b = EmbeddingSpec("model", 256)
    assert not a.is_compatible_with(b)


def test_embedding_spec_diff_model():
    a = EmbeddingSpec("model-a", 128)
    b = EmbeddingSpec("model-b", 128)
    assert not a.is_compatible_with(b)


def test_checker_record_compatible():
    c = CompatibilityChecker(SchemaVersion(1, 2, 0))
    r = VersionedRecord("1.2.0", "s", "d", {})
    res = c.check_record(r)
    assert res.compatible
    assert not res.needs_migration


def test_checker_record_needs_migration():
    c = CompatibilityChecker(SchemaVersion(1, 3, 0))
    r = VersionedRecord("1.0.0", "s", "d", {})
    res = c.check_record(r)
    assert res.compatible
    assert res.needs_migration


def test_checker_record_breaking():
    c = CompatibilityChecker(SchemaVersion(2, 0, 0))
    r = VersionedRecord("1.5.0", "s", "d", {})
    res = c.check_record(r)
    assert not res.compatible
    assert "Major version mismatch" in res.breaking_changes


def test_checker_record_invalid_version():
    c = CompatibilityChecker(SchemaVersion(1, 0, 0))
    r = VersionedRecord("bad", "s", "d", {})
    res = c.check_record(r)
    assert not res.compatible


def test_checker_embedding_compatible():
    c = CompatibilityChecker(SchemaVersion(1, 0, 0))
    s = EmbeddingSpec("m", 128)
    res = c.check_embedding(s, EmbeddingSpec("m", 128))
    assert res.compatible


def test_checker_embedding_mismatch():
    c = CompatibilityChecker(SchemaVersion(1, 0, 0))
    res = c.check_embedding(
        EmbeddingSpec("a", 128),
        EmbeddingSpec("b", 256),
    )
    assert not res.compatible
    assert "Model name mismatch" in res.breaking_changes
    assert "Dimensions mismatch" in res.breaking_changes


def test_checker_upgrade_same_major():
    c = CompatibilityChecker(SchemaVersion(1, 2, 0))
    res = c.check_upgrade_path(
        SchemaVersion(1, 0, 0),
        SchemaVersion(1, 2, 0),
    )
    assert res.compatible


def test_checker_upgrade_diff_major():
    c = CompatibilityChecker(SchemaVersion(2, 0, 0))
    res = c.check_upgrade_path(
        SchemaVersion(1, 0, 0),
        SchemaVersion(2, 0, 0),
    )
    assert not res.compatible


def test_migration_step_fields():
    s = MigrationStep(
        SchemaVersion(1, 0, 0),
        SchemaVersion(1, 1, 0),
        "Add field",
    )
    assert s.reversible is True
    assert s.description == "Add field"


def test_migration_plan_add_and_list():
    p = MigrationPlan()
    s1 = MigrationStep(
        SchemaVersion(1, 0, 0),
        SchemaVersion(1, 1, 0),
        "s1",
    )
    s2 = MigrationStep(
        SchemaVersion(1, 1, 0),
        SchemaVersion(1, 2, 0),
        "s2",
    )
    p.add_step(s1)
    p.add_step(s2)
    assert len(p.steps) == 2


def test_migration_plan_steps_between():
    p = MigrationPlan()
    s1 = MigrationStep(
        SchemaVersion(1, 0, 0),
        SchemaVersion(1, 1, 0),
        "s1",
    )
    s2 = MigrationStep(
        SchemaVersion(1, 1, 0),
        SchemaVersion(1, 2, 0),
        "s2",
    )
    s3 = MigrationStep(
        SchemaVersion(2, 0, 0),
        SchemaVersion(2, 1, 0),
        "s3",
    )
    p.add_step(s1)
    p.add_step(s2)
    p.add_step(s3)
    between = p.steps_between(
        SchemaVersion(1, 0, 0),
        SchemaVersion(1, 2, 0),
    )
    assert len(between) == 2
    assert s3 not in between
