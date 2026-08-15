---
spec_id: CHANGE-NNN
status: draft
created_at: YYYY-MM-DD
---

# Implementation Plan

## Outcome and stop condition

State the required result and when execution must stop.

## Preconditions

- Approved specification.
- Required ADRs accepted.
- Platform impact contains no blocking unknowns.

## Task graph

| ID | Role | Owned paths | Depends on | Change | Validation | Stop condition |
| --- | --- | --- | --- | --- | --- | --- |
| T-01 | role.id | path | none | change | command/evidence | condition |

## Parallel waves

Describe which tasks may run concurrently and why their writes do not overlap.

## Acceptance-to-evidence map

| Acceptance ID | Task IDs | Evidence owner | Evidence |
| --- | --- | --- | --- |
| AC-01 | T-01 | core.verifier | command/artifact |

## Required commands

Record each stable command ID and its exact argv array. Handoffs authorize only
the IDs they need; command events and PASS verdicts must match these argv values.

| Command ID | argv | Evidence output |
| --- | --- | --- |
| repository-check | `["make", "check"]` | path/to/output.txt |

## Migration, rollout, and rollback

Describe sequencing and required human approvals.

## Risks and mitigations

| Risk | Likelihood | Impact | Mitigation | Owner |
| --- | --- | --- | --- | --- |

## Review record

- Specification reviewer:
- Verdict:
- Blocking findings:
