---
name: code-quality-review
description: Review an implementation for correctness, security, reliability, performance, and maintainability after specification compliance passes.
---

# Code Quality Review

## Preconditions

- Specification-compliance review passed.
- The review scope and comparison base are explicit.

## Workflow

1. Inspect the actual diff and surrounding code.
2. Check correctness, edge cases, error handling, and data consistency.
3. Check authentication, authorization, secrets, input handling, and trust
   boundaries.
4. Check concurrency, resource use, performance, and failure recovery.
5. Check compatibility, migration, rollout, and observability.
6. Apply affected platform concerns from `platforms/`.
7. Evaluate tests for meaningful failure detection, not only coverage count.
8. Classify each actionable issue by severity and cite exact evidence.
9. Avoid style-only findings unless they materially affect maintainability.

## Output

Use the finding schema. The verdict is:

- `PASS`: no blocking findings.
- `FAIL`: one or more critical or high findings.
- `PARTIAL`: review scope or evidence is incomplete.
- `BLOCKED`: the diff, specification, or environment is unavailable.

Do not implement fixes while acting as reviewer.
