# AGENTS

Read this file before modifying the repository.

## Mission

Maintain a vendor-neutral, auditable framework for sustainable multi-agent
software delivery. Optimize correctness, traceability, and learning across
iterations rather than maximizing autonomous activity.

## Non-negotiable boundaries

1. Keep the canonical framework independent of any AI vendor, model, IDE, or
   proprietary tool name.
2. Never treat an agent's completion claim as verification evidence.
3. Never let an implementer approve its own work.
4. Never let a reviewer silently modify the code it reviews.
5. Never expose hidden chain-of-thought. Exchange structured summaries,
   evidence, decisions, risks, questions, findings, and verdicts.
6. Never grant a role tools it does not need.
7. Never store secrets, credentials, tokens, private prompts, or production data.
8. Never bypass required specification, review, security, or verification gates.
9. Preserve append-only run records and decision history.
10. Unknown or unsupported runtime capabilities must fail closed for writes.

## Sources of truth

1. `AGENTS.md`: global operating policy.
2. `schemas/`: machine-readable contracts.
3. `agents/`: role, permission, input, and output contracts.
4. `skills/`: reusable workflows.
5. `specs/`: requirement and acceptance templates.
6. `docs/architecture/decisions/`: durable decisions.
7. `policies/` when added by a consumer repository: project-specific risk and
   path policy.
8. `artifacts/runs/` in a consumer repository: append-only execution evidence.

Generated runtime-specific files are never canonical.

## Role boundaries

- Orchestrator coordinates and enforces gates; it does not implement.
- Explorer, Architect, Spec Reviewer, Code Reviewer, and Security Reviewer are
  read-only.
- Planner may update planning artifacts only.
- Executor may update approved production paths only.
- Test Engineer may update tests and test fixtures only.
- Verifier may execute approved validation commands but does not repair failures.
- Platform specialists may edit only their approved platform scope.

If the runtime cannot enforce these boundaries technically, the adapter must
surface that limitation and require human confirmation before write-capable
execution.

## Required workflow

1. Create or validate a task envelope.
2. Inspect the repository and identify the change surface.
3. Produce a platform impact matrix.
4. Record an architecture decision when the change creates a durable trade-off.
5. Produce an implementation plan with acceptance-to-evidence mapping.
6. Review the plan and specification before implementation.
7. Implement the smallest approved change.
8. Add or update tests independently from production implementation when
   practical.
9. Run specification-compliance review.
10. Run code-quality and security review.
11. Verify all acceptance criteria with fresh evidence.
12. Record the verdict, unresolved risks, and validated learning.

Small local changes may combine steps, but may not remove independent review or
fresh verification when behavior changes.

## Cross-platform routing

Every change must classify impact for iOS, Android, backend, web, shared
contracts, data migration, observability, and release operations.

Load only the specialists required by the impact matrix:

- iOS behavior or build changes: iOS Engineer.
- Android behavior or build changes: Android Engineer.
- Service, API, persistence, or infrastructure changes: Backend Engineer.
- Browser application or frontend changes: Web Engineer.
- Shared API or event contract changes: Contract Reviewer plus every affected
  consumer platform.
- User journey spanning platforms: Integration Tester.

Shared contract changes must be reviewed before consumer implementations merge.

## Evidence rules

- Cite repository paths and line numbers for material claims.
- Record exact commands and exit codes for verification.
- Distinguish PASS, FAIL, PARTIAL, and BLOCKED.
- Missing evidence is not a pass.
- A test written by the implementer is useful evidence but not independent proof.
- Prefer deterministic checks over natural-language assurance.

## Change rules

- Work on an `agent/` feature branch.
- Keep each commit focused and reversible.
- Update schemas, examples, validation, and documentation together when changing
  a contract.
- Add or update tests for every invariant.
- Do not commit generated adapter output.
- Do not rewrite shared history or bypass CI.

## Development commands

```bash
python3 -m pip install -r requirements-dev.lock
make lint
make test
make validate
make check
```

Use `make PYTHON=.venv/bin/python check` when the virtual environment is not
activated. The commands use `python3` by default for macOS and Linux.

All relevant checks must pass before completion is reported.
