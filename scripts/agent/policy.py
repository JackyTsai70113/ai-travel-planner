from __future__ import annotations

import fnmatch
import json
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any


class PolicyError(ValueError):
    """Raised when the collaboration policy or a scoped path is invalid."""


_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def load_policy(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "agent-collaboration" / "project-policy.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"cannot load collaboration policy: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError("collaboration policy must be a JSON object")
    return value


def normalize_repo_path(value: str) -> str:
    candidate = value.strip().replace("\\", "/")
    while candidate.startswith("./"):
        candidate = candidate[2:]
    path = PurePosixPath(candidate)
    if not candidate or path.is_absolute() or ".." in path.parts:
        raise PolicyError(f"invalid repository-relative path: {value!r}")
    return path.as_posix()


def matches_path(path: str, pattern: str) -> bool:
    normalized_path = normalize_repo_path(path)
    normalized_pattern = normalize_repo_path(pattern)
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return normalized_path == prefix or normalized_path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(normalized_path, normalized_pattern)


def classify_paths(paths: Iterable[str], policy: dict[str, Any]) -> str:
    risk_rules = policy.get("risk")
    if not isinstance(risk_rules, dict):
        raise PolicyError("policy risk rules are missing")
    result = "low"
    saw_path = False
    for raw_path in paths:
        path = normalize_repo_path(raw_path)
        saw_path = True
        matched = next(
            (
                level
                for level in ("high", "medium", "low")
                if any(
                    matches_path(path, pattern) for pattern in risk_rules.get(level, [])
                )
            ),
            "high",
        )
        if _RISK_ORDER[matched] > _RISK_ORDER[result]:
            result = matched
    return result if saw_path else "low"


def domain_reviewers(paths: Iterable[str], policy: dict[str, Any]) -> list[str]:
    normalized = [normalize_repo_path(path) for path in paths]
    selected: list[str] = []
    for reviewer in policy.get("domain_reviewers", []):
        if not isinstance(reviewer, dict):
            raise PolicyError("domain reviewer entry must be an object")
        reviewer_id = reviewer.get("id")
        patterns = reviewer.get("paths")
        if not isinstance(reviewer_id, str) or not isinstance(patterns, list):
            raise PolicyError("domain reviewer entry is incomplete")
        if any(
            matches_path(path, pattern) for path in normalized for pattern in patterns
        ):
            selected.append(reviewer_id)
    return selected


def route_paths(paths: Iterable[str], policy: dict[str, Any]) -> dict[str, Any]:
    normalized = [normalize_repo_path(path) for path in paths]
    risk = classify_paths(normalized, policy)
    roles = policy.get("roles", {}).get(risk)
    if not isinstance(roles, dict):
        raise PolicyError(f"role routing is missing for risk {risk}")
    return {
        "risk": risk,
        "paths": normalized,
        "implementation_roles": list(roles.get("implementation", [])),
        "review_roles": list(roles.get("review", []))
        + domain_reviewers(normalized, policy),
    }


def path_is_owned(path: str, write_patterns: Iterable[str]) -> bool:
    return any(matches_path(path, pattern) for pattern in write_patterns)


def _static_prefix(pattern: str) -> str:
    normalized = normalize_repo_path(pattern)
    wildcard_positions = [
        position
        for position in (
            normalized.find("*"),
            normalized.find("?"),
            normalized.find("["),
        )
        if position >= 0
    ]
    if not wildcard_positions:
        return normalized
    return normalized[: min(wildcard_positions)].rstrip("/")


def ownership_patterns_overlap(left: str, right: str) -> bool:
    left_path = normalize_repo_path(left)
    right_path = normalize_repo_path(right)
    if matches_path(left_path, right_path) or matches_path(right_path, left_path):
        return True
    left_prefix = _static_prefix(left_path)
    right_prefix = _static_prefix(right_path)
    if not left_prefix or not right_prefix:
        return True
    return left_prefix.startswith(right_prefix + "/") or right_prefix.startswith(
        left_prefix + "/"
    )


def find_ownership_conflicts(
    requested: Iterable[str], existing: Iterable[tuple[Any, Iterable[str]]]
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    requested_paths = [normalize_repo_path(path) for path in requested]
    for issue_number, patterns in existing:
        for requested_path in requested_paths:
            for existing_path in patterns:
                if ownership_patterns_overlap(requested_path, existing_path):
                    conflicts.append(
                        {
                            "issue_number": issue_number if isinstance(issue_number, int) and issue_number > 0 else None,
                            "work_item": issue_number,
                            "requested": requested_path,
                            "existing": normalize_repo_path(existing_path),
                        }
                    )
    return conflicts
