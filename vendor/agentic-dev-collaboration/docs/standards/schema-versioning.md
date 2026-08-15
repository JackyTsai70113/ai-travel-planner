# Schema Versioning and Compatibility

Every artifact carries `schema_version`. The validator supports only versions
whose full semantics it can enforce; an unknown version fails closed.

- Patch versions correct documentation without changing accepted instances.
- Minor versions add backward-compatible optional fields or enum values.
- Major versions make a field required, change its representation, or strengthen
  lifecycle semantics in a way that requires migration.

Current contract versions:

| Contract | Version | Compatibility note |
| --- | --- | --- |
| Lesson | 1.0 | Initial contract |
| Agent manifest, platform profile | 1.0 | Initial contract |
| Runtime policy | 1.0 | Initial contract |
| Event policy | 3.0 | Executable allowlist entries declare a fail-closed kind |
| Task envelope | 2.0 | Terminal cancellation is represented explicitly |
| Hooks manifest | 2.0 | Blocking hooks receive trusted actor identity and mode |
| Review verdict | 2.0 | Every outcome has a summary; PARTIAL is explicit |
| Adapter declaration | 2.0 | Trusted identity and automatic command support are explicit |
| Finding | 3.0 | Fixed and verified findings require resolution proof |
| Handoff | 2.0 | Assignments explicitly authorize command IDs |
| Plan | 2.0 | Approved plans define trusted required command argv |
| Hook event | 4.0 | Reviews reference verdicts and canonical event coverage is complete |
| Verification verdict | 3.0 | PASS commands must match the approved plan |
| Run record | 3.0 | Completed runs reference their approved plan |
| Trusted pull-request control | 1.0 | Trusted base, immutable diff, bound human evidence, checks, permissions, and merge head |
| Consumer snapshot manifest | 1.0 | Fixed portable framework include set |
| Consumer snapshot lock | 1.0 | Pinned upstream identity plus deterministic per-file mode and hashes |
| Consumer overlay | 1.0 | Fixed policy precedence with fail-closed conflicts |

New major contracts intentionally reject their earlier forms. Adapters must
migrate stored payloads or retain a matching historical validator; they must not
rewrite closed run records in place.
