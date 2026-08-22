# Command Model and Dataflow Research

**Status:** PARKED
**Priority:** High
**Revisit:** Before finalizing the Loom workflow DSL or object/data model

## Context

Historical `redhat-access` command-family projects created by Scot Floess may contain architectural patterns that are directly relevant to Loom. These projects should be treated as prior art from the same architect, not as unrelated legacy code.

The current Loom work identified a need for first-class objects/data, deterministic filters and transformations, and a workflow intermediate representation. The command-family architecture may already contain useful answers to some of these problems.

## Questions to investigate

- What constitutes a command?
- How are command inputs and outputs represented?
- What object/data types flow between commands?
- How are filters and predicates expressed?
- How are objects transformed, projected, selected, grouped, or aggregated?
- Can commands compose and chain naturally?
- How is execution represented?
- How does state/context propagate?
- How are errors and partial results propagated?
- Are operations lazy, eager, or both?
- Does the command model naturally form a graph/dataflow representation?
- Which concepts can become Loom primitives rather than being reinvented?

## Loom relevance

Potential prior art for:

- Loom object/value model
- Collections and streams
- Deterministic data operations
- Filters and predicates
- Transformations and projections
- Command/tool composition
- Execution graphs
- Workflow IR
- Typed agent inputs and outputs

## Important architectural distinction

Loom should separate deterministic data operations from model reasoning.

Examples of deterministic operations:

```text
filter
map
select
project
join
group
sort
aggregate
validate
deduplicate
```

Examples of reasoning operations:

```text
analyze
classify
infer
plan
decide
review
generate
```

The intended composition is therefore potentially:

```text
DATA → REASON → DATA → REASON → DATA
```

rather than routing every operation through an LLM.

## DSL and backtracking

Do **not** finalize the Loom DSL or backtracking semantics until this research and the underlying object/data model have been resolved.

Backtracking remains a future capability. It should eventually be modeled as search over workflow strategies/decision points, rather than merely retrying the same operation.

## Next step

Locate and review the relevant `redhat-access` command-family repositories and classes as a coherent architectural family. Compare their semantics against the Loom workflow model and identify concepts worth carrying forward.

## Decision

No architecture decision is made by this document. This is explicitly parked research and should inform a future ADR only after the historical implementation has been inspected and the Loom requirements are understood.
