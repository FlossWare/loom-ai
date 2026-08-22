from loom_ai.workflow_lang import WorkflowBuilder, WorkflowDefinition, WorkflowNode, WorkflowValidationError


def test_workflow_compiles_to_execution_plan():
    workflow = (
        WorkflowBuilder("test", "complete task")
        .fact("repository", "example/repo")
        .constraint("tests must pass")
        .policy("max_iterations", 3)
        .node("inspect", "inspect", agent="analyst")
        .node("implement", "implement", agent="developer", depends_on=["inspect"])
        .node("verify", "verify", agent="tester", depends_on=["implement"], human_approval=True)
        .build()
    )
    plan = workflow.to_execution_plan()
    assert [task.id for task in plan.tasks] == ["inspect", "implement", "verify"]
    assert plan.tasks[1].dependencies == ["inspect"]
    assert plan.tasks[2].input_data["human_approval"] is True
    assert plan.tasks[0].input_data["facts"]["repository"] == "example/repo"


def test_workflow_allows_parallel_branches():
    workflow = WorkflowDefinition(
        name="parallel",
        goal="review",
        nodes=[
            WorkflowNode("security", "security review"),
            WorkflowNode("architecture", "architecture review"),
            WorkflowNode("synthesis", "synthesize", depends_on=("security", "architecture")),
        ],
    )
    plan = workflow.to_execution_plan()
    assert plan.tasks[2].dependencies == ["security", "architecture"]


def test_workflow_rejects_unknown_dependency():
    workflow = WorkflowDefinition(
        name="invalid",
        goal="fail",
        nodes=[WorkflowNode("x", "x", depends_on=("missing",))],
    )
    try:
        workflow.validate()
    except WorkflowValidationError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("expected WorkflowValidationError")


def test_workflow_rejects_cycles():
    workflow = WorkflowDefinition(
        name="cyclic",
        goal="fail",
        nodes=[
            WorkflowNode("a", "a", depends_on=("b",)),
            WorkflowNode("b", "b", depends_on=("a",)),
        ],
    )
    try:
        workflow.validate()
    except WorkflowValidationError as exc:
        assert "cycle" in str(exc)
    else:
        raise AssertionError("expected WorkflowValidationError")
