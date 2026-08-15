# Agent Manifests

Agent manifests describe responsibilities, permissions, inputs, outputs, and
handoffs without embedding a vendor-specific system prompt.

## Naming

- Core roles: `core.<role>`.
- Platform roles: `<platform>.<role>`.
- Domain roles added by consumers: `domain.<name>`.

## Permission interpretation

Capability and tool names are semantic. A runtime adapter maps them to actual
tools. If an exact safe mapping is unavailable, the adapter must omit the
capability and report the limitation.

Write paths are examples until a consumer repository replaces them with actual
path rules. Placeholder paths must never be interpreted as wildcards.

## Prompt generation

A runtime-specific prompt may be generated from:

1. The role identity and summary.
2. Allowed capabilities and paths.
3. Required inputs and outputs.
4. Constraints.
5. Project policy from `AGENTS.md`.

Generated prompts are disposable and must not become a competing source of
truth.
