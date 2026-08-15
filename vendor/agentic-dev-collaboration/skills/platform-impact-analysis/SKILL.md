---
name: platform-impact-analysis
description: Classify iOS, Android, backend, web, contract, data, observability, and operations impact before planning.
---

# Platform Impact Analysis

## Workflow

For each surface, classify impact as `none`, `compatible`, `changed`, or
`unknown`:

- iOS.
- Android.
- Backend.
- Web.
- Shared contracts.
- Data.
- Observability.
- Operations.

For every value other than `none`, record:

- Affected paths and components.
- Compatibility requirement.
- Required specialist.
- Required validation.
- Rollout and rollback implications.

## Routing

- Load a platform engineer only for `changed`.
- Load Contract Reviewer for changed or unknown shared contracts.
- Load Integration Tester when multiple changed platforms participate in one
  journey.
- Escalate unknown production impact to Planner or Architect.

## Mobile compatibility

Always consider previously released mobile clients, store rollout delays,
offline behavior, and minimum supported versions.

## Output

Return a completed platform impact object compatible with the task-envelope
schema plus a short routing recommendation.
