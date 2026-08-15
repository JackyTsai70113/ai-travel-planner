# Adoption Guide

Adopt the framework gradually. Do not enable autonomous writes before role
boundaries and deterministic checks are proven in the target repository.

## Phase 0: Repository contract

1. Add a project-specific `AGENTS.md`.
2. Identify sources of truth and protected files.
3. Record exact lint, test, build, and validation commands.
4. Define human approval boundaries.
5. Add the task-envelope, finding, and verdict schemas.
6. Vendor a pinned consumer snapshot and commit its lock.
7. Record policy overlays with consumer root policy above project/domain,
   pinned framework, and generated adapter layers.

Exit criteria:

- Project policy is reviewed by maintainers.
- CI can run deterministic checks without an agent.
- CI validates the committed framework snapshot offline without a private
  upstream credential.

## Phase 1: Read-only collaboration

Enable Explorer, Architect, Planner, Spec Reviewer, Code Reviewer, and Verifier
with read-only or validation-only access.

Pilot on real tasks and measure:

- Valid findings.
- Missed requirements.
- Time and compute cost.
- Human corrections.
- Evidence gaps.

Exit criteria:

- Reviewers cite useful repository evidence.
- Verifier distinguishes missing proof from failure.
- No role requires unnecessary permissions.

## Phase 2: Controlled implementation

Enable Executor in isolated branches or worktrees.

Controls:

- Explicit path scope.
- Approved plan.
- No deployment or secret access.
- Independent review and verification.
- Maximum rework and cost budgets.

Exit criteria:

- Write boundaries are technically enforced or visibly mediated.
- Rollback from a failed run is understood.
- Review gates catch seeded or known failure cases.

## Phase 3: Platform specialists

Add iOS, Android, backend, and web specialists only for actual changed surfaces.
Add Contract Reviewer and Integration Tester for shared contracts and
cross-platform journeys.

Exit criteria:

- Platform impact correctly routes specialists.
- Shared contract changes are reviewed before consumer implementation.
- Integrated evidence covers compatibility windows.

## Phase 4: Runtime adapters and hooks

Add runtime-specific discovery, tool mapping, and lifecycle-event adapters.
Keep generated files out of the canonical contract.

Exit criteria:

- Adapter limitations are documented.
- Blocking hooks fail closed.
- Removing the adapter does not remove project policy or evidence history.

Migrate legacy runtime discovery through a thin generated adapter. First run it
in shadow mode, then a bounded canary, and compare discovery, policy, hook, and
evidence results. Do not delete the legacy path until the replacement is
verified. Adapter output remains disposable and non-canonical.

## Trusted pull request control

Adopt `schemas/trusted-pr-control.schema.json` before allowing a review result to
influence merge-readiness. Keep the trusted base and required-check set in
protected configuration, lock the head and diff digest before and after review,
and treat fork content as untrusted. Require immutable automation dependency
refs, read-only review, separate merge authority, and an atomic expected-head
merge.

Do not let a model verdict override deterministic blockers or place untrusted
model values into repair instructions. Require human approval and independent
meta-review for trust-anchor changes.

If one legacy identity currently holds both review and merge authority, record
that as a blocker. Shadow the separated read-only reviewer, canary the
expected-head merge controller, and remove the combined authority only after
both paths are proven. Migration status is evidence, not an exception: it
cannot bypass review, verification, permission-separation, or merge gates.

See `consumer/README.md` for deterministic export, offline validation, and
overlay precedence.

## Continuous improvement

Review metrics every few iterations. Remove steps that add cost without useful
signal. Promote lessons only after evidence and review. Version contract
changes and retain old run records.

## Rollback

The framework can be rolled back in layers:

1. Disable write-capable agents.
2. Disable runtime adapters and lifecycle hooks.
3. Retain schemas, specifications, decisions, and run records.
4. Continue using deterministic CI and human review.

The repository should remain understandable and buildable without an AI agent.
