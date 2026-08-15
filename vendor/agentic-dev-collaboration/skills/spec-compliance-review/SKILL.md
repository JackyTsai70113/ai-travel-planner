---
name: spec-compliance-review
description: Independently verify that a plan or implementation satisfies the approved specification without adding unapproved scope.
---

# Specification Compliance Review

Run this review before code-quality review.

## Required inputs

- Task envelope and acceptance criteria.
- Approved plan and architecture decisions.
- Plan or implementation diff under review.

## Workflow

1. Build a checklist from every requirement, constraint, and non-goal.
2. Verify that each acceptance criterion has planned or implemented coverage.
3. Identify missing behavior.
4. Identify behavior, abstractions, dependencies, or migrations not approved by
   the specification.
5. Verify platform impact and shared-contract compatibility.
6. Verify that documentation, rollout, and rollback requirements are included.
7. Emit evidence-backed findings using `schemas/finding.schema.json`.
8. Issue `PASS` only when no critical or high specification findings remain.

## Review boundary

Ignore style preferences unless they violate an explicit requirement. Do not
modify the plan or implementation while reviewing it.

## Output

- Requirement coverage matrix.
- Structured findings.
- `PASS`, `FAIL`, `PARTIAL`, or `BLOCKED` verdict.
