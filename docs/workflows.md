# Loom Workflow Language

Loom workflows are **declarative AI work specifications**, not merely CI pipelines. A pipeline is one possible execution graph. A workflow can express a goal, facts, constraints, agents, dependencies, conditions, retries, verification, human approval, and policy.

The first runtime representation is `loom_ai.workflow_lang.WorkflowDefinition`. It compiles directly to the existing `ExecutionPlan`, so applications can adopt the model without replacing the proven DAG executor.

## Python

```python
from loom_ai.workflow_lang import WorkflowBuilder

workflow = (
    WorkflowBuilder("issue-to-pr", "Produce a production-ready PR")
    .fact("repository", "FlossWare/loom-ai")
    .constraint("tests must pass")
    .policy("max_iterations", 5)
    .node("inspect", "Inspect issue and repository", agent="analyst")
    .node("implement", "Implement verified fix", agent="developer", depends_on=["inspect"])
    .node("verify", "Run tests and review changes", agent="tester", depends_on=["implement"])
    .node("publish", "Create PR after approval", agent="publisher",
          depends_on=["verify"], human_approval=True)
    .build()
)

plan = workflow.to_execution_plan()
```

## Groovy

Groovy is the first external DSL frontend because it provides a concise executable DSL, closures, Java interoperability, and a natural fit for FlossWare's JVM ecosystem. The reference frontend lives at `groovy/Loom.groovy` and emits the same declarative shape as the Python model.

```groovy
workflow('issue-to-pr', 'Produce a production-ready PR') {
    fact 'repository', 'FlossWare/loom-ai'
    constraint 'tests must pass'
    policy 'max_iterations', 5

    node('inspect', 'Inspect issue and repository', 'analyst')
    node('implement', 'Implement verified fix', 'developer', ['inspect'])
    node('verify', 'Run tests and review changes', 'tester', ['implement'])
    node('publish', 'Create PR after approval', 'publisher', ['verify'], null, true)
}
```

## Semantic model

```text
workflow
  goal
  facts
  constraints
  policy
  execution graph
      ├── sequential dependencies
      ├── parallel branches
      ├── conditions
      ├── retries/timeouts
      ├── human gates
      └── agent/tool metadata
```

The workflow definition is intentionally broader than `.gitlab-ci.yml`: it describes **what outcome must be achieved and the constraints around achieving it**, while Loom remains responsible for execution and future adaptive planning.

## Dogfooding

The first real consumer is `personal-agent`, which is being moved into the `sfloess` namespace. The target is not a demo. It is a real application that uses Loom to perform real repository work: investigate an issue, implement a change, validate it, and produce a PR. Failures in that application become Loom engineering work.
