# Intent, Worker, and Arbiter

Loom's canonical execution model is intentionally small:

```text
Intent
  |
Worker
  |
Arbiter
 / | \
W  W  W
  |
result -> evidence -> evaluation
```

## Intent

`Intent` describes the desired outcome, requirements, constraints, and
acceptance criteria. It does not contain an execution plan, model choice,
provider configuration, or workflow definition.

Markdown is a human-friendly transport representation. The runtime contract
is the `Intent` value object so clients can submit intents through MCP, API,
CLI/TUI, files, or other adapters without coupling execution to Markdown.

## Worker

`Worker` is the fundamental executable abstraction:

```python
result = worker.execute(context)
```

Execution state is explicit in `WorkerContext`. A Worker does not need to
inherit from a Loom base class. Structural typing keeps implementations
independent of the runtime and provider ecosystem.

## Arbiter

`Arbiter` satisfies the same Worker contract. It is therefore a Composite,
not a second orchestration universe.

An Arbiter can coordinate one Worker or many Workers, including other
Arbiters. After each result it may complete, continue, retry, or replan by
adding further Workers.

This means fix/iterate, SDLC activities, verification retries, and larger
task graphs are ordinary Worker composition. They do not require a special
coding-agent or workflow subsystem.

## Boundaries

- `model-gateway` owns model/provider invocation and resource selection.
- `evaluation` owns outcome evaluation and reward signals.
- `knowledge` owns durable derived knowledge.
- `strategy` owns interchangeable decision strategies.
- Cross-cutting repositories provide resilience, budget, security,
  observability, streaming, and caching without becoming orchestrators.
- Loom owns Intent interpretation, Worker/Arbiter composition, execution
  state, evidence, and task-level orchestration.

The old Agent and Workflow abstractions are migration targets, not the
canonical Loom execution model.
