---
name: continuous-collaboration
description: Drive a repository change through architecture, planning, implementation, testing, independent review, repair, verification, and merge-readiness while binding every gate to one unchanged commit.
---

# Continuous Collaboration

Coordinate role-separated iterations until the change is proven merge-ready or
a terminal blocker is reached.

## Run the role sequence

1. Ask Architect to resolve durable boundaries and trade-offs.
2. Ask Planner to map acceptance criteria, owned paths, commands, and evidence.
3. Ask Executor to implement only the approved production scope.
4. Ask Test Engineer to add or update independent tests in authorized paths.
5. Ask independent, read-only Spec, Code, and risk-triggered Security Reviewers
   to inspect the exact diff and commit.
6. Ask Verifier to run approved commands and map fresh evidence to acceptance
   criteria.

Keep reviewers read-only. Keep implementation and merge authority separate from
review authority. Exchange structured summaries, findings, evidence, and
verdicts rather than hidden reasoning.

## Bind every iteration

Record the exact head SHA before review and verification. Bind findings,
commands, check results, and verdicts to that SHA. If HEAD changes, invalidate
earlier PASS results and repeat every affected gate.

When any reviewer returns `REQUEST_CHANGES` or a blocking finding:

1. Route production fixes to Executor and test fixes to Test Engineer.
2. Produce a new commit and fresh evidence.
3. Send the new SHA and actual diff to the same independent reviewer.
4. Repeat until that reviewer returns PASS for the unchanged SHA or a terminal
   condition is reached.

Do not treat an implementer self-check, model completion claim, stale review, or
passing check from another SHA as clearance.

## Declare merge-readiness

Declare merge-readiness only when:

- HEAD is unchanged from the reviewed and verified SHA;
- every required independent review is PASS;
- every required CI and repository check has one latest successful attempt;
- all blocking findings are independently cleared;
- the verification verdict is PASS with fresh evidence;
- deterministic policy reports no blocker;
- the merge controller can enforce the expected head atomically.

Never let a model verdict override a deterministic blocker.

## Stop

Return `BLOCKED` when required authority, trusted evidence, environment, or a
product decision is unavailable. Return `FAIL` when deterministic behavior
disproves acceptance. Stop after the declared retry, time, or cost budget rather
than looping on self-reported completion. Escalate repeated unchanged findings
or head churn with the exact evidence required to continue.

Return a terminal summary with the current SHA, gate states, unresolved
findings, latest evidence, next authorized action, and merge-readiness status.
