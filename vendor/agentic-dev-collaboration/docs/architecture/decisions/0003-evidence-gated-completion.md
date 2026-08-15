---
status: accepted
date: 2026-07-30
decision-makers:
  - repository-owner
consulted: []
informed: []
---

# ADR-0003: Completion requires independent, evidence-gated verification

## Context and problem statement

Implementers and reviewers may repeat the same assumption, report stale test
results, or mistake a plausible patch for a completed change.

## Decision drivers

- Auditable completion.
- Reduced false confidence.
- Clear blocked and partial states.
- Repeatable validation.

## Considered options

1. Trust implementer summaries.
2. Require review approval only.
3. Require an independent verifier and fresh evidence.

## Decision outcome

Chosen option: "independent verifier and fresh evidence".

### Consequences

- Good: completion claims map to observable proof.
- Good: missing proof remains visible.
- Bad: verification adds time and compute cost.
- Neutral: human approval remains necessary for product and risk decisions.

## Validation

The verdict contract requires acceptance-to-evidence mappings and distinguishes
PASS, FAIL, PARTIAL, and BLOCKED.

## Rollback or supersession

Individual low-risk repositories may define a reduced evidence profile, but
behavior changes still require fresh validation.
