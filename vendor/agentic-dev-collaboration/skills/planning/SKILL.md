---
name: planning
description: Create an executable, evidence-mapped implementation plan from an approved task and repository facts.
---

# Planning

Use this skill when behavior-changing work needs decomposition before
implementation.

## Required inputs

- Valid task envelope.
- Repository exploration report.
- Applicable project policy.
- Approved architecture decisions, if any.

## Workflow

1. Restate the objective, scope, constraints, and stop condition.
2. Confirm every platform impact value; unresolved `unknown` values block the
   plan.
3. List affected shared contracts and compatibility windows.
4. Decompose work into small tasks with:
   - responsible role;
   - owned paths;
   - dependencies;
   - expected change;
   - validation;
   - stop condition.
5. Identify tasks that may run in parallel without overlapping ownership.
6. Map each acceptance criterion to planned evidence.
7. Define migration, rollout, rollback, observability, and human approval where
   the risk requires them.
8. Review the plan for missing requirements, unnecessary scope, and ambiguous
   ownership.

## Output

Produce:

- Scope summary.
- Platform impact matrix.
- Ordered task graph.
- Acceptance-to-evidence map.
- Risk and approval gates.
- Verification commands or evidence sources.

Do not implement code while using this skill.

## Stop conditions

Stop and return `BLOCKED` when:

- A product or policy decision is missing.
- Shared-contract impact is unknown.
- Required repository evidence is unavailable.
- Two tasks require overlapping writes without an integration order.
