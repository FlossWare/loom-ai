#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$ROOT" ]] || { echo "FAIL: run inside the Loom checkout" >&2; exit 1; }
cd "$ROOT"

PY=.venv/bin/python
[[ -x "$PY" ]] || { echo "FAIL: .venv/bin/python is required" >&2; exit 1; }

SERVICE="${LOOM_SYSTEMD_SERVICE:-loom.service}"
BASE="${LOOM_SERVER_URL:-http://127.0.0.1:18000}"

systemctl is-active --quiet "$SERVICE" || {
    echo "FAIL: $SERVICE is not active" >&2
    exit 1
}

check_health() {
    "$PY" - "$BASE" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1]
with urllib.request.urlopen(f"{base}/health", timeout=5) as response:
    assert response.status == 200
    assert json.load(response) == {"status": "ok"}
PY
}

run_intent() {
    "$PY" - "$BASE" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1]
payload = {
    "title": "Stage 3 real worker dogfood",
    "goal": "Execute a bounded real worker task through the Loom server.",
    "acceptance": [
        "The artifact writer creates the deterministic artifact.",
        "The artifact verifier confirms the artifact matches the Intent.",
    ],
}
request = urllib.request.Request(
    f"{base}/intents",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=5) as response:
    result = json.load(response)

assert result["status"] == "success", result
workers = result["output"]
assert [worker["worker_id"] for worker in workers] == [
    "artifact-writer",
    "artifact-verifier",
], result
assert all(worker["status"] == "success" for worker in workers), result
evidence_types = [item["type"] for item in result["evidence"] if "type" in item]
assert "artifact-written" in evidence_types, result
assert "artifact-verified" in evidence_types, result
print("intent: success")
print("execution: success")
print("verification: success")
PY
}

check_health
printf '%s\n' "health: success"
run_intent

systemctl restart "$SERVICE"
for _ in {1..50}; do
    if check_health >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done
check_health
printf '%s\n' "restart: success"
run_intent
printf '%s\n' "recovery-execution: success"
printf '%s\n' "RESULT: LOOM STAGE 3 SERVER DOGFOOD PASSED"
