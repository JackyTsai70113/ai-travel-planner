# Multi-agent GitHub development

This repository uses GitHub Issues or MR-first pull requests as the shared control plane, and external Git worktrees as the local isolation boundary. It adopts the portable contracts from `agentic-dev-collaboration` while keeping travel-specific correctness policy in this repository.

## What is supported

1. Multiple implementation agents can work concurrently on different work items.
2. Every Issue or MR-first request has a deterministic branch and external worktree.
3. Writable paths are declared before implementation; overlapping active ownership is rejected.
4. Risk classification selects implementation and independent review roles.
5. Handoffs include exact base/head SHAs, changed files, ownership, and test evidence.
6. A regular non-Draft PR is opened after local validation.
7. GitHub Actions independently validates the framework lock, Python suite, and renderer build.

GitHub is the durable coordination and review surface. Agent process scheduling is supplied by the active Codex session or another trusted runner; this repository does not store an API token or start a hosted agent by itself.

## One-time validation

```sh
python3 scripts/validate_agent_collaboration.py
python3 -m unittest discover -s tests -v
```

The upstream snapshot is pinned by commit and per-file SHA-256 values:

```text
vendor/agentic-dev-collaboration/
vendor/agentic-dev-collaboration.lock.json
```

Do not edit the snapshot. Project overrides belong in `agent-collaboration/`.

## Plan work items

Create Issues with `.github/ISSUE_TEMPLATE/agent-task.yml` when an Issue is useful. When no remote Issue exists, start directly from an MR-first request: the MR description must state observable acceptance criteria, proposed write ownership, dependencies, risk, validation, and the reason no Issue is linked. The MR description becomes the authoritative task envelope.

Use routing before delegation:

```sh
python3 -m scripts.agent.collaboration route \
  src/intent/parser.py \
  tests/test_travel_intent.py
```

The highest-risk changed path controls the whole task. Unknown paths fail closed as high risk.

Safe parallel example:

```text
Issue #28 owns src/intent/** and tests/test_travel_intent.py
Issue #29 owns src/reservations/** and tests/test_reservations.py
Issue #30 owns src/sources/official/** and tests/test_official_sources.py
```

Unsafe example:

```text
Issue #28 owns src/**
Issue #29 owns src/reservations/**
```

The second `prepare` is rejected while the first worktree remains active.

## Prepare each worktree

Run from the primary checkout:

```sh
git switch main
git pull --ff-only origin main

python3 -m scripts.agent.collaboration prepare 28 \
  --slug request-constraints \
  --write-path 'src/intent/**' \
  --write-path 'tests/test_travel_intent.py'

python3 -m scripts.agent.collaboration prepare 29 \
  --slug reservation-evidence \
  --write-path 'src/reservations/**' \
  --write-path 'tests/test_reservations.py'

# MR-first mode: no GitHub Issue is required.
python3 -m scripts.agent.collaboration prepare \
  --mr-slug request-constraints \
  --write-path 'src/intent/**' \
  --write-path 'tests/test_travel_intent.py'
```

If `--slug` is omitted, the command reads the Issue title through `gh`. MR-first mode uses the explicit `--mr-slug`, fetches `origin/main`, resolves its exact base SHA, creates `agent/mr-<slug>`, and records ownership in Git's shared common directory. The state is local metadata and is never committed to the product branch.

List prepared workspaces:

```sh
python3 -m scripts.agent.collaboration status
```

The orchestrator may now assign one writable agent to each returned worktree. Never assign a writable agent to the primary checkout.

## Validate ownership and hand off

Run inside the Issue worktree:

```sh
python3 -m scripts.agent.collaboration check 28
# or: python3 -m scripts.agent.collaboration check mr:request-constraints

python3 -m scripts.agent.collaboration handoff 28 \
  --test-evidence 'python3 -m unittest tests.test_travel_intent=PASS'
```

`check` verifies all of the following against Git reality:

1. Current directory is the registered canonical Issue worktree.
2. Current branch is the registered Issue branch.
3. Git's worktree registry agrees with local Issue state.
4. Every committed, staged, unstaged, and untracked changed file is inside declared ownership.

`handoff` adds exact base/head SHAs, current routing roles, test evidence, and a `ready_for_push` result. A dirty worktree or missing evidence is not ready.

## Publish a regular PR

After commit and local validation, run inside the Issue worktree:

```sh
python3 -m scripts.agent.collaboration publish 28 \
  --title 'feat: preserve explicit day constraints' \
  --test-evidence 'python3 -m unittest tests.test_travel_intent=PASS'
```

The command reruns ownership checks, rejects dirty or evidence-free worktrees, pushes the Issue or MR-first branch, and opens a regular non-Draft PR to `main`. It never enables auto-merge. If a PR already exists, it reports the existing PR rather than creating a duplicate. MR-first publishing requires `--body-file`; the body must contain the complete task envelope, acceptance criteria, write ownership, validation, and evidence. It does not need `Closes #...`.

Use `.github/PULL_REQUEST_TEMPLATE/agentic-checklist.md` to record acceptance coverage and the exact pushed head SHA.

## Review and integration

1. CI jobs `framework`, `python`, and `website` must pass.
2. Reviewers inspect the pushed exact head SHA and remain read-only.
3. Travel domain reviewers are routed by changed path from `agent-collaboration/project-policy.json`.
4. Any material fix invalidates an earlier verdict and requires review of the new SHA.
5. The user or an explicitly authorized merge process performs the final merge.
6. Dependent Issues rebase on the newly updated `origin/main`; agents do not copy unmerged worktree files.

## Failure boundaries

Implementation, tests, build, workflow, and repository failures are fixed in the Issue branch. A task pauses only for a verified permission, missing credential, external service, destructive product decision, or materially ambiguous requirement blocker.

The collaboration layer never grants provider credentials to agents and never places secrets in Issue state, GitHub output, Trip JSON, or rendered pages.
