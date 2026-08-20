# Loom Demo Runbook

## Preparation

1. Start from a clean working tree.
2. Use a small, real issue in `FlossWare/loom-ai`.
3. Ensure the required model/provider credentials are configured through the normal Loom configuration mechanism.
4. Ensure repository tools and the relevant test command are available.
5. Record the starting commit so the demonstration is reproducible.

## Session 1

### Start

Start Loom in local mode using the normal supported command/configuration.

Create a project/session associated with the Loom repository.

### Prompt

Use a bounded engineering request such as:

> Investigate issue #<ISSUE>. Understand the relevant code, implement the appropriate fix, run the relevant tests, and summarize the problem, decision, changes, and verification evidence. Preserve the important discoveries and decisions for a future session.

### Observe

Capture evidence that Loom:

- discovers relevant repository context
- uses tools rather than fabricating repository state
- modifies the intended files
- runs tests
- produces a useful summary
- persists the session/knowledge

### End

Terminate the Loom process/session completely.

Do not provide Session 2 with the Session 1 transcript.

## Session 2

Start a fresh Loom process/session for the same project.

Use:

> What did we learn while working on the previous issue? Explain the problem, why we made the change, what files were involved, and what evidence we have that it works.

Then ask:

> What should I be careful about if I modify this component again?

The response should be based on persisted Loom knowledge and cite or otherwise expose its provenance where supported.

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
      ↓
Loom discovers limitations
      ↓
Loom records the lessons
      ↓
Loom improves itself
      ↓
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
