---
status: accepted
date: 2026-07-30
decision-makers:
  - repository-owner
consulted: []
informed: []
---

# ADR-0001: Keep canonical collaboration contracts vendor-neutral

## Context and problem statement

Coding-agent runtimes use different discovery paths, tool names, hook events,
agent formats, and model features. Encoding those differences in core policy
creates lock-in and duplicated, drifting instructions.

## Decision drivers

- Portability between agent runtimes.
- Reviewable and durable project policy.
- Deterministic validation.
- Low migration cost.

## Considered options

1. Maintain one full configuration per vendor.
2. Select one vendor as canonical.
3. Maintain vendor-neutral contracts and thin adapters.

## Decision outcome

Chosen option: "vendor-neutral contracts and thin adapters", because project
policy and evidence must outlive individual runtimes.

### Consequences

- Good: roles, skills, and audit artifacts can be reused.
- Good: vendor differences are isolated.
- Bad: adapter generation and compatibility testing are required.
- Neutral: not every runtime can enforce every permission.

## Validation

Validation rejects vendor names in canonical agent manifests and checks that
adapters declare unsupported capabilities.

## Rollback or supersession

Supersede this ADR if an industry standard fully covers role, permission,
workflow, and hook semantics without losing required controls.
