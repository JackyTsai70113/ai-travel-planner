---
name: context-recovery
description: Recover an interrupted, compacted, handed-off, or resumed repository task from durable project sources, current version-control state, reviews, and CI evidence before continuing work.
---

# Context Recovery

Recover facts from durable sources before acting.

## Read in authority order

1. Read the nearest applicable `AGENTS.md`, then its parent instructions.
2. Read the active handoff and approved plan or task envelope.
3. Read only the role contract needed for the current assignment.
4. Inspect the current branch, exact HEAD, worktree status, recent commits, and
   upstream tracking state.
5. Inspect unresolved review findings and CI evidence for that exact HEAD.
6. Read source files named by those artifacts when a claim needs confirmation.

Treat generated output, caches, dashboards, local scratch state, model
summaries, and chat transcripts as non-authoritative. Do not replay a
conversation to reconstruct state. Do not accept a completion claim without
repository or CI evidence.

## Detect unfinished work

Confirm:

- the branch and HEAD match the active handoff;
- the worktree is clean or every modification has an identified owner;
- the approved plan still matches the task and current diff;
- required reviews apply to the current HEAD;
- unresolved findings, requested changes, failed checks, and interrupted
  commands remain visible;
- no newer commit invalidated earlier evidence.

Fail closed when durable sources disagree. Preserve the conflicting facts and
request a decision instead of guessing.

## Resume safely

1. Restate the authorized objective, non-goals, role, path scope, and stop
   conditions.
2. Identify the last proven lifecycle state and the next incomplete gate.
3. Re-run only stale or missing checks; never label old evidence fresh.
4. Continue without rewriting append-only history.
5. Write recovered state only to an explicitly authorized path. Otherwise
   return the summary without modifying the repository.

## Output

Return a structured context summary containing:

- `objective`
- `role_and_scope`
- `branch`
- `head_sha`
- `worktree_state`
- `durable_sources`
- `confirmed_facts`
- `unresolved_reviews`
- `ci_state`
- `next_gate`
- `blockers`
- `stale_or_untrusted_inputs`

Separate confirmed facts from inference. Cite paths, commit identifiers, review
references, and check evidence for every material claim.
