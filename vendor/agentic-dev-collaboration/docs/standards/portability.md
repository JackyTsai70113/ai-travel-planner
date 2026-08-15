# Portability Standards

## Canonical formats

| Concern | Canonical format |
| --- | --- |
| Repository instructions | `AGENTS.md` |
| Reusable workflow | Agent Skills-compatible `SKILL.md` |
| Agent role | YAML manifest validated by JSON Schema |
| Requirements and plans | Markdown with YAML frontmatter |
| Architecture decision | MADR-style Markdown |
| Collaboration payload | YAML or JSON validated by JSON Schema |
| Tool integration | MCP where an external tool protocol is needed |
| Deterministic gate | Script, Git hook, or CI workflow |

## Adapter contract

Adapters may:

- Map canonical roles to runtime agent definitions.
- Map capability names to available tools.
- Install skills into runtime discovery paths.
- Translate lifecycle events into canonical hook events.
- Surface unsupported capabilities.

Adapters may not:

- Change role permissions silently.
- Remove quality gates.
- duplicate and fork canonical policy.
- select a weaker validation command without recording the difference.
- embed secrets.

## Compatibility levels

- Level 0: runtime can read repository instructions.
- Level 1: runtime can discover portable skills.
- Level 2: runtime can create isolated role contexts.
- Level 3: runtime can enforce per-role tools and permissions.
- Level 4: runtime can emit lifecycle events and structured evidence.

An adapter must declare its supported level and limitations.

Machine-readable declarations conform to
`schemas/adapter-declaration.schema.json`. Canonical capabilities and tools are
defined in `registries/runtime-policy.yaml`; adapters map from that registry
rather than inventing implicit authority.

Executable authorization is separately defined by
`registries/event-policy.yaml:allowed_executables`. Each entry declares a
canonical name and whether it is a `direct_tool`, `interpreter`, `shell`, or
`dispatcher`; only `direct_tool` is eligible for automatic execution. A
consumer may extend its active project copy for required platform checks, but
the addition is an independently reviewed policy change and does not replace
exact plan argv or handoff command-ID authorization. Runtime discovery or
adapter availability must never implicitly add or reclassify an executable.
