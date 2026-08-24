# AI Travel Planner agent development contract

## Source of truth

1. Every implementation starts from the latest `origin/main`.
2. The GitHub Issue acceptance criteria, or the MR description when using MR-first mode, and this file are authoritative.
3. Canonical Trip remains the product source of truth. Agent collaboration may not bypass the existing Research, Planning, Optimization, Validation, and Rendering boundaries.

## Parallel development boundary

1. One work item maps to one branch and one external Git worktree. A work item is either an open GitHub Issue or an MR-first request.
2. Issue branch: `agent/issue-<number>-<slug>`; MR-first branch: `agent/mr-<slug>`.
3. Canonical worktree: `../.worktrees/ai-travel-planner/issue-<number>-<slug>` or `../.worktrees/ai-travel-planner/mr-<slug>`.
4. Implementation agents may run in parallel only when their declared write paths do not overlap.
5. Each writable path has one owner. Other agents are read-only for that path.
6. Review agents are always read-only and may not fix or approve their own findings.
7. Do not let multiple implementation agents edit the primary checkout.
8. One integration owner resolves cross-Issue dependencies through GitHub PRs; agents must not copy unmerged changes between worktrees.

Use the repository guard before delegating writable work:

```sh
python3 -m scripts.agent.collaboration prepare 28 \
  --slug request-constraints \
  --write-path 'src/intent/**' \
  --write-path 'tests/test_travel_intent.py'
```

Before commit, push, or handoff:

```sh
python3 -m scripts.agent.collaboration check 28
python3 -m scripts.agent.collaboration handoff 28 \
  --test-evidence 'python3 -m unittest tests.test_travel_intent=PASS'
```

## Risk and role routing

Run `python3 -m scripts.agent.collaboration route <changed-path>...` before delegation.

1. Low risk: `core.executor`, followed by `core.code-reviewer`.
2. Medium risk: `core.planner`, `core.executor`, `core.test-engineer`, followed by `core.code-reviewer` and the routed domain reviewer.
3. High risk: `core.explorer`, `core.architect`, `core.planner`, `core.executor`, `core.test-engineer`, followed by `core.spec-reviewer`, `core.code-reviewer`, `core.verifier`, and routed domain reviewers.
4. A higher-risk path makes the whole change higher risk.
5. Domain reviewers are defined in `agent-collaboration/agents/` and are read-only.

## Required delivery lifecycle

Unless the user explicitly limits the task to local changes or analysis:

1. Read the Issue and identify acceptance criteria, or write the scope, acceptance criteria, ownership, risk, dependencies, and validation plan in the MR description before starting MR-first work.
2. Prepare the dedicated Issue worktree from latest `origin/main`.
3. Declare non-overlapping write ownership before spawning implementation agents.
4. Implement the smallest complete change.
5. Run repository validation and relevant tests.
6. Run the collaboration ownership check.
7. Commit and push the Issue branch.
8. Open a regular, non-Draft PR to `main` using the repository PR template. In MR-first mode, provide `--body-file`; the MR description is the source of truth and must contain the full acceptance criteria and evidence fields; no Issue reference is required.
9. Inspect CI; fix repository-caused failures and repeat until green or a verified external blocker exists.
10. Hand the exact pushed head SHA, changed files, acceptance criteria, and test evidence to an independent reviewer.
11. Re-review after any material fix because an older verdict does not cover a newer SHA.

Do not stop after local implementation when push, PR, CI, and review remain in scope. Do not automatically merge unless the user or repository policy explicitly authorizes it.

## Evidence requirements

A handoff must contain:

1. Issue and PR numbers when an Issue exists; otherwise the MR URL/number and the MR-first work-item slug.
2. Base and head SHAs.
3. Declared write paths and actual changed files.
4. Acceptance criteria coverage.
5. Exact local test commands and results.
6. CI check results.
7. Known warnings, unverified behavior, and blockers.

Claims such as “implemented”, “tested”, “CI passed”, or “reviewed” require current evidence bound to the exact head SHA.

## CI failure handling

1. Inspect the failed job, step, and log before changing code.
2. Fix implementation, test, build, workflow, or repository failures that are in scope.
3. Do not label a repeated green rerun as a flaky-test fix without evidence.
4. Escalate only verified permission, credential, service, or product-decision blockers.
5. Required CI must pass before the work is reported complete.

## Project-specific correctness gates

Changes touching the following areas require the corresponding read-only reviewer:

1. `src/schemas/**`, `fixtures/trips/**`, or canonical contract docs: `domain.trip-schema-reviewer`.
2. `src/planner/**`, `src/optimizer/**`, `src/validator/**`, routing, or production orchestration: `domain.itinerary-invariant-reviewer`.
3. `src/sources/**`, provider adapters, restaurant evidence, or provenance docs: `domain.source-provenance-auditor`.

Never use provider-specific raw payloads inside planner logic, treat unknown routing as zero, assume unknown opening hours are open, expose credentials, or render an invalid trip as successful.

## Framework integrity

1. `vendor/agentic-dev-collaboration/` is a pinned upstream snapshot. Do not edit it in place.
2. `vendor/agentic-dev-collaboration.lock.json` must verify before delivery.
3. Project overrides live under `agent-collaboration/`.
4. Run `python3 scripts/validate_agent_collaboration.py` after collaboration-policy changes.
