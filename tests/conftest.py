from __future__ import annotations

from pathlib import Path

import pytest

from tests.markers import BACKEND_GROUPS


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    file_to_groups: dict[str, list[str]] = {}
    for group, files in BACKEND_GROUPS.items():
        for filepath in files:
            file_to_groups.setdefault(filepath, []).append(group)

    rootpath = Path(config.rootpath)
    for item in items:
        rel = Path(item.fspath).relative_to(rootpath).as_posix()
        for group in file_to_groups.get(rel, []):
            item.add_marker(getattr(pytest.mark, group))
