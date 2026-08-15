from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.agent.policy import PolicyError, load_policy, route_paths
from scripts.agent.workspace import (
    WorkspaceError,
    all_states,
    assert_workspace,
    check_ownership,
    git_value,
    handoff,
    prepare_workspace,
    repository_root,
)


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _workspace_for_issue(issue_number: int):
    root = repository_root()
    return root, assert_workspace(root, issue_number)


def _default_pr_body(issue_number: int, evidence: dict[str, Any]) -> str:
    changed = (
        "\n".join(f"  - `{path}`" for path in evidence["changed_files"]) or "  - none"
    )
    ownership = (
        "\n".join(f"  - `{path}`" for path in evidence["write_paths"])
        or "  - read-only"
    )
    tests = "\n".join(f"  - `{item}`" for item in evidence["test_evidence"])
    return (
        f"Closes #{issue_number}\n\n"
        "## Agent handoff evidence\n\n"
        f"- Base SHA: `{evidence['base_sha']}`\n"
        f"- Exact head SHA: `{evidence['head_sha']}`\n"
        f"- Risk: `{evidence['routing']['risk']}`\n"
        "- PR state: regular non-Draft\n\n"
        "### Declared write ownership\n\n"
        f"{ownership}\n\n"
        "### Changed files\n\n"
        f"{changed}\n\n"
        "### Local validation\n\n"
        f"{tests}\n\n"
        "### Required review roles\n\n"
        + "\n".join(f"  - `{role}`" for role in evidence["routing"]["review_roles"])
        + "\n"
    )


def _publish(arguments: argparse.Namespace) -> dict[str, Any]:
    root, workspace = _workspace_for_issue(arguments.issue)
    evidence = handoff(workspace, arguments.test_evidence)
    if not evidence["ready_for_push"]:
        raise WorkspaceError("publish requires a clean worktree and test evidence")
    subprocess.run(
        ["git", "push", "--set-upstream", "origin", workspace.branch],
        cwd=workspace.worktree,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        existing = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                workspace.branch,
                "--json",
                "number,url,isDraft,headRefOid",
            ],
            cwd=workspace.worktree,
            check=True,
            capture_output=True,
            text=True,
        )
        pull_request = json.loads(existing.stdout)
    except subprocess.CalledProcessError:
        command = [
            "gh",
            "pr",
            "create",
            "--base",
            load_policy(root)["delivery"]["base_branch"],
            "--head",
            workspace.branch,
            "--title",
            arguments.title,
        ]
        if arguments.body_file:
            command.extend(["--body-file", str(arguments.body_file)])
        else:
            command.extend(
                ["--body", _default_pr_body(workspace.issue_number, evidence)]
            )
        created = subprocess.run(
            command,
            cwd=workspace.worktree,
            check=True,
            capture_output=True,
            text=True,
        )
        pull_request = {"url": created.stdout.strip(), "isDraft": False}
    if pull_request.get("isDraft") is True:
        raise WorkspaceError("repository policy forbids Draft PRs")
    expected_head = git_value(workspace.worktree, "rev-parse", "HEAD")
    reported_head = pull_request.get("headRefOid")
    if reported_head is not None and reported_head != expected_head:
        raise WorkspaceError("existing PR does not point to the pushed exact head SHA")
    return {"handoff": evidence, "pull_request": pull_request}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Prepare and guard parallel GitHub Issue worktrees for development agents."
    )
    commands = value.add_subparsers(dest="command", required=True)

    route = commands.add_parser(
        "route", help="Classify changed paths and select agent roles."
    )
    route.add_argument("paths", nargs="+")

    prepare = commands.add_parser(
        "prepare", help="Create one canonical Issue worktree."
    )
    prepare.add_argument("issue", type=int)
    prepare.add_argument("--slug")
    prepare.add_argument("--write-path", action="append", default=[])
    prepare.add_argument("--read-only", action="store_true")
    prepare.add_argument("--base-ref", default="origin/main")
    prepare.add_argument("--no-fetch", action="store_true")
    prepare.add_argument(
        "--no-github-check", action="store_true", help=argparse.SUPPRESS
    )

    check = commands.add_parser(
        "check", help="Verify branch, worktree, and write ownership."
    )
    check.add_argument("issue", type=int)

    handoff_parser = commands.add_parser(
        "handoff", help="Emit exact-SHA handoff evidence."
    )
    handoff_parser.add_argument("issue", type=int)
    handoff_parser.add_argument("--test-evidence", action="append", default=[])

    status = commands.add_parser("status", help="List prepared Issue workspaces.")
    status.add_argument("--issue", type=int)

    publish = commands.add_parser(
        "publish", help="Push and open a regular non-Draft PR."
    )
    publish.add_argument("issue", type=int)
    publish.add_argument("--title", required=True)
    publish.add_argument("--body-file", type=Path)
    publish.add_argument("--test-evidence", action="append", default=[])
    return value


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        root = repository_root()
        if arguments.command == "route":
            _emit(route_paths(arguments.paths, load_policy(root)))
        elif arguments.command == "prepare":
            workspace = prepare_workspace(
                repo_root=root,
                issue_number=arguments.issue,
                slug=arguments.slug,
                write_paths=arguments.write_path,
                read_only=arguments.read_only,
                base_ref=arguments.base_ref,
                fetch=not arguments.no_fetch,
                verify_issue=not arguments.no_github_check,
            )
            _emit(workspace.__dict__ | {"worktree": str(workspace.worktree)})
        elif arguments.command == "check":
            _, workspace = _workspace_for_issue(arguments.issue)
            _emit(check_ownership(workspace))
        elif arguments.command == "handoff":
            _, workspace = _workspace_for_issue(arguments.issue)
            _emit(handoff(workspace, arguments.test_evidence))
        elif arguments.command == "status":
            states = all_states(root)
            if arguments.issue is not None:
                states = [
                    state
                    for state in states
                    if state.get("issue_number") == arguments.issue
                ]
            _emit({"workspaces": states})
        elif arguments.command == "publish":
            _emit(_publish(arguments))
    except (
        PolicyError,
        WorkspaceError,
        FileNotFoundError,
        subprocess.CalledProcessError,
    ) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
