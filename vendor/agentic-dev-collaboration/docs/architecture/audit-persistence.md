# Audit Persistence

`artifacts/runs/<run-id>/` is durable evidence, not a cache. A consumer must use
one of these persistence modes:

1. Commit closed run directories to protected Git history.
2. Upload them to append-only object storage and retain stable references plus
   retention metadata in the run record.

Closeout is not valid until persistence succeeds. Closed records are never
overwritten or deleted by an agent; corrections append an event or create a
superseding record.

The repository ignores only `artifacts/local-runs/`, which is disposable
workspace data and cannot satisfy a gate. `artifacts/runs/` is intentionally not
ignored. A consumer using external storage may keep payloads out of Git only
after the durable upload and reference are verified.
