# Loom Demo Runbook

## Prerequisites

| Item | Requirement | How to satisfy |
|------|-------------|----------------|
| Python | **3.10** or newer | `python --version` |
| Loom-AI package | Latest development version | `pip install -e .` (run from repo root) |
| Environment variables | Optional -- choose storage backend | `export LOOM_STORAGE=postgresql` to use PostgreSQL, otherwise defaults to in-memory |
| Workspace | Local checkout of a GitHub repo containing the target issue | `git clone https://github.com/owner/repo.git && cd repo` |
| Issue number | Valid GitHub issue that the agent can resolve | e.g. `123` |

When using PostgreSQL, ensure the database is reachable and the `DATABASE_URL` variable is set (e.g. `postgresql://user:pass@host/db`).

## Session 1 -- Resolve an Issue and Persist Knowledge

### Start

Record the starting commit so the demonstration is reproducible.

```bash
python -m loom_ai.demo_agent --issue 123 --workspace /path/to/repo
```

### Observe

Capture evidence that Loom:

- discovers relevant repository context
- uses tools rather than fabricating repository state
- modifies the intended files
- runs tests
- produces a useful summary
- persists the session/knowledge

Expected output:

```
[DemoAgent] Issue #123: <title>
[DemoAgent] Resolution steps: ...
[DemoAgent] Knowledge persisted (session_id=...)
```

### Verify persistence

```python
from loom_ai.session_persistence import SessionManager
sm = SessionManager()
print(sm.list_sessions())            # should contain the current session_id
print(sm.get_knowledge(session_id))   # should show the knowledge generated above
```

If `LOOM_STORAGE=postgresql`, query the `sessions` table to see the row.

### End

Terminate the Loom process/session completely (Ctrl-C or SIGTERM).

Do not provide Session 2 with the Session 1 transcript.

## Session 2 -- Recover Knowledge and Continue

Start a fresh Loom process/session for the same project:

```bash
python -m loom_ai.demo_agent --issue 123 --workspace /path/to/repo
```

### Agent recovery

On start-up the agent loads the most recent session from `SessionManager`.

Expected log excerpt:

```
[DemoAgent] Loaded previous session (session_id=...) with 1 knowledge items
[DemoAgent] Summarizing previous work: ...
```

### Follow-up verification

Ask:

> What did we learn while working on the previous issue? Explain the problem, why we made the change, what files were involved, and what evidence we have that it works.

Then ask:

> What should I be careful about if I modify this component again?

The response should be based on persisted Loom knowledge and cite or otherwise expose its provenance where supported.

### Confirm updated persistence

```python
from loom_ai.session_persistence import SessionManager
sm = SessionManager()
knowledge = sm.get_knowledge(session_id)
print(len(knowledge))   # should be >= 2 (original + follow-up)
```

## Verification Checklist

- [ ] Python 3.10+ is active.
- [ ] `loom_ai` package installed in editable mode.
- [ ] `LOOM_STORAGE` set correctly (or omitted for in-memory).
- [ ] Issue number exists and is reachable.
- [ ] Session 1 logs show "Knowledge persisted".
- [ ] `SessionManager.list_sessions()` returns a session ID after Session 1.
- [ ] Process is killed cleanly.
- [ ] Session 2 logs show "Loaded previous session".
- [ ] Follow-up output references Session 1 work.
- [ ] Knowledge count after Session 2 >= 2.

## Persistence Backends

| Backend | Characteristics | When to use |
|---------|-----------------|-------------|
| **InMemoryPersistentMemory** (default) | Stores data only for the lifetime of the Python process; data survives only if the same process re-creates the `SessionManager` within the same interpreter session. | Quick demos, CI runs, no external services. |
| **PostgreSQL** (`LOOM_STORAGE=postgresql`) | Persists across process restarts, containers, and machines. Requires a reachable PostgreSQL instance and `DATABASE_URL`. | Production-like testing, multi-node demos, long-term knowledge retention. |

If you switch from in-memory to PostgreSQL, clear any stale in-memory sessions by restarting the interpreter before rerunning the demo.

## Dogfood

After validating the memory boundary, give Loom a follow-up issue that improves Loom itself.

The follow-up should deliberately touch an area revealed as weak during the demonstration.

Examples:

- context retrieval quality
- persistent session behavior
- tool error handling
- provenance
- knowledge extraction
- test coverage

This creates the first dogfood loop:

```text
Loom builds Loom
      |
Loom discovers limitations
      |
Loom records the lessons
      |
Loom improves itself
      |
repeat
```

## Failure handling

A failed demo is useful if the failure is captured precisely.

Record:

- task
- session
- model/provider
- tool used
- expected behavior
- actual behavior
- missing context/knowledge
- relevant logs or test output

Create or update a GitHub issue rather than silently working around the limitation.

## Demo discipline

Do not add major architecture solely to make the demonstration look impressive. The demo should reveal what Loom can actually do today.
