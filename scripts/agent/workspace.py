from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.agent.policy import (
    find_ownership_conflicts,
    load_policy,
    normalize_repo_path,
    path_is_owned,
    route_paths,
)


class WorkspaceError(RuntimeError):
    """Raised when Git reality disagrees with Issue workspace ownership."""


@dataclass(frozen=True)
class IssueWorkspace:
    issue_number: int | None
    work_item: str
    branch: str
    worktree: Path
    base_ref: str
    base_sha: str
    write_paths: tuple[str, ...]
    read_only: bool


def _run(
    cwd: Path, *command: str, check: bool = True, capture: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        capture_output=capture,
        text=True,
    )


def git_value(cwd: Path, *arguments: str) -> str:
    try:
        return _run(cwd, "git", *arguments).stdout.strip()
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "git command failed").strip()
        raise WorkspaceError(detail) from exc


def repository_root(cwd: Path | None = None) -> Path:
    selected = (cwd or Path.cwd()).resolve()
    return Path(git_value(selected, "rev-parse", "--show-toplevel")).resolve()


def canonical_branch(issue_number: int | None, slug: str, prefix: str = "agent") -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise WorkspaceError("slug must use lowercase letters, digits, and hyphens")
    return f"{prefix}/issue-{issue_number}-{slug}" if issue_number is not None else f"{prefix}/mr-{slug}"


def issue_slug(title: str) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return "-".join(words[:8]) or "delivery"


def _github_issue(repo_root: Path, issue_number: int) -> dict[str, Any]:
    try:
        result = _run(
            repo_root,
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--json",
            "number,state,title",
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise WorkspaceError("cannot verify the GitHub Issue with gh") from exc
    try:
        issue = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WorkspaceError("GitHub Issue response is invalid") from exc
    if (
        not isinstance(issue, dict)
        or issue.get("number") != issue_number
        or issue.get("state") != "OPEN"
        or not isinstance(issue.get("title"), str)
        or not issue["title"]
    ):
        raise WorkspaceError("GitHub Issue must exist and be open")
    return issue


def canonical_worktree(repo_root: Path, issue_number: int | None, slug: str) -> Path:
    prefix = f"issue-{issue_number}" if issue_number is not None else "mr"
    return (
        repo_root.resolve().parent
        / ".worktrees"
        / repo_root.name
        / f"{prefix}-{slug}"
    ).resolve()


def _has_symlink_ancestor(path: Path) -> bool:
    current = path.absolute()
    while True:
        if current.is_symlink():
            return True
        if current.parent == current:
            return False
        current = current.parent


def _state_root(repo_root: Path) -> Path:
    common = Path(git_value(repo_root, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = repo_root / common
    return common.resolve() / "agent-collaboration" / "issues"


def _state_path(repo_root: Path, work_item: str) -> Path:
    return _state_root(repo_root) / f"{work_item.replace(':', '-')}.json"


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def load_state(repo_root: Path, work_item: str) -> dict[str, Any]:
    path = _state_path(repo_root, work_item)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkspaceError(
            f"Work item {work_item} has no prepared workspace"
        ) from exc
    except json.JSONDecodeError as exc:
        raise WorkspaceError(f"Work item {work_item} state is invalid") from exc
    if not isinstance(value, dict):
        raise WorkspaceError(f"Work item {work_item} state must be an object")
    return value


def all_states(repo_root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    state_root = _state_root(repo_root)
    if not state_root.exists():
        return result
    for path in sorted(state_root.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def prepare_workspace(
    *,
    repo_root: Path,
    issue_number: int | None,
    slug: str | None = None,
    write_paths: Iterable[str],
    read_only: bool = False,
    base_ref: str = "origin/main",
    fetch: bool = True,
    verify_issue: bool = True,
    mr_slug: str | None = None,
) -> IssueWorkspace:
    root = repo_root.resolve()
    if _has_symlink_ancestor(repo_root):
        raise WorkspaceError("repository path must not contain a symlink")
    policy = load_policy(root)
    if mr_slug is not None and issue_number is not None:
        raise WorkspaceError("choose either an Issue or MR-first mode, not both")
    if mr_slug is not None and (verify_issue or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", mr_slug)):
        raise WorkspaceError("MR-first mode requires a lowercase --mr-slug and skips GitHub Issue verification")
    github_issue = _github_issue(root, issue_number) if verify_issue else None
    if mr_slug is not None and slug is not None:
        raise WorkspaceError("use --mr-slug as the MR-first slug, not --slug")
    if mr_slug is None and slug is None and github_issue is None:
        raise WorkspaceError(
            "slug is required when GitHub Issue verification is disabled"
        )
    selected_slug = mr_slug or slug or issue_slug(str(github_issue["title"]))
    work_item = f"mr:{selected_slug}" if mr_slug is not None else f"issue:{issue_number}"
    prefix = policy["delivery"]["canonical_branch_prefix"]
    branch = canonical_branch(issue_number, selected_slug, prefix)
    if not re.fullmatch(policy["delivery"]["branch_pattern"], branch):
        raise WorkspaceError("canonical branch does not satisfy project policy")
    normalized_paths = tuple(normalize_repo_path(path) for path in write_paths)
    if read_only and normalized_paths:
        raise WorkspaceError("read-only workspace cannot declare write paths")
    if not read_only and not normalized_paths:
        raise WorkspaceError(
            "implementation workspace requires at least one --write-path"
        )

    existing_ownership: list[tuple[Any, Iterable[str]]] = []
    for state in all_states(root):
        state_issue = state.get("issue_number")
        state_work_item = state.get("work_item") or (f"issue:{state_issue}" if state_issue is not None else None)
        state_worktree = Path(str(state.get("worktree", "")))
        if state_work_item == work_item:
            raise WorkspaceError(
                f"Work item {work_item} already has a prepared workspace"
            )
        if state_worktree.is_dir() and not state.get("read_only"):
            existing_ownership.append((state_issue if state_issue is not None else state_work_item, state.get("write_paths", [])))
    conflicts = find_ownership_conflicts(normalized_paths, existing_ownership)
    if conflicts:
        first = conflicts[0]
        owner = f"Issue #{first['issue_number']}" if first["issue_number"] is not None else f"MR-first {first['work_item']}"
        raise WorkspaceError(
            f"write ownership overlaps {owner}: {first['requested']} <-> {first['existing']}"
        )

    if fetch:
        remote = policy["delivery"]["remote"]
        try:
            _run(root, "git", "fetch", "--prune", remote)
        except subprocess.CalledProcessError as exc:
            raise WorkspaceError((exc.stderr or "git fetch failed").strip()) from exc
        remote_branch = _run(
            root,
            "git",
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/remotes/{remote}/{branch}",
            check=False,
        )
        if remote_branch.returncode == 0:
            raise WorkspaceError(
                f"remote Issue branch already exists: {remote}/{branch}"
            )
    base_sha = git_value(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    worktree = canonical_worktree(root, issue_number, selected_slug)
    if worktree.exists():
        raise WorkspaceError(f"canonical worktree path already exists: {worktree}")
    worktree.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run(root, "git", "worktree", "add", "-b", branch, str(worktree), base_sha)
    except subprocess.CalledProcessError as exc:
        raise WorkspaceError((exc.stderr or "git worktree add failed").strip()) from exc

    state = {
        "schema_version": 1,
        "issue_number": issue_number,
        "slug": selected_slug,
        "branch": branch,
        "worktree": str(worktree),
        "base_ref": base_ref,
        "base_sha": base_sha,
        "write_paths": list(normalized_paths),
        "read_only": read_only,
        "status": "PREPARED",
        "routing": route_paths(normalized_paths, policy),
    }
    state["work_item"] = work_item
    _write_json_atomic(_state_path(root, work_item), state)
    return IssueWorkspace(
        issue_number=issue_number,
        work_item=work_item,
        branch=branch,
        worktree=worktree,
        base_ref=base_ref,
        base_sha=base_sha,
        write_paths=normalized_paths,
        read_only=read_only,
    )


def _worktree_registry(repo_root: Path) -> dict[Path, str]:
    records: dict[Path, str] = {}
    raw = git_value(repo_root, "worktree", "list", "--porcelain")
    for block in raw.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            fields[key] = value
        if fields.get("worktree"):
            records[Path(fields["worktree"]).resolve()] = fields.get(
                "branch", ""
            ).removeprefix("refs/heads/")
    return records


def assert_workspace(
    repo_root: Path, issue_number: int | None, worktree: Path | None = None, mr_slug: str | None = None
) -> IssueWorkspace:
    root = repo_root.resolve()
    work_item = f"mr:{mr_slug}" if mr_slug is not None else f"issue:{issue_number}"
    state = load_state(root, work_item)
    expected = Path(state["worktree"]).resolve()
    selected = (worktree or Path.cwd()).resolve()
    if selected != expected:
        raise WorkspaceError(
            f"current directory is not work item {work_item} canonical worktree"
        )
    if _has_symlink_ancestor(worktree or Path.cwd()) or not selected.is_dir():
        raise WorkspaceError("Issue worktree is missing or symlinked")
    top_level = Path(git_value(selected, "rev-parse", "--show-toplevel")).resolve()
    branch = git_value(selected, "branch", "--show-current")
    if top_level != expected or branch != state["branch"]:
        raise WorkspaceError("Git branch/worktree reality disagrees with Issue state")
    if _worktree_registry(root).get(expected) != branch:
        raise WorkspaceError("Git worktree registry disagrees with Issue state")
    return IssueWorkspace(
        issue_number=issue_number,
        work_item=state.get("work_item", work_item),
        branch=branch,
        worktree=expected,
        base_ref=state["base_ref"],
        base_sha=state["base_sha"],
        write_paths=tuple(state.get("write_paths", [])),
        read_only=bool(state.get("read_only")),
    )


def changed_files(workspace: IssueWorkspace) -> list[str]:
    diff = _run(
        workspace.worktree,
        "git",
        "diff",
        "--name-only",
        "-z",
        f"{workspace.base_sha}...HEAD",
    ).stdout
    committed = {path for path in diff.split("\0") if path}
    status = _run(
        workspace.worktree,
        "git",
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ).stdout
    entries = status.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        code = entry[:2]
        committed.add(entry[3:])
        if "R" in code or "C" in code:
            if index < len(entries) and entries[index]:
                committed.add(entries[index])
            index += 1
    return sorted(normalize_repo_path(path) for path in committed if path)


def check_ownership(workspace: IssueWorkspace) -> dict[str, Any]:
    files = changed_files(workspace)
    violations = (
        files
        if workspace.read_only
        else [path for path in files if not path_is_owned(path, workspace.write_paths)]
    )
    if violations:
        raise WorkspaceError(
            "changed files outside declared ownership: " + ", ".join(violations)
        )
    dirty = bool(
        _run(
            workspace.worktree,
            "git",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ).stdout
    )
    return {
        "issue_number": workspace.issue_number,
        "work_item": workspace.work_item,
        "branch": workspace.branch,
        "worktree": str(workspace.worktree),
        "changed_files": files,
        "write_paths": list(workspace.write_paths),
        "dirty": dirty,
        "ownership": "PASS",
    }


def handoff(workspace: IssueWorkspace, test_evidence: Iterable[str]) -> dict[str, Any]:
    ownership = check_ownership(workspace)
    policy = load_policy(repository_root(workspace.worktree))
    head_sha = git_value(workspace.worktree, "rev-parse", "HEAD")
    evidence = list(test_evidence)
    return {
        **ownership,
        "base_sha": workspace.base_sha,
        "head_sha": head_sha,
        "routing": route_paths(ownership["changed_files"], policy),
        "test_evidence": evidence,
        "ready_for_push": not ownership["dirty"] and bool(evidence),
    }
