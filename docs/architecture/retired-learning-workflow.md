# Retired Learning and Workflow Extraction

**Date:** 2026-09-12

This document records what was intentionally retained from the historical `learning` and `workflow` repositories during the Loom consolidation.

## Learning

The old learning package combined:

- conversation feedback detection;
- task/outcome experience recording;
- derived learning extraction;
- Thompson Sampling reward state.

Those concerns now have separate owners:

- feedback observations -> `evaluation`;
- execution evidence/run history -> Loom + `storage`;
- durable derived knowledge -> `knowledge`;
- strategy state and optimization -> `strategy`.

The old `SimpleLearningExtractor` is therefore not a Loom primitive. It combined too many responsibilities and made the word "learning" do far too much work.

## Workflow

The old workflow engine provided sequential phases, status, persistence, resume, and worker results. The useful semantics are retained, but the workflow abstraction is not.

Loom replaces it with the smaller execution model:

```text
Intent
  -> Arbiter
      -> Worker
      -> Worker
      -> Arbiter
  -> evidence
  -> evaluation
  -> result
```

### Mapping

| Historical concept | Loom/capability |
| --- | --- |
| workflow phase | Worker |
| workflow engine | Arbiter |
| nested workflow | nested Arbiter |
| phase retry | Arbiter decision |
| dynamic continuation | Arbiter decision |
| replan | Arbiter decision |
| worker result | WorkerResult/evidence |
| execution persistence | checkpoint/replay + storage |
| status/progress | streaming + observability |
| outcome | evaluation |

The historical engine cached definitions in process memory, so resume worked only in the same process. Loom issue #961 intentionally replaces that limitation with durable checkpointing and replayable run history.

## Why nothing else was ported

Porting classes such as `WorkflowDefinition`, `WorkflowResult`, or `SimpleWorkflowEngine` would recreate the abstraction Loom was created to remove. Likewise, porting the combined learning extractor would recreate responsibility collisions that are now explicit repository boundaries.

The surviving implementation worth preserving from `learning` is the dependency-free conversation feedback matcher, now located in `evaluation`.

## Principle

The migration preserves **semantics**, not obsolete class hierarchies:

> Behavior is composable; execution state is explicit; capabilities own their contracts.

The historical repositories can therefore be archived without losing the architectural lessons or the one reusable implementation identified during extraction.
