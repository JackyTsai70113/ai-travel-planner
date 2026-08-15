# Collaboration Lifecycle

## 1. Intake

Create a task envelope with objective, constraints, out-of-scope items,
acceptance criteria, risk, budgets, and initial platform impact.

## 2. Exploration

Explorer gathers repository-backed facts and returns relevant paths, patterns,
dependencies, commands, and unknowns. It does not propose edits.

## 3. Architecture

Architect determines whether a durable decision is needed. If needed, create or
update an ADR with alternatives, decision drivers, consequences, and rollback.

## 4. Planning

Planner maps acceptance criteria to implementation tasks and verification
evidence. Each task has path ownership, dependencies, responsible role, stop
condition, and validation.

## 5. Pre-implementation review

Spec Reviewer checks completeness, consistency, scope, platform impact, and
testability. Implementation cannot begin while blocking findings remain.

## 6. Implementation and tests

Executor or platform engineers implement approved tasks. Test Engineer writes
or improves independent tests. Shared contracts are fixed before parallel
consumer work.

## 7. Independent review

First verify specification compliance. Only after it passes, evaluate code
quality, security, maintainability, performance, and platform conventions.

## 8. Verification

Verifier maps every acceptance criterion to fresh evidence and emits PASS,
FAIL, PARTIAL, or BLOCKED.

## 9. Learning and closeout

Record the final verdict, material decisions, unresolved risks, actual
validation, and candidate lessons. Promote only reviewed lessons.
