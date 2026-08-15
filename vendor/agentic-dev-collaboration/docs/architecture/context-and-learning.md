# Context, Memory, and Learning

## Context layers

1. Stable project policy: repository instructions and architecture decisions.
2. Task context: task envelope, approved specification, and plan.
3. Execution context: assigned files, commands, findings, and evidence.
4. Learning context: validated lessons from completed iterations.

Agents should receive only the layers required for their role.

## Structured handoffs

A handoff contains:

- Task and run identifiers.
- Objective and approved scope.
- Relevant constraints.
- Inputs and repository evidence.
- Decisions already made.
- Open questions.
- Expected output contract.
- Stop conditions.

Do not forward hidden chain-of-thought or an entire conversation when a
structured handoff is sufficient.

## Learning lifecycle

```text
hypothesis -> observed result -> review -> validated lesson -> policy candidate
```

- A hypothesis is not reusable guidance.
- A single successful task may be insufficient evidence for a general rule.
- Lessons must cite runs and describe scope limits.
- A policy change requires review and versioning.
- Superseded lessons remain in history with status and rationale.

## Compaction

When context must be compacted, preserve:

- Current state and next valid transitions.
- Acceptance criteria.
- Unresolved findings.
- Architecture decisions.
- Exact evidence locations.
- Explicit assumptions and unknowns.

Discard duplicated narrative and speculative reasoning.
