---
status: accepted
date: 2026-07-30
decision-makers:
  - repository-owner
consulted: []
informed: []
---

# ADR-0002: Use a permanent core team and on-demand platform specialists

## Context and problem statement

Projects may include iOS, Android, backend, and web. Permanently running a full
agent team for every platform duplicates context and increases conflicts and
cost.

## Decision drivers

- Clear ownership.
- Minimal context and cost.
- Cross-platform consistency.
- Independent quality gates.

## Considered options

1. One general-purpose agent for all work.
2. Permanent full team for every platform.
3. Permanent core roles plus impact-routed specialists.

## Decision outcome

Chosen option: "permanent core roles plus impact-routed specialists".

### Consequences

- Good: platform expertise is available without permanent overhead.
- Good: shared contracts have explicit reviewers.
- Bad: every task needs a platform impact assessment.
- Bad: orchestration must prevent overlapping path ownership.

## Validation

Plans must include a platform impact matrix. Unknown shared-contract impact
blocks implementation.

## Rollback or supersession

Revisit if measured routing cost is greater than the reduction in rework and
agent compute cost.
