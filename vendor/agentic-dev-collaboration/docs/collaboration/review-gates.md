# Review Gates

## Gate 1: Plan and specification

Checks:

- Objective and non-goals are unambiguous.
- Acceptance criteria are observable.
- Platform impact has no unexplained `unknown`.
- Shared contract compatibility is addressed.
- Tasks are ordered and path ownership is non-overlapping.
- Test and rollback strategies match the risk.

## Gate 2: Specification compliance

Checks:

- Every acceptance criterion is implemented or explicitly deferred.
- No unapproved behavior or abstraction was added.
- Required platforms and compatibility paths are covered.
- Documentation and migration requirements are satisfied.

This gate ignores style unless style affects an explicit requirement.

## Gate 3: Code quality and security

Checks:

- Correctness and edge cases.
- Trust boundaries and authorization.
- Error handling and observability.
- Concurrency and data consistency.
- Performance and resource use.
- Platform conventions and accessibility.
- Maintainability and unnecessary complexity.

## Gate 4: Verification

Checks:

- Fresh commands and exit codes are recorded.
- Required tests passed in the intended environment.
- Acceptance criteria map to evidence.
- Known limitations and unavailable proof are explicit.
- Integrated behavior is tested when multiple platforms changed.

Only Gate 4 may produce the final completion verdict.

A PASS verdict must use the same task ID, cover every acceptance criterion
exactly once, mark every applicable result `pass`, reference non-empty fresh
evidence, and record exit code 0 for every command required by the approved
plan. An empty or self-declared command set is not a pass.

Critical and high findings block PASS until their status is `verified` or
`rejected`; `fixed` alone is not clearance. Fixed and verified findings need a
concrete disposition and resolvable resolution evidence. Verification must be
recorded by the independent registered `core.verifier`, never the finding
author. A rejected finding needs a concrete disposition from an independent
registered reviewer. Every non-terminal medium-or-higher finding needs a
disposition.

## Completion gate

A completed task cannot retain an `unknown` platform impact. A completed run
must have `completed_at`, PASS specification and code-quality reviews, any
risk-triggered security or contract reviews, and a PASS verification verdict.
