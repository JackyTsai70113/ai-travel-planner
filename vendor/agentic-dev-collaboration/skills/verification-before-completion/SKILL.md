---
name: verification-before-completion
description: Prove or disprove task completion with fresh commands and acceptance-to-evidence mapping.
---

# Verification Before Completion

## Required inputs

- Task envelope.
- Integrated repository state.
- Required review verdicts and finding dispositions.
- Project validation commands.

## Workflow

1. List every claim that must be proven.
2. Confirm that required reviews passed or have explicit approved dispositions.
3. Run the narrowest commands that prove each acceptance criterion.
4. Run required repository-wide regression checks.
5. Record exact commands, exit codes, and output references.
6. Separate failed behavior from unavailable proof.
7. Map every acceptance criterion to `pass`, `fail`, `unproven`, or
   `not_applicable`.
8. Emit a verdict conforming to `schemas/verdict.schema.json`.

## Verdict rules

- `PASS`: every applicable acceptance criterion passed and required checks
  succeeded.
- `FAIL`: at least one applicable criterion failed.
- `PARTIAL`: implementation may be correct, but material proof is missing.
- `BLOCKED`: required environment, authority, or artifact is unavailable.

Never infer a pass from an implementer or reviewer summary.
