"""Version compatibility and migration policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self


@dataclass(frozen=True, order=True)
class SchemaVersion:
    """Semantic version for schema compatibility."""

    major: int
    minor: int
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def parse(cls, s: str) -> Self:
        s = s.strip()
        parts = s.split(".")
        if len(parts) not in (2, 3):
            raise ValueError(f"Invalid version: {s!r}")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            raise ValueError(f"Non-numeric version: {s!r}")
        if len(nums) == 2:
            nums.append(0)
        return cls(*nums)

    def is_compatible_with(
        self,
        other: SchemaVersion,
    ) -> bool:
        return self.major == other.major


@dataclass
class VersionedRecord:
    """A persisted record with schema version."""

    schema_version: str
    record_type: str
    created_at: str
    data: dict[str, Any]


@dataclass(frozen=True)
class EmbeddingSpec:
    """Embedding model identity and dimensions."""

    model_name: str
    dimensions: int

    def is_compatible_with(
        self,
        other: EmbeddingSpec,
    ) -> bool:
        return (
            self.model_name == other.model_name and self.dimensions == other.dimensions
        )


@dataclass
class CompatResult:
    """Outcome of a compatibility check."""

    compatible: bool
    needs_migration: bool = False
    message: str = ""
    breaking_changes: list[str] = field(
        default_factory=list,
    )


@dataclass
class MigrationStep:
    """A single migration between versions."""

    from_version: SchemaVersion
    to_version: SchemaVersion
    description: str
    reversible: bool = True


class MigrationPlan:
    """Ordered list of migration steps."""

    def __init__(self) -> None:
        self._steps: list[MigrationStep] = []

    def add_step(
        self,
        step: MigrationStep,
    ) -> None:
        self._steps.append(step)

    def steps_between(
        self,
        from_ver: SchemaVersion,
        to_ver: SchemaVersion,
    ) -> list[MigrationStep]:
        return [
            s
            for s in self._steps
            if s.from_version >= from_ver and s.to_version <= to_ver
        ]

    @property
    def steps(self) -> list[MigrationStep]:
        return list(self._steps)


class CompatibilityChecker:
    """Check compatibility of records and specs."""

    def __init__(
        self,
        current_version: SchemaVersion,
    ) -> None:
        self._current = current_version
        self.migration_plan = MigrationPlan()

    def check_record(
        self,
        record: VersionedRecord,
    ) -> CompatResult:
        try:
            rec_ver = SchemaVersion.parse(
                record.schema_version,
            )
        except ValueError:
            return CompatResult(
                compatible=False,
                message="Invalid schema version",
                breaking_changes=[
                    "Invalid schema version format",
                ],
            )

        if not rec_ver.is_compatible_with(
            self._current,
        ):
            return CompatResult(
                compatible=False,
                message="Incompatible major version",
                breaking_changes=[
                    "Major version mismatch",
                ],
            )

        needs = rec_ver < self._current
        return CompatResult(
            compatible=True,
            needs_migration=needs,
            message=("Migration needed" if needs else "Compatible"),
        )

    def check_embedding(
        self,
        stored: EmbeddingSpec,
        current: EmbeddingSpec,
    ) -> CompatResult:
        if stored.is_compatible_with(current):
            return CompatResult(
                compatible=True,
                message="Compatible",
            )
        changes: list[str] = []
        if stored.model_name != current.model_name:
            changes.append("Model name mismatch")
        if stored.dimensions != current.dimensions:
            changes.append("Dimensions mismatch")
        return CompatResult(
            compatible=False,
            message="Embedding specs mismatch",
            breaking_changes=changes,
        )

    def check_upgrade_path(
        self,
        from_ver: SchemaVersion,
        to_ver: SchemaVersion,
    ) -> CompatResult:
        if from_ver.major != to_ver.major:
            return CompatResult(
                compatible=False,
                message="Major version change",
                breaking_changes=[
                    "Major version change",
                ],
            )
        steps = self.migration_plan.steps_between(
            from_ver,
            to_ver,
        )
        if steps:
            return CompatResult(
                compatible=True,
                needs_migration=True,
                message="Upgrade path available",
            )
        return CompatResult(
            compatible=True,
            message="No migration needed",
        )
