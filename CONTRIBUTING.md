# Contributing to loom-ai

## Issue Close Policy

### Acceptance Checklist Issues

Close as `completed` **only** when every checklist item is verified
against the current `main` branch. Link a commit, PR, or harness
output as evidence in the closing comment.

### Partial Progress

Leave the issue open or close as `not_planned` with an explanation.
Never mark partial work as `completed`.

### Security and Demo DoD Issues

Require a second verification:

- Code path check (grep, read, or test proving the fix is on `main`)
- Test result or runbook evidence

Both must be referenced in the closing comment.

### Closing Comment Template

```
Verified on main (<commit>):
- [ ] Checklist item 1: <commit/PR link>
- [ ] Checklist item 2: <commit/PR link>
- [ ] Security/demo verification: <test output or runbook link>
```
