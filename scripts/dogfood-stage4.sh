#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

PY=${PYTHON:-python3}
TASK_ROOT=$(mktemp -d)
trap 'rm -rf "$TASK_ROOT"' EXIT

"$PY" -m pip install -e '.[dev,server]' >/dev/null
"$PY" -m ruff format --check .
"$PY" -m ruff check .
"$PY" -m pytest -q

"$PY" - "$TASK_ROOT" <<'PY'
import json
import pathlib
import subprocess
import sys

root = pathlib.Path.cwd()
task_root = pathlib.Path(sys.argv[1])
fixture = task_root / "stage4_fixture.py"
fixture.write_text("def value():\n    return 41\n", encoding="utf-8")

script = root / "scripts" / "stage4_task.py"
result = subprocess.run(
    [sys.executable, str(script), str(fixture)],
    check=False,
    text=True,
    capture_output=True,
)
if result.returncode:
    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    raise SystemExit(result.returncode)

payload = json.loads(result.stdout)
assert payload["status"] == "success"
assert payload["acceptance"] is True
assert payload["workers"] == ["inspect", "plan", "implement", "verify"]
assert payload["evidence"]
assert "return 42" in fixture.read_text(encoding="utf-8")

print("RESULT: LOOM STAGE 4 DOGFOOD PASSED")
PY
