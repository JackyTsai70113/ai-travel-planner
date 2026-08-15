# Collaboration Protocol

## Message types

Agents communicate through five structured artifact types:

1. Task envelope: authorized objective and scope.
2. Handoff: role-specific assignment and context.
3. Finding: evidence-backed defect, risk, or gap.
4. Decision: approved architecture or scope choice.
5. Verdict: acceptance and verification outcome.

Authorized handoff write paths must be a subset of the receiving agent's
manifest. Capability and tool names must exist in
`registries/runtime-policy.yaml` and be allowed for that agent mode.
Paths use conservative POSIX segments: absolute paths, traversal, mixed
separators, embedded glob syntax, and empty segments are rejected.

Handoffs authorize command IDs explicitly. Exact argv comes from an approved
plan; a verdict or event cannot invent its own required command.

## Finding requirements

Every actionable finding includes:

- Severity.
- Category.
- Claim.
- Repository evidence.
- Impact.
- Suggested remediation or missing decision.
- Status.

Findings without evidence should be labeled as hypotheses.

## Severity

- `critical`: exploitation, irreversible loss, or core contract failure.
- `high`: likely user-visible failure, security exposure, or major requirement
  miss.
- `medium`: bounded correctness, reliability, or maintainability problem.
- `low`: non-blocking improvement.

Critical and high findings block completion. Medium findings require explicit
disposition. Low findings may be deferred.

For PASS review purposes, `fixed` records remain blocking until an independent
`core.verifier` records `verified` with a concrete disposition and resolvable
evidence. Evidence-backed rejection by an independent registered reviewer may
also clear the gate.

## Conflict resolution

When agents disagree:

1. State the disputed claim.
2. Identify the evidence each position relies on.
3. Run a deterministic experiment or targeted test when possible.
4. Ask Architect to resolve technical trade-offs.
5. Ask the human owner to resolve product, policy, or risk-acceptance choices.

Do not resolve disagreements by majority vote alone.
