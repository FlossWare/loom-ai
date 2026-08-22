"""Minimal Groovy frontend contract for Loom workflows.

This file is intentionally dependency-free.  It is a reference DSL that
builds the same declarative shape consumed by the Loom workflow model.  A
Groovy application can embed this script, serialize ``definition`` as JSON,
and submit it to a Loom runtime.

Example:

workflow('issue-to-pr', 'Produce a production-ready PR') {
    fact 'repository', 'FlossWare/loom-ai'
    constraint 'tests must pass'
    policy 'max_iterations', 5

    node('inspect', 'Inspect issue and repository', 'analyst')
    node('implement', 'Implement the verified fix', 'developer', ['inspect'])
    node('verify', 'Run tests and review changes', 'tester', ['implement'])
    node('publish', 'Create PR after approval', 'publisher', ['verify'], null, true)
}
"""

class LoomNode {
    String id
    String task
    String agent
    List<String> dependsOn = []
    String condition
    boolean humanApproval = false
    int retry = 0
    double timeoutSeconds = 0
    Map metadata = [:]

    Map asMap() {
        [id: id, task: task, agent: agent, depends_on: dependsOn,
         condition: condition, retry: retry, timeout_seconds: timeoutSeconds,
         human_approval: humanApproval, metadata: metadata]
    }
}

class LoomWorkflow {
    String name
    String goal
    Map facts = [:]
    List<String> constraints = []
    Map policy = [:]
    List<LoomNode> nodes = []

    void fact(String name, Object value) { facts[name] = value }
    void constraint(String expression) { constraints << expression }
    void policy(String name, Object value) { policy[name] = value }

    void node(String id, String task, String agent = null,
              List<String> dependsOn = [], String condition = null,
              boolean humanApproval = false, int retry = 0,
              double timeoutSeconds = 0, Map metadata = [:]) {
        nodes << new LoomNode(id: id, task: task, agent: agent,
            dependsOn: dependsOn, condition: condition,
            humanApproval: humanApproval, retry: retry,
            timeoutSeconds: timeoutSeconds, metadata: metadata)
    }

    Map asMap() {
        [name: name, goal: goal, facts: facts, constraints: constraints,
         policy: policy, nodes: nodes.collect { it.asMap() }]
    }
}

def workflow(String name, String goal, Closure body) {
    def definition = new LoomWorkflow(name: name, goal: goal)
    body.delegate = definition
    body.resolveStrategy = Closure.DELEGATE_FIRST
    body()
    definition
}
