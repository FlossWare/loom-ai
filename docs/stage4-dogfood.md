# Stage 4: real repository task dogfood

Stage 4 is executable implementation dogfood for the Python realization of the Loom AI contracts. It is maintained in `FlossWare/loom-ai-python`, not in this contract repository.

The deterministic task exercises a real repository operation through the Python implementation's HTTP boundary:

```text
HTTP client
  -> Python Loom Server
      -> Intent
          -> Arbiter
              -> Inspect Worker
              -> Planning Worker
              -> Implementation Worker
              -> Verification Worker
          -> Result + evidence
```

The task uses an isolated temporary fixture so it exercises real filesystem behavior without modifying the checkout. It verifies submission, Intent provenance, worker completion, acceptance, evidence, and the expected file change.

No Crush, LLM, model routing, or local inference is involved. Model-backed planning belongs to later implementation stages and remains outside the foundational Loom contract.

## Contract relevance

The executable test is an implementation qualification of the language-neutral semantics defined by `loom-ai`. Changes to the semantic contract belong here; changes to Python runtime mechanics belong in `loom-ai-python`.

See the Python implementation repository for the executable Stage 4 dogfood entry point.
