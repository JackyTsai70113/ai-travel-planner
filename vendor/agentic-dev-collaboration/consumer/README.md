# Consumer Snapshot and Overlay

Vendor a pinned framework snapshot instead of depending on a sibling checkout
or a network fetch during consumer CI.

## Export

Pin only a post-merge commit that has passed required review and CI on the
canonical branch or an approved release. A feature-branch or pre-review commit
is not an adoptable framework release. Check out that exact commit in a clean
local worktree, pre-create real non-symlinked parent directories for the output
and lock, then run:

```bash
python3 scripts/export_consumer_snapshot.py export \
  --source-repo /path/to/framework \
  --source-ref <full-40-hex-commit> \
  --output-dir /path/to/consumer/vendor/framework \
  --lock-path /path/to/consumer/vendor/framework.lock.json
```

The exporter reads the manifest and every selected file from immutable Git
tree/blob objects at the validated full commit. It never copies worktree bytes,
so line-ending conversion and a concurrent checkout cannot alter the snapshot.
Every Git command uses `--no-replace-objects` plus a scrubbed Git environment;
caller-supplied repository, worktree, object, index, namespace, replace, and
config overrides cannot redirect identity or blob resolution.
It permits only the fixed canonical set and rejects symlinks, local remotes,
query/fragment-bearing remotes, unsafe paths, and sensitive path-name variants
such as `.env.*`, credential, secret, token, or key files.

Only normalized `https://`, `ssh://`, and legal SCP-like remotes are portable.
The lock records the normalized upstream URL, exact commit, sorted included
paths, and each file's Git mode plus SHA-256 hash. Only Git `100644` and `100755`
are portable: the committed snapshot must expose them as exact filesystem
permissions `0644` and `0755`. `snapshot_identity_sha256` covers
`schema_version`, normalized `upstream_url`, `commit`, and the complete entry
array; the digest field itself is excluded.

The output and lock must be absent and remain outside the source repository.
Every existing destination-parent component must be a real directory, never a
symlink. Export uses a private sibling staging directory, no-follow writes,
self-validation, and atomic publication; a failed export removes only its own
staging or published identity. Commit both results to the consumer repository.

## Validate offline

Run without an upstream checkout or network credential:

```bash
python3 vendor/framework/scripts/export_consumer_snapshot.py validate \
  --snapshot-dir vendor/framework \
  --lock-path vendor/framework.lock.json
```

Validation rejects missing, unknown, modified, unsafe, or symlinked files;
non-regular file types; non-portable remotes; mode changes; extra permission
bits such as group-write, set-id, or sticky bits; and any metadata, entry, or
identity-digest tampering. A platform that cannot enforce the exact portable
permission semantics must fail closed.
The result is deterministic because it contains no export time, local path, or
mutable ref.

## Apply consumer precedence

Apply policy in this order:

1. Consumer root `AGENTS.md` and security policy.
2. Project or domain overlays.
3. Pinned framework snapshot.
4. Generated runtime adapter output.

Let the stricter rule win. Fail closed when two rules cannot be reconciled.
Never let a generated adapter or pinned default weaken a higher consumer layer.
Use `schemas/consumer-overlay.schema.json` and
`consumer/examples/overlay.yaml` to record the sources.

Keep legacy runtime discovery in place while a thin generated adapter runs in
shadow mode and then a canary. Remove the legacy path only after the replacement
has proven equivalent discovery, policy, hook, and evidence behavior. Generated
adapters remain disposable and non-canonical.
