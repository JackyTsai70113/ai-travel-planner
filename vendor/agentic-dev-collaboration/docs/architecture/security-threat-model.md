# Security Threat Model

## Assets

- Source code and version history.
- Credentials and signing material.
- Specifications and architecture decisions.
- Build, release, and deployment systems.
- User and production data.
- Agent prompts, skills, tools, and execution records.

## Trust boundaries

- Human request to orchestrator.
- Repository content to agent context.
- External content and MCP responses to agent context.
- Agent output to tools.
- Worker handoff to another worker.
- Generated patch to repository.
- Repository to CI, release, and production systems.

## Threats and controls

| Threat | Control |
| --- | --- |
| Prompt injection in files or web content | Treat content as data; restrict tools; require approval for writes |
| Malicious skill or adapter | Review source; pin version; verify checksums or commit |
| Excessive agency | Explicit tool allowlists and human approval boundaries |
| Secret leakage | Deny secret paths; redact logs; scan commits |
| Reviewer rubber-stamping | Independent context, file evidence, deterministic checks |
| Unbounded loops | Retry, token, time, and cost budgets |
| Conflicting parallel edits | Path ownership and isolated worktrees |
| Compromised dependency | Lock files, dependency review, minimal runtime dependencies |
| Unsafe generated command | Allowlisted commands and shell argument validation |
| False completion | Fresh verifier evidence and explicit verdict schema |
| Untrusted pull-request instructions | Treat the diff as inert data; never interpolate it into privileged control input |
| Head changes during review | Lock head and diff digest before and after; fail closed on either change |
| Fork content sent externally | Reject before external processing or require an approved manual path |
| Stale or ambiguous checks | Require the complete unique check set and latest attempt for the locked head |
| Model verdict bypasses policy | Evaluate deterministic blockers first; model output cannot clear them |
| Review session can merge | Separate read-only review from expected-head merge authority |
| Trust-anchor self-approval | Require human approval and independent meta-review |
| Movable automation dependency | Pin by immutable commit or content digest |
| Worktree conversion changes exported bytes | Read tree and blob objects from the exact validated commit |
| Replace refs or inherited Git environment redirects objects | Disable replacement and scrub all caller-provided Git overrides for every command |
| Destination symlink or parent swap | Traverse with no-follow directory handles, stage privately, verify identity, publish atomically |
| Lock metadata changes without file changes | Bind schema, normalized remote, commit, and complete entries in one identity digest |
| Executable mode changes without content changes | Bind Git mode and require exact no-follow regular-file permissions offline |

## High-impact actions

The following require explicit human approval even if a runtime supports them:

- Production deployment or release.
- Credential or secret changes.
- Destructive data operations.
- Access-control or permission expansion.
- Signing, store submission, or publishing.
- Protected branch or CI permission changes.
- Disabling security, test, or audit controls.

See [trusted pull request control](trusted-pr-control.md) for the portable
control record and merge-readiness threat model.
