from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agent.policy import PolicyError, load_policy


class ValidationError(ValueError):
    """Raised when the collaboration control plane is incomplete or inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid JSON: {exc}") from exc
    _require(isinstance(value, dict), f"{path.relative_to(ROOT)} must be a JSON object")
    return value


def _validate_snapshot(policy: dict[str, Any]) -> None:
    framework = policy.get("framework")
    _require(isinstance(framework, dict), "framework policy is missing")
    snapshot = ROOT / str(framework.get("snapshot_path"))
    lock_path = ROOT / str(framework.get("lock_path"))
    lock = _load_json(lock_path)
    _require(
        lock.get("schema_version") == "1.0", "snapshot lock schema version mismatch"
    )
    _require(lock.get("commit") == framework.get("commit"), "snapshot commit mismatch")
    _require(
        lock.get("upstream_url") == framework.get("upstream_url"),
        "snapshot upstream URL mismatch",
    )
    entries = lock.get("included_paths")
    _require(isinstance(entries, list), "snapshot lock included_paths must be a list")
    _require(
        len(entries) == framework.get("expected_file_count"),
        "snapshot file count does not match project policy",
    )
    locked_paths: set[str] = set()
    for entry in entries:
        _require(isinstance(entry, dict), "snapshot lock entry must be an object")
        relative = entry.get("path")
        digest = entry.get("sha256")
        mode = entry.get("mode")
        _require(
            isinstance(relative, str) and relative, "snapshot lock path is invalid"
        )
        _require(relative not in locked_paths, f"duplicate snapshot path: {relative}")
        locked_paths.add(relative)
        target = snapshot / relative
        _require(
            target.is_file() and not target.is_symlink(),
            f"snapshot file missing: {relative}",
        )
        actual_digest = hashlib.sha256(target.read_bytes()).hexdigest()
        _require(actual_digest == digest, f"snapshot hash mismatch: {relative}")
        _require(
            isinstance(mode, str)
            and re.fullmatch(r"100[67][0-7][0-7]", mode) is not None,
            f"snapshot mode invalid: {relative}",
        )
        actual_mode = os.stat(target).st_mode & 0o777
        _require(
            actual_mode == int(mode[-3:], 8), f"snapshot mode mismatch: {relative}"
        )
    actual_paths = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file()
    }
    _require(
        actual_paths == locked_paths,
        "snapshot contains files not represented by its lock",
    )


def _validate_policy(policy: dict[str, Any]) -> None:
    _require(policy.get("schema_version") == "1.0", "project policy schema mismatch")
    delivery = policy.get("delivery")
    _require(isinstance(delivery, dict), "delivery policy is missing")
    pattern = delivery.get("branch_pattern")
    _require(isinstance(pattern, str), "branch pattern is missing")
    compiled = re.compile(pattern)
    _require(
        compiled.fullmatch("agent/issue-28-example") is not None,
        "branch pattern rejects canonical branch",
    )
    _require(
        compiled.fullmatch("agent/mr-request-constraints") is not None,
        "branch pattern rejects MR-first branch",
    )
    _require(
        compiled.fullmatch("agent/example") is None,
        "branch pattern accepts non-Issue branch",
    )
    _require(
        delivery.get("pull_request_state") == "ready", "pull requests must be non-Draft"
    )
    _require(
        delivery.get("automatic_merge") is False, "automatic merge must remain disabled"
    )
    parallelism = policy.get("parallelism")
    _require(isinstance(parallelism, dict), "parallelism policy is missing")
    for gate in (
        "one_work_item_per_worktree",
        "one_writer_per_path",
        "reviewers_read_only",
        "require_declared_write_paths",
    ):
        _require(parallelism.get(gate) is True, f"parallelism gate disabled: {gate}")
    checks = policy.get("required_checks")
    _require(checks == ["framework", "python", "website"], "required CI jobs mismatch")


def _validate_domain_agents(policy: dict[str, Any]) -> None:
    forbidden = {"write_repository", "fix_findings", "approve_own_work", "deploy"}
    configured = policy.get("domain_reviewers")
    _require(
        isinstance(configured, list) and configured, "domain reviewers are missing"
    )
    seen: set[str] = set()
    for reviewer in configured:
        _require(isinstance(reviewer, dict), "domain reviewer policy entry is invalid")
        reviewer_id = reviewer.get("id")
        manifest_path = reviewer.get("manifest")
        _require(
            isinstance(reviewer_id, str) and reviewer_id not in seen,
            "domain reviewer id is invalid",
        )
        _require(
            isinstance(manifest_path, str), f"{reviewer_id}: manifest path is missing"
        )
        seen.add(reviewer_id)
        manifest = _load_json(ROOT / manifest_path)
        _require(
            manifest.get("id") == reviewer_id, f"{reviewer_id}: manifest id mismatch"
        )
        _require(
            manifest.get("mode") == "read_only", f"{reviewer_id}: must be read-only"
        )
        _require(
            manifest.get("path_policy", {}).get("write") == [],
            f"{reviewer_id}: write paths forbidden",
        )
        denied = set(manifest.get("tools", {}).get("deny", []))
        _require(
            forbidden <= denied, f"{reviewer_id}: required denied tools are missing"
        )


def _validate_repository_contracts() -> None:
    required = [
        "AGENTS.md",
        ".github/PULL_REQUEST_TEMPLATE/agentic-checklist.md",
        ".github/ISSUE_TEMPLATE/agent-task.yml",
        ".github/workflows/ci.yml",
        "agent-collaboration/overlay.json",
        "docs/agents/DEVELOPMENT.md",
    ]
    for relative in required:
        _require(
            (ROOT / relative).is_file(),
            f"required collaboration file missing: {relative}",
        )
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for phrase in (
        "最新的 `origin/main`",
        "一個外部 Git worktree",
        "寫入路徑不重疊",
        "regular、非 Draft",
        "不得自動 merge",
    ):
        _require(phrase in agents, f"AGENTS.md contract missing: {phrase}")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for command in (
        "python3 scripts/validate_agent_collaboration.py",
        "python3 -m unittest discover -s tests -v",
        "python3 -m src.renderer.build_site",
    ):
        _require(command in workflow, f"CI workflow command missing: {command}")
    template = (ROOT / ".github/PULL_REQUEST_TEMPLATE/agentic-checklist.md").read_text(
        encoding="utf-8"
    )
    for phrase in ("Issue", "MR-first", "write ownership", "exact head SHA", "non-Draft"):
        _require(phrase in template, f"PR template evidence field missing: {phrase}")
    overlay = _load_json(ROOT / "agent-collaboration" / "overlay.json")
    _require(
        overlay.get("precedence")
        == ["consumer_root", "project_domain_overlay", "pinned_framework"],
        "collaboration overlay precedence mismatch",
    )
    _require(
        overlay.get("conflict_resolution") == "stricter_wins_fail_closed",
        "collaboration overlay must fail closed",
    )


def validate() -> dict[str, Any]:
    try:
        policy = load_policy(ROOT)
    except PolicyError as exc:
        raise ValidationError(str(exc)) from exc
    _validate_snapshot(policy)
    _validate_policy(policy)
    _validate_domain_agents(policy)
    _validate_repository_contracts()
    return {
        "status": "PASS",
        "framework_commit": policy["framework"]["commit"],
        "snapshot_files": policy["framework"]["expected_file_count"],
        "domain_reviewers": len(policy["domain_reviewers"]),
        "required_checks": policy["required_checks"],
    }


def main() -> int:
    try:
        result = validate()
    except ValidationError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
