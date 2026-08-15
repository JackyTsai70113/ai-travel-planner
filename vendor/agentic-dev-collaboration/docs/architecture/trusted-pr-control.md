# Trusted Pull Request Control

`schemas/trusted-pr-control.schema.json` defines a portable control record. It
does not grant merge permission and is not an executable automation workflow.

## Trust model

Use protected configuration to select the trusted base repository, ref, commit,
required checks, trust-anchor paths, and immutable automation dependency refs.
Treat the pull-request diff, title, description, comments, branch content, and
model output as inert untrusted data.

Record the implementer identity, complete changed-path set, reviewed head, and
diff digest for each run. A changed path matching a trust anchor requires one
independent human meta-review record bound to that same head and digest, with a
PASS verdict, timestamp, and durable evidence reference. A self-review, stale
SHA, wrong digest, failed verdict, or reduced mandatory anchor baseline blocks.

Reject fork content before sending it to an external model provider, or route it
through an explicitly approved human manual process whose evidence is bound in
the same way. An automatically processed fork remains blocked. Never
interpolate an untrusted model value, diff instruction, check name, path, or
suggested command into a repair prompt or privileged controller input.

## Deterministic sequence

1. Resolve the trusted base from protected configuration.
2. Record the exact base and head commits.
3. Materialize the diff as inert data and compute its SHA-256 digest.
4. Record the head and digest immediately before review.
5. Run read-only review without merge or repository-write permission.
6. Record the head and digest again after review.
7. Block when either value changed.
8. Require the complete configured check-name set exactly once. Accept only the
   latest successful attempt bound to the locked head.
9. Apply deterministic blockers before considering any model verdict.
10. Hand the expected head to a separately authorized human or trusted merge
    controller. Require an atomic expected-head comparison at merge time.

A model PASS cannot clear a changed head, changed digest, missing or duplicated
check, stale attempt, failed check, fork-processing violation, permission
overlap, or unreviewed trust-anchor change.

## Trust anchors

Treat repository instructions, schemas, hooks, security policy, required-check
configuration, automation definitions, and merge-control policy as trust
anchors. A change to a trust anchor requires human approval and an independent
meta-review that does not rely on the policy being changed.

The `portable-v1` anchor profile is a minimum baseline. A repository may add
anchors but may not remove required instruction, agent, skill, schema, hook,
policy, registry, validation-script, or workflow categories.

Pin automation dependencies by immutable commit or content digest. A movable
tag, branch, channel, or release label is not an immutable ref.

## Permission separation

Give reviewers read-only access to the diff and source context. Keep merge write
authority in a separate controller or human session. Do not expose a
high-permission automatic merge workflow from this framework.

Secret scanning is one defense layer. Continue to prevent secret access, redact
context, minimize permissions, validate outputs, and review trust boundaries
even when the scanner passes.

When migrating a controller that combines review and merge authority, run the
new read-only reviewer in shadow mode and the separate expected-head controller
as a bounded canary. No migration exception may clear a deterministic blocker
or weaken a gate.

See `collaboration/examples/trusted-pr-control.yaml` for a PASS record.
