#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$ROOT" ]] || { echo "FAIL: run inside the Loom checkout" >&2; exit 1; }
cd "$ROOT"

command -v python3 >/dev/null 2>&1 || { echo "FAIL: python3 is required" >&2; exit 1; }
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' || { echo "FAIL: Python 3.11+ is required" >&2; exit 1; }

BASE_URL="${LOOM_LLM_BASE_URL:-http://127.0.0.1:8765/v1}"
MODEL="${LOOM_LLM_MODEL:-flossware}"
API_KEY="${LOOM_LLM_API_KEY:-}"
export LOOM_STAGE2_ROOT="$ROOT" LOOM_STAGE2_BASE_URL="$BASE_URL" LOOM_STAGE2_MODEL="$MODEL" LOOM_STAGE2_API_KEY="$API_KEY"

[[ -x .venv/bin/python ]] || python3 -m venv .venv
PY=.venv/bin/python
"$PY" -m pip install --quiet -e '.[dev]'

"$PY" - <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from loom_ai import (
    Arbiter,
    ArbiterDecision,
    Intent,
    WorkerContext,
    WorkerEvaluation,
    WorkerResult,
    WorkerStatus,
)

ROOT = Path(os.environ["LOOM_STAGE2_ROOT"])
TEST_FILE = ROOT / "tests" / "test_worker_arbiter.py"
MARKER = "test_worker_result_successful_property"
BASE_URL = os.environ["LOOM_STAGE2_BASE_URL"].rstrip("/")
MODEL = os.environ["LOOM_STAGE2_MODEL"]
API_KEY = os.environ["LOOM_STAGE2_API_KEY"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def ask_model(source: str) -> dict:
    prompt = f'''You are the planning worker in a small software-execution system.
Inspect this Python test file and choose the smallest useful regression-test action.
The only allowed action is "add_successful_regression_test" when coverage for
WorkerResult.successful is absent. Otherwise choose "no_change".
Return JSON only with keys action and reason.

File: tests/test_worker_arbiter.py

{source}
'''
    payload = {
        "model": MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    }
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"LLM gateway unavailable at {BASE_URL}: {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content)
        return json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LLM returned an invalid planning response: {body!r}") from exc


class InspectWorker:
    worker_id = "inspect"

    def execute(self, context: WorkerContext) -> WorkerResult:
        text = TEST_FILE.read_text()
        return WorkerResult(
            worker_id=self.worker_id,
            status=WorkerStatus.SUCCESS,
            output={"test_file": str(TEST_FILE)},
            evidence=({"worker": self.worker_id, "source": text},),
        )


class LLMPlanningWorker:
    worker_id = "llm-planner"

    def execute(self, context: WorkerContext) -> WorkerResult:
        source = context.evidence[-1]["source"]
        plan = ask_model(source)
        if plan.get("action") not in {"add_successful_regression_test", "no_change"}:
            return WorkerResult(
                worker_id=self.worker_id,
                status=WorkerStatus.FAILED,
                error=f"unsupported LLM action: {plan!r}",
            )
        return WorkerResult(
            worker_id=self.worker_id,
            status=WorkerStatus.SUCCESS,
            output=plan,
            evidence=({"worker": self.worker_id, "plan": plan},),
        )


class ImplementationWorker:
    worker_id = "implementation"

    def execute(self, context: WorkerContext) -> WorkerResult:
        plan = context.evidence[-1].get("plan", {})
        action = plan.get("action")
        text = TEST_FILE.read_text()
        if action == "no_change":
            return WorkerResult(
                worker_id=self.worker_id,
                status=WorkerStatus.SUCCESS,
                output="LLM selected no_change",
                evidence=({"worker": self.worker_id, "changed": False},),
            )
        if action != "add_successful_regression_test":
            return WorkerResult(
                worker_id=self.worker_id,
                status=WorkerStatus.FAILED,
                error=f"implementation rejected action: {action!r}",
            )
        if MARKER in text:
            return WorkerResult(
                worker_id=self.worker_id,
                status=WorkerStatus.SUCCESS,
                output="regression test already present",
                evidence=({"worker": self.worker_id, "changed": False},),
            )
        addition = '''\n\n\ndef test_worker_result_successful_property():\n    """Verify successful reflects WorkerStatus.SUCCESS only."""\n    success = WorkerResult(worker_id="success", status=WorkerStatus.SUCCESS)\n    failure = WorkerResult(worker_id="failure", status=WorkerStatus.FAILED)\n\n    assert success.successful\n    assert not failure.successful\n'''
        TEST_FILE.write_text(text.rstrip() + addition)
        return WorkerResult(
            worker_id=self.worker_id,
            status=WorkerStatus.SUCCESS,
            output=f"updated {TEST_FILE}",
            evidence=({"worker": self.worker_id, "changed": True, "action": action},),
        )


class VerificationWorker:
    worker_id = "verification"

    def execute(self, context: WorkerContext) -> WorkerResult:
        text = TEST_FILE.read_text()
        result = run("python", "-m", "pytest", "-q")
        expected = MARKER in text
        if result.returncode != 0 or not expected:
            return WorkerResult(
                worker_id=self.worker_id,
                status=WorkerStatus.FAILED,
                output=result.stdout,
                error=result.stderr[-4000:] or "expected regression test is missing",
            )
        return WorkerResult(
            worker_id=self.worker_id,
            status=WorkerStatus.SUCCESS,
            output=result.stdout,
            evidence=({"worker": self.worker_id, "returncode": result.returncode},),
        )


intent = Intent(
    title="Stage 2 LLM-backed Loom dogfood",
    goal="Use an LLM Worker to choose a small regression-test action, execute it safely, and verify the repository.",
    requirements=(
        "Inspect the target test file.",
        "Ask an external LLM for a constrained implementation plan.",
        "Accept only a declared action from the LLM.",
        "Keep filesystem modification deterministic and outside the LLM.",
        "Verify the resulting repository with pytest.",
    ),
    constraints=(
        "The Loom core must remain unchanged.",
        "The LLM may choose an action but may not directly edit files.",
        "The implementation worker must reject unsupported actions.",
    ),
    acceptance=(
        "The LLM planner returns a supported action.",
        "The implementation follows that action.",
        "The post-change test suite passes.",
    ),
)

workers = [InspectWorker(), LLMPlanningWorker(), ImplementationWorker(), VerificationWorker()]


def evaluate(result: WorkerResult, _context: WorkerContext) -> WorkerEvaluation:
    if not result.successful:
        return WorkerEvaluation(ArbiterDecision.REPLAN, reason=result.error or "worker failed")
    if result.worker_id == "verification":
        return WorkerEvaluation(ArbiterDecision.COMPLETE, reason="acceptance criteria satisfied")
    return WorkerEvaluation(ArbiterDecision.CONTINUE)


print(f"Intent: {intent.goal}")
print(f"LLM: {MODEL} via {BASE_URL}")
result = Arbiter(workers, evaluate, max_retries=0).execute(
    WorkerContext(intent=intent, state={"repository": str(ROOT)})
)

for output in result.output:
    print(f"{output.worker_id:>18}: {output.status.value}")
    if output.worker_id == "llm-planner" and output.output:
        print(f"{'LLM plan':>18}: {output.output}")

if not result.successful:
    raise SystemExit(f"Stage 2 failed: {result.error}")

print("\nRESULT: LOOM STAGE 2 DOGFOOD PASSED")
PY

printf '\nNOTE: Stage 2 intentionally leaves the test-only change in the checkout.\n'
printf 'Review it with: git diff -- tests/test_worker_arbiter.py\n'
