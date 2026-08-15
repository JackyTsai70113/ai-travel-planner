# Hooks

No lifecycle-hook format is universally implemented by all agent runtimes.
This repository therefore defines:

1. Canonical event payloads in `schemas/hook-event.schema.json`.
2. Deterministic gates in `hooks/hooks.yaml`.
3. An adapter contract for mapping runtime events to canonical events.
4. Git and CI checks that remain useful without an agent runtime.

## Safety

- Hook commands are arrays, not shell strings.
- Blocking hooks fail closed.
- Adapters must not weaken a blocking hook.
- Hook input is untrusted and must be schema-validated.
- Secrets must be redacted before events are written.
- Events should be append-only and bounded by retention policy.

## Adapter invocation

An adapter replaces `{event_path}` and `{workspace_root}` in `hooks/hooks.yaml`
with the actual event file and consumer workspace. It must also replace
`{actor_id}` and `{actor_mode}` from authenticated runtime session state, never
from fields supplied by the event producer. It executes the command array
directly, without a shell. A missing trusted identity, malformed event,
identity mismatch, or out-of-workspace artifact returns non-zero. Static
repository fixtures pass their declared identity explicitly only for conformance
testing; that fixture path is not a live-runtime trust mechanism.

`implementation.started` requires a referenced plan with `status: approved`,
complete acceptance mapping, and an approval by someone other than the plan
owner. Production-write events also reject every `unknown` platform impact.
`verification.completed` and `task.completed` validate all referenced evidence
and verdicts across documents.

`registries/event-policy.yaml` maps security-critical events to allowed roles,
modes, assignment requirements, and blocking gates. Write events must reference
a handoff whose recipient is the actor and whose task/run identity matches.
Requested files must fit both the agent manifest and handoff scope.

`command.requested` accepts an argv array only. The command ID and exact argv
must match both the independently approved plan and the receiving handoff.
Executable comparison is case-insensitive and strips only a controlled `.exe`
suffix. The resulting identifier must appear in
`registries/event-policy.yaml:allowed_executables`; the canonical default
contains only `{name: make, kind: direct_tool}`, and every unknown executable
fails closed. Automatic commands, approved plan commands, and verification
commands accept only entries classified as `direct_tool`. Entries classified as
`interpreter`, `shell`, or `dispatcher` fail closed for every argv; the
validator does not attempt to infer executable aliases or parse their CLI
options. Windows script suffixes, denied executables, commands outside the
assignment, and commands for terminal tasks also fail closed.

## Extending executable policy

A project or platform consumer may replace or extend `allowed_executables` with
reviewed `{name, kind}` entries in its active event policy. Each addition must:

1. Use the canonical lowercase identifier without `.exe`, a path, or shell
   syntax.
2. Classify the executable as `direct_tool`, `interpreter`, `shell`, or
   `dispatcher`.
3. Be required by a documented project or platform validation command and
   receive independent specification, code-quality, and security review.
4. Keep exact argv in the approved plan and the command ID in the recipient's
   handoff.
5. Add positive and negative full-event fixtures before automatic execution is
   enabled.

When validation needs Python, Node, Ruby, or another interpreter, expose the
operation as a reviewed target of a narrowly scoped task runner or other
`direct_tool`; do not authorize the interpreter itself. Registering an arbitrary
wrapper as `direct_tool` is a security-sensitive policy change and requires an
independent reviewer to verify that the wrapper cannot dispatch unapproved
commands or reinterpret untrusted input.

`review.completed` references a complete review-verdict artifact. The gate
cross-checks its reviewer, review type, task, evidence, and findings. A clean
PASS may have no findings; FAIL must contain a valid finding; PARTIAL and
BLOCKED must include a concrete summary and resolvable evidence.

## Canonical events

- `session.started`
- `task.accepted`
- `plan.proposed`
- `plan.approved`
- `implementation.started`
- `file.write.requested`
- `command.requested`
- `review.completed`
- `verification.completed`
- `task.completed`
- `task.blocked`

Consumer repositories may add namespaced events, but canonical event semantics
must remain stable within a major schema version.

`session.started` is intentionally non-blocking. Every other security-critical
transition, including `plan.proposed`, has a blocking hook and a complete event
policy entry.
