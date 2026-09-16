# Stage 4: real repository task dogfood

Stage 4 proves that Loom can execute a useful repository task through the HTTP server boundary without requiring an LLM or model provider.

The deterministic task follows:

```text
HTTP client
  -> Loom Server
      -> Intent
          -> Arbiter
              -> Inspect Worker
              -> Planning Worker
              -> Implementation Worker
              -> Verification Worker
          -> Result + evidence
```

The dogfood uses an isolated temporary fixture so it exercises real filesystem behavior without modifying the Loom checkout. The task is intentionally small: inspect a Python file, plan a replacement, apply it, and verify the acceptance condition.

The gate checks that:

- the task is submitted via `POST /intents`;
- Intent provenance carries the task path through the server boundary;
- inspection, planning, implementation, and verification all succeed;
- the acceptance condition is true;
- evidence is present in the returned result;
- the expected file change actually occurred.

No Crush, LLM, model routing, or local inference is involved. Model-backed planning belongs to a later stage and remains outside Loom core.
