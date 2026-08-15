"""Validate the vendor-neutral collaboration contracts and lifecycle gates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

try:
    from scripts.export_consumer_snapshot import (
        SnapshotError,
        normalize_remote_url,
        path_component_is_sensitive,
        snapshot_identity_digest,
    )
except ModuleNotFoundError:
    from export_consumer_snapshot import (  # type: ignore[no-redef]
        SnapshotError,
        normalize_remote_url,
        path_component_is_sensitive,
        snapshot_identity_digest,
    )

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_CORE_AGENTS = {
    "core.orchestrator",
    "core.explorer",
    "core.architect",
    "core.planner",
    "core.executor",
    "core.test-engineer",
    "core.spec-reviewer",
    "core.code-reviewer",
    "core.verifier",
    "core.security-reviewer",
}

REQUIRED_MODES = {
    "coordinator",
    "read_only",
    "plan_write",
    "production_write",
    "test_write",
    "verify_execute",
}

VENDOR_TERMS = re.compile(
    r"\b(chatgpt|claude|codex|copilot|gemini|openai|anthropic)\b",
    re.IGNORECASE,
)

EXAMPLE_SCHEMAS = {
    "task-envelope.yaml": "task-envelope.schema.json",
    "finding.yaml": "finding.schema.json",
    "verdict.yaml": "verdict.schema.json",
    "handoff.yaml": "handoff.schema.json",
    "run-record.yaml": "run-record.schema.json",
    "lesson.yaml": "lesson.schema.json",
    "plan.yaml": "plan.schema.json",
    "spec-review-verdict.yaml": "review-verdict.schema.json",
    "code-review-verdict.yaml": "review-verdict.schema.json",
    "security-review-verdict.yaml": "review-verdict.schema.json",
    "contract-review-verdict.yaml": "review-verdict.schema.json",
    "trusted-pr-control.yaml": "trusted-pr-control.schema.json",
}

EVENT_ARTIFACT_FIELDS = {
    "task.accepted": ("task_envelope_path",),
    "plan.proposed": ("task_envelope_path", "plan_path"),
    "plan.approved": ("task_envelope_path", "plan_path"),
    "implementation.started": ("task_envelope_path", "plan_path", "handoff_path"),
    "file.write.requested": (
        "task_envelope_path",
        "handoff_path",
        "requested_paths",
    ),
    "command.requested": (
        "task_envelope_path",
        "plan_path",
        "handoff_path",
        "command_id",
        "argv",
    ),
    "review.completed": ("review_verdict_path",),
    "verification.completed": ("task_envelope_path", "plan_path", "verdict_path"),
    "task.completed": ("task_envelope_path", "run_record_path"),
}

REVIEW_ROLES = {
    "spec_compliance": "core.spec-reviewer",
    "code_quality": "core.code-reviewer",
    "security": "core.security-reviewer",
    "contract": "cross-platform.contract-reviewer",
}

REVIEWER_AGENT_IDS = set(REVIEW_ROLES.values())
WRITE_EVENT_NAMES = {"implementation.started", "file.write.requested"}
NONTERMINAL_FINDING_STATUSES = {"open", "accepted", "fixed", "deferred"}
SAFE_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
SYMBOLIC_SCOPE = re.compile(r"^<approved-[a-z0-9-]+-paths>$")
SAFE_EXECUTABLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]*$")
WINDOWS_SCRIPT_SUFFIXES = (".cmd", ".bat", ".com", ".ps1")
EXECUTABLE_KINDS = {"direct_tool", "interpreter", "shell", "dispatcher"}
REQUIRED_CONSUMER_INCLUDES = {
    "AGENTS.md",
    "LICENSE",
    "agents",
    "skills",
    "schemas",
    "hooks",
    "specs",
    "docs",
    "platforms",
    "registries",
    "consumer",
    "collaboration/examples/trusted-pr-control.yaml",
    "scripts",
}
TRUSTED_CONTROL_BLOCKERS = {
    "untrusted_base",
    "fork_external_processing",
    "head_changed",
    "diff_digest_changed",
    "missing_required_check",
    "duplicate_required_check",
    "stale_check_attempt",
    "failed_required_check",
    "trust_anchor_changed_without_meta_review",
    "review_not_read_only",
    "merge_authority_not_separated",
}
MANDATORY_TRUST_ANCHORS = {
    ".github/workflows/**",
    "AGENTS.md",
    "agents/**",
    "hooks/**",
    "policies/**",
    "registries/**",
    "schemas/**",
    "skills/**",
    "scripts/validate.py",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected a JSON object")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected a YAML object")
    return value


def load_artifact(path: Path) -> dict[str, Any]:
    return load_json(path) if path.suffix == ".json" else load_yaml(path)


def schema_errors(instance: Any, schema_name: str, label: str) -> list[str]:
    schema = load_json(ROOT / "schemas" / schema_name)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "<root>"
        errors.append(f"{label}:{location}: {error.message}")
    return errors


def resolve_artifact(
    reference: str | Path | Any,
    artifact_root: Path,
    label: str,
) -> tuple[Path | None, list[str]]:
    if not isinstance(reference, (str, Path)) or not str(reference):
        return None, [f"{label}: artifact reference must be a non-empty path"]
    root = artifact_root.resolve()
    candidate = Path(reference)
    candidate = candidate if candidate.is_absolute() else root / candidate
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        return None, [f"{label}: artifact path escapes workspace: {reference}"]
    if not resolved.is_file():
        return None, [f"{label}: artifact does not exist: {reference}"]
    return resolved, []


def load_resolved_artifact(
    path: Path,
    label: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        return load_artifact(path), []
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return None, [f"{label}: invalid artifact: {exc}"]


def validate_task_semantics(task: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    acceptance_ids = [item.get("id") for item in task.get("acceptance_criteria", [])]
    if len(acceptance_ids) != len(set(acceptance_ids)):
        errors.append(f"{label}: acceptance criterion ids must be unique")
    if task.get("status") == "completed":
        unknown = sorted(
            name
            for name, impact in task.get("platform_impact", {}).items()
            if impact == "unknown"
        )
        if unknown:
            errors.append(
                f"{label}: completed task has unknown platform impact: {unknown}"
            )
    return errors


def validate_read_only_policy(agent: dict[str, Any], label: str) -> list[str]:
    if agent.get("mode") != "read_only":
        return []

    errors = []
    if agent.get("path_policy", {}).get("write", []):
        errors.append(f"{label}: read-only agent declares write paths")
    return errors


def validate_runtime_policy(
    policy: dict[str, Any],
    label: str = "registries/runtime-policy.yaml",
) -> list[str]:
    errors = schema_errors(policy, "runtime-policy.schema.json", label)
    modes = policy.get("mode_allowlists", {})
    missing = sorted(REQUIRED_MODES - modes.keys())
    if missing:
        errors.append(f"{label}: missing mode allowlists: {missing}")
    known_capabilities = policy.get("capabilities", [])
    known_tools = policy.get("tools", [])
    if len(known_capabilities) != len(set(known_capabilities)):
        errors.append(f"{label}: capability ids must be unique")
    if len(known_tools) != len(set(known_tools)):
        errors.append(f"{label}: tool ids must be unique")
    for mode, allowlist in modes.items():
        unknown_capabilities = sorted(
            set(allowlist.get("capabilities", [])) - set(known_capabilities)
        )
        unknown_tools = sorted(set(allowlist.get("tools", [])) - set(known_tools))
        if unknown_capabilities:
            errors.append(
                f"{label}: mode {mode} allows unknown capabilities: "
                f"{unknown_capabilities}"
            )
        if unknown_tools:
            errors.append(f"{label}: mode {mode} allows unknown tools: {unknown_tools}")
    return errors


def validate_agent_authorization(
    agent: dict[str, Any],
    policy: dict[str, Any],
    label: str,
) -> list[str]:
    errors = validate_read_only_policy(agent, label)
    mode = agent.get("mode")
    allowlist = policy.get("mode_allowlists", {}).get(mode)
    if allowlist is None:
        return [*errors, f"{label}: unknown or unregistered mode '{mode}'"]

    known_capabilities = set(policy.get("capabilities", []))
    known_tools = set(policy.get("tools", []))
    capabilities = set(agent.get("capabilities", []))
    allowed_tools = set(agent.get("tools", {}).get("allow", []))
    denied_tools = set(agent.get("tools", {}).get("deny", []))

    unknown_capabilities = sorted(capabilities - known_capabilities)
    unknown_tools = sorted((allowed_tools | denied_tools) - known_tools)
    if unknown_capabilities:
        errors.append(
            f"{label}: unknown capabilities fail closed: {unknown_capabilities}"
        )
    if unknown_tools:
        errors.append(f"{label}: unknown tools fail closed: {unknown_tools}")

    disallowed_capabilities = sorted(
        capabilities - set(allowlist.get("capabilities", []))
    )
    disallowed_tools = sorted(allowed_tools - set(allowlist.get("tools", [])))
    if disallowed_capabilities:
        errors.append(
            f"{label}: mode {mode} does not allow capabilities: "
            f"{disallowed_capabilities}"
        )
    if disallowed_tools:
        errors.append(
            f"{label}: mode {mode} does not allow tools: {disallowed_tools}"
        )
    return errors


def validate_agent_manifests() -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    agents: dict[str, dict[str, Any]] = {}
    policy_path = ROOT / "registries" / "runtime-policy.yaml"
    try:
        policy = load_yaml(policy_path)
    except (OSError, TypeError, yaml.YAMLError) as exc:
        return [f"registries/runtime-policy.yaml: {exc}"], agents
    errors.extend(validate_runtime_policy(policy))

    for path in sorted((ROOT / "agents").rglob("*.agent.yaml")):
        relative = path.relative_to(ROOT).as_posix()
        try:
            agent = load_yaml(path)
        except (OSError, TypeError, yaml.YAMLError) as exc:
            errors.append(f"{relative}: {exc}")
            continue

        errors.extend(schema_errors(agent, "agent-manifest.schema.json", relative))
        agent_id = agent.get("id")
        if isinstance(agent_id, str):
            if agent_id in agents:
                errors.append(f"{relative}: duplicate agent id '{agent_id}'")
            agents[agent_id] = agent

        allowed = set(agent.get("tools", {}).get("allow", []))
        denied = set(agent.get("tools", {}).get("deny", []))
        overlap = sorted(allowed & denied)
        if overlap:
            errors.append(f"{relative}: tools appear in allow and deny: {overlap}")

        write_paths = agent.get("path_policy", {}).get("write", [])
        if "**" in write_paths:
            errors.append(f"{relative}: unrestricted write path '**' is forbidden")
        errors.extend(
            validate_scope_paths(
                agent.get("path_policy", {}).get("read", []),
                f"{relative}:path_policy.read",
                allow_glob=True,
                allow_symbolic=False,
            )
        )
        errors.extend(
            validate_scope_paths(
                write_paths,
                f"{relative}:path_policy.write",
                allow_glob=True,
                allow_symbolic=True,
            )
        )

        if VENDOR_TERMS.search(path.read_text(encoding="utf-8")):
            errors.append(f"{relative}: canonical agent manifest contains a vendor term")

        errors.extend(validate_agent_authorization(agent, policy, relative))

    missing = sorted(REQUIRED_CORE_AGENTS - agents.keys())
    if missing:
        errors.append(f"agents: missing required core agents: {missing}")

    known_agents = set(agents) | {"human.owner"}
    for agent_id, agent in agents.items():
        handoffs = agent.get("handoffs", {})
        references = set(handoffs.get("accepts_from", [])) | set(
            handoffs.get("sends_to", [])
        )
        unknown = sorted(references - known_agents)
        if unknown:
            errors.append(f"agent {agent_id}: unknown handoff targets: {unknown}")

    return errors, agents


def parse_posix_scope(
    value: Any,
    *,
    allow_glob: bool,
    allow_symbolic: bool,
) -> tuple[tuple[str, ...] | None, str | None]:
    if not isinstance(value, str) or not value:
        return None, "path must be a non-empty string"
    if "\x00" in value:
        return None, "NUL is forbidden"
    if "\\" in value:
        return None, "backslashes and mixed separators are forbidden"
    pure = PurePosixPath(value)
    if pure.is_absolute() or value.startswith("/"):
        return None, "absolute paths are forbidden"
    raw_segments = value.split("/")
    if any(segment == "" for segment in raw_segments):
        return None, "empty path segments are forbidden"
    if any(segment in {".", ".."} for segment in raw_segments):
        return None, "dot and traversal segments are forbidden"
    if allow_symbolic and len(raw_segments) == 1 and SYMBOLIC_SCOPE.fullmatch(value):
        return (value,), None

    for index, segment in enumerate(raw_segments):
        if segment == "**":
            if not allow_glob or index != len(raw_segments) - 1:
                return None, "recursive glob is allowed only as the final segment"
            continue
        if any(character in segment for character in "*?[]{}"):
            return None, "unprovable glob syntax is forbidden"
        if not SAFE_PATH_SEGMENT.fullmatch(segment):
            return None, f"unsafe path segment '{segment}'"
    return tuple(raw_segments), None


def path_scope_is_subset(requested: str, permitted: str) -> bool:
    requested_parts, requested_error = parse_posix_scope(
        requested, allow_glob=True, allow_symbolic=True
    )
    permitted_parts, permitted_error = parse_posix_scope(
        permitted, allow_glob=True, allow_symbolic=True
    )
    if requested_error or permitted_error or requested_parts is None or permitted_parts is None:
        return False
    if requested_parts == permitted_parts:
        return True
    if permitted_parts == ("**",):
        return True
    if permitted_parts[-1:] == ("**",):
        prefix = permitted_parts[:-1]
        return len(requested_parts) >= len(prefix) and requested_parts[: len(prefix)] == prefix
    return False


def validate_scope_paths(
    paths: list[Any],
    label: str,
    *,
    allow_glob: bool,
    allow_symbolic: bool,
) -> list[str]:
    errors: list[str] = []
    for value in paths:
        _, error = parse_posix_scope(
            value, allow_glob=allow_glob, allow_symbolic=allow_symbolic
        )
        if error:
            errors.append(f"{label}: unsafe path '{value}': {error}")
    return errors


def validate_handoff_semantics(
    handoff: dict[str, Any],
    agents: dict[str, dict[str, Any]],
    label: str,
) -> list[str]:
    errors: list[str] = []
    recipient_id = handoff.get("to")
    if recipient_id == "human.owner":
        return errors
    recipient = agents.get(recipient_id)
    if recipient is None:
        return [f"{label}: unknown recipient agent '{recipient_id}'"]

    sender_id = handoff.get("from")
    sender = agents.get(sender_id)
    if sender_id != "human.owner" and sender is None:
        errors.append(f"{label}: unknown sender agent '{sender_id}'")
    elif sender is not None and recipient_id not in sender.get("handoffs", {}).get(
        "sends_to", []
    ):
        errors.append(f"{label}: sender {sender_id} cannot hand off to {recipient_id}")
    if sender_id not in recipient.get("handoffs", {}).get("accepts_from", []):
        errors.append(f"{label}: recipient {recipient_id} does not accept {sender_id}")

    declared_reads = recipient.get("path_policy", {}).get("read", [])
    authorized_reads = handoff.get("authorized_scope", {}).get("read", [])
    errors.extend(
        validate_scope_paths(
            authorized_reads,
            f"{label}:authorized_scope.read",
            allow_glob=True,
            allow_symbolic=False,
        )
    )
    for requested in authorized_reads:
        if not any(
            path_scope_is_subset(str(requested), str(permitted))
            for permitted in declared_reads
        ):
            errors.append(
                f"{label}: authorized read scope '{requested}' exceeds "
                f"recipient {recipient_id} manifest"
            )

    declared_writes = recipient.get("path_policy", {}).get("write", [])
    authorized_writes = handoff.get("authorized_scope", {}).get("write", [])
    errors.extend(
        validate_scope_paths(
            authorized_writes,
            f"{label}:authorized_scope.write",
            allow_glob=True,
            allow_symbolic=True,
        )
    )
    for requested in authorized_writes:
        if not any(
            path_scope_is_subset(str(requested), str(permitted))
            for permitted in declared_writes
        ):
            errors.append(
                f"{label}: authorized write scope '{requested}' exceeds "
                f"recipient {recipient_id} manifest"
            )
    if recipient.get("mode") == "read_only" and authorized_writes:
        errors.append(f"{label}: read-only recipient cannot receive write scope")
    return errors


def validate_platform_profiles(
    agents: dict[str, dict[str, Any]],
) -> tuple[list[str], int]:
    errors: list[str] = []
    count = 0
    for path in sorted((ROOT / "platforms").glob("*.yaml")):
        relative = path.relative_to(ROOT).as_posix()
        profile = load_yaml(path)
        errors.extend(schema_errors(profile, "platform-profile.schema.json", relative))
        unknown = sorted(set(profile.get("agents", [])) - agents.keys())
        if unknown:
            errors.append(f"{relative}: unknown agents: {unknown}")
        count += 1
    return errors, count


def parse_skill_frontmatter(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", content, re.DOTALL)
    if not match:
        raise ValueError("missing YAML frontmatter")
    value = yaml.safe_load(match.group(1))
    if not isinstance(value, dict):
        raise TypeError("frontmatter must be an object")
    return value


def validate_skills() -> tuple[list[str], int]:
    errors: list[str] = []
    count = 0
    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        relative = path.relative_to(ROOT).as_posix()
        count += 1
        try:
            metadata = parse_skill_frontmatter(path)
        except (TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"{relative}: {exc}")
            continue

        expected_name = path.parent.name
        if metadata.get("name") != expected_name:
            errors.append(f"{relative}: skill name must equal directory '{expected_name}'")
        description = metadata.get("description")
        if not isinstance(description, str) or len(description) < 20:
            errors.append(f"{relative}: description must contain at least 20 characters")
        if VENDOR_TERMS.search(path.read_text(encoding="utf-8")):
            errors.append(f"{relative}: canonical skill contains a vendor term")
    return errors, count


def load_event_policy() -> tuple[dict[str, Any], list[str]]:
    path = ROOT / "registries" / "event-policy.yaml"
    try:
        policy = load_yaml(path)
    except (OSError, TypeError, yaml.YAMLError) as exc:
        return {}, [f"registries/event-policy.yaml: {exc}"]
    return policy, schema_errors(
        policy, "event-policy.schema.json", "registries/event-policy.yaml"
    )


def validate_event_policy_semantics(
    policy: dict[str, Any],
    agents: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    allowed_events = set(
        load_json(ROOT / "schemas/hook-event.schema.json")["properties"]["event"][
            "enum"
        ]
    )
    missing_events = sorted(allowed_events - policy.get("events", {}).keys())
    if missing_events:
        errors.append(
            "registries/event-policy.yaml: missing canonical event policies: "
            f"{missing_events}"
        )
    for event, rule in policy.get("events", {}).items():
        if event not in allowed_events:
            errors.append(f"registries/event-policy.yaml: unknown event '{event}'")
        unknown_modes = sorted(set(rule.get("allowed_modes", [])) - REQUIRED_MODES)
        if unknown_modes:
            errors.append(
                f"registries/event-policy.yaml: event {event} has unknown modes "
                f"{unknown_modes}"
            )
        for agent_id in rule.get("allowed_agents", []):
            agent = agents.get(agent_id)
            if agent is None:
                errors.append(
                    f"registries/event-policy.yaml: event {event} has unknown agent "
                    f"{agent_id}"
                )
            elif agent.get("mode") not in rule.get("allowed_modes", []):
                errors.append(
                    f"registries/event-policy.yaml: event {event} agent {agent_id} "
                    "mode is not allowed"
                )
    allowed_entries = policy.get("allowed_executables")
    canonical_allowed: list[str] = []
    direct_tools: set[str] = set()
    if not isinstance(allowed_entries, list) or not allowed_entries:
        errors.append(
            "registries/event-policy.yaml: allowed_executables must be a "
            "non-empty array"
        )
    else:
        for entry in allowed_entries:
            if not isinstance(entry, dict):
                errors.append(
                    "registries/event-policy.yaml: allowed executable must be "
                    "an object with name and kind"
                )
                continue
            name = entry.get("name")
            kind = entry.get("kind")
            canonical_name = (
                name.casefold().removesuffix(".exe")
                if isinstance(name, str)
                else None
            )
            canonical_is_safe = (
                canonical_name is not None
                and SAFE_EXECUTABLE.fullmatch(canonical_name) is not None
            )
            if (
                not canonical_is_safe
                or name != canonical_name
                or name.endswith(WINDOWS_SCRIPT_SUFFIXES)
            ):
                errors.append(
                    "registries/event-policy.yaml: allowed_executables contains "
                    f"unsafe or non-canonical executable '{name}'"
                )
            if canonical_is_safe:
                canonical_allowed.append(canonical_name)
            if kind not in EXECUTABLE_KINDS:
                errors.append(
                    "registries/event-policy.yaml: allowed executable "
                    f"'{name}' has invalid kind '{kind}'"
                )
            elif kind == "direct_tool" and canonical_is_safe:
                direct_tools.add(canonical_name)
        if len(canonical_allowed) != len(set(canonical_allowed)):
            errors.append(
                "registries/event-policy.yaml: allowed_executables must contain "
                "unique canonical names"
            )

    denied_values = policy.get("denied_executables")
    canonical_denied: list[str] = []
    if not isinstance(denied_values, list) or not denied_values:
        errors.append(
            "registries/event-policy.yaml: denied_executables must be a "
            "non-empty array"
        )
    else:
        for value in denied_values:
            canonical_value = (
                value.casefold().removesuffix(".exe")
                if isinstance(value, str)
                else None
            )
            canonical_is_safe = (
                canonical_value is not None
                and SAFE_EXECUTABLE.fullmatch(canonical_value) is not None
            )
            if (
                not canonical_is_safe
                or value != canonical_value
                or value.endswith(WINDOWS_SCRIPT_SUFFIXES)
            ):
                errors.append(
                    "registries/event-policy.yaml: denied_executables contains "
                    f"unsafe or non-canonical executable '{value}'"
                )
            if canonical_is_safe:
                canonical_denied.append(canonical_value)
        if len(canonical_denied) != len(set(canonical_denied)):
            errors.append(
                "registries/event-policy.yaml: denied_executables must contain "
                "unique canonical names"
            )

    overlap = sorted(direct_tools & set(canonical_denied))
    if overlap:
        errors.append(
            "registries/event-policy.yaml: direct tools cannot also be denied: "
            f"{overlap}"
        )
    return errors


def validate_argv(
    argv: Any,
    event_policy: dict[str, Any],
    label: str,
) -> list[str]:
    if not isinstance(argv, list) or not argv:
        return [f"{label}: command argv must be a non-empty array"]
    if any(
        not isinstance(argument, str) or not argument or "\x00" in argument
        for argument in argv
    ):
        return [f"{label}: command argv contains an invalid argument"]
    executable = argv[0]
    folded_executable = executable.casefold()
    if folded_executable.endswith(WINDOWS_SCRIPT_SUFFIXES):
        return [
            f"{label}: Windows script executable '{executable}' is forbidden"
        ]
    canonical_executable = folded_executable.removesuffix(".exe")
    if not SAFE_EXECUTABLE.fullmatch(canonical_executable) or "/" in executable:
        return [f"{label}: executable must be an approved bare identifier"]
    denied = {
        str(value).casefold().removesuffix(".exe")
        for value in event_policy.get("denied_executables", [])
    }
    if canonical_executable in denied:
        return [
            f"{label}: dangerous executable '{canonical_executable}' is forbidden"
        ]
    matching_kinds = [
        entry.get("kind")
        for entry in event_policy.get("allowed_executables", [])
        if isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and SAFE_EXECUTABLE.fullmatch(entry["name"])
        and entry.get("name") == entry["name"].casefold()
        and not entry["name"].endswith(".exe")
        and not entry["name"].endswith(WINDOWS_SCRIPT_SUFFIXES)
        and entry.get("kind") in EXECUTABLE_KINDS
        and entry["name"] == canonical_executable
    ]
    if not matching_kinds:
        return [
            f"{label}: executable '{canonical_executable}' is not allowed by policy"
        ]
    if len(matching_kinds) != 1:
        return [
            (
                f"{label}: executable '{canonical_executable}' does not have one "
                "unambiguous policy classification"
            )
        ]
    executable_kind = matching_kinds[0]
    if executable_kind != "direct_tool":
        return [
            (
                f"{label}: executable '{canonical_executable}' is classified as "
                f"{executable_kind} and is not eligible for automatic execution"
            )
        ]
    return []


def validate_plan_semantics(
    plan: dict[str, Any],
    task: dict[str, Any],
    agents: dict[str, dict[str, Any]],
    event_policy: dict[str, Any],
    label: str,
    require_approved: bool = False,
) -> list[str]:
    errors: list[str] = []
    if plan.get("task_id") != task.get("task_id"):
        errors.append(f"{label}: plan task_id does not match task envelope")
    mappings = plan.get("acceptance_mapping", [])
    mapped_ids = [mapping.get("acceptance_id") for mapping in mappings]
    required_ids = {
        criterion.get("id") for criterion in task.get("acceptance_criteria", [])
    }
    if len(mapped_ids) != len(set(mapped_ids)):
        errors.append(f"{label}: acceptance mapping ids must be unique")
    if set(mapped_ids) != required_ids:
        errors.append(
            f"{label}: plan acceptance mapping must exactly cover task criteria"
        )
    owner = agents.get(plan.get("owner"))
    if owner is None or owner.get("mode") != "plan_write":
        errors.append(f"{label}: plan owner must be a registered plan_write agent")

    commands = plan.get("required_commands", [])
    command_ids = [command.get("id") for command in commands if isinstance(command, dict)]
    if not commands:
        errors.append(f"{label}: plan requires at least one trusted command")
    if len(command_ids) != len(set(command_ids)):
        errors.append(f"{label}: required command ids must be unique")
    for command in commands:
        if isinstance(command, dict):
            errors.extend(
                validate_argv(
                    command.get("argv"),
                    event_policy,
                    f"{label}:required_commands.{command.get('id')}",
                )
            )
    if require_approved or plan.get("status") == "approved":
        if plan.get("status") != "approved":
            errors.append(f"{label}: implementation requires an approved plan")
        approval = plan.get("approval")
        if not isinstance(approval, dict):
            errors.append(f"{label}: approved plan requires approval evidence")
        else:
            approver_id = approval.get("reviewer")
            approver = agents.get(approver_id)
            if approver_id == plan.get("owner"):
                errors.append(f"{label}: plan owner cannot approve their own plan")
            if (
                approver_id != "core.spec-reviewer"
                or approver is None
                or approver.get("mode") != "read_only"
                or "review_specification" not in approver.get("capabilities", [])
            ):
                errors.append(
                    f"{label}: plan approver must be registered core.spec-reviewer"
                )
    return errors


def validate_verdict_semantics(
    verdict: dict[str, Any],
    task: dict[str, Any],
    plan: dict[str, Any] | None,
    agents: dict[str, dict[str, Any]],
    event_policy: dict[str, Any],
    artifact_root: Path,
    label: str,
) -> list[str]:
    errors: list[str] = []
    verifier_id = verdict.get("verifier")
    verifier = agents.get(verifier_id)
    if (
        verifier_id != "core.verifier"
        or verifier is None
        or verifier.get("mode") != "verify_execute"
    ):
        errors.append(f"{label}: verifier must be registered core.verifier")
    if verdict.get("task_id") != task.get("task_id"):
        errors.append(f"{label}: verdict task_id does not match task envelope")

    criteria = {
        item.get("id"): item for item in task.get("acceptance_criteria", [])
    }
    results = verdict.get("acceptance_results", [])
    result_ids = [result.get("acceptance_id") for result in results]
    if len(result_ids) != len(set(result_ids)):
        errors.append(f"{label}: acceptance results must not contain duplicate ids")
    if set(result_ids) != set(criteria):
        errors.append(
            f"{label}: acceptance results must exactly cover task acceptance criteria"
        )

    if verdict.get("verdict") != "PASS":
        return errors

    if plan is None:
        errors.append(f"{label}: PASS requires a trusted approved plan")
        trusted_commands: dict[str, list[str]] = {}
    else:
        if plan.get("status") != "approved" or plan.get("task_id") != task.get("task_id"):
            errors.append(f"{label}: PASS requires the matching approved plan")
        trusted_commands = {
            command.get("id"): command.get("argv")
            for command in plan.get("required_commands", [])
            if isinstance(command, dict)
        }

    completed_at_raw = verdict.get("completed_at")
    try:
        completed_at = datetime.fromisoformat(completed_at_raw)
    except (TypeError, ValueError):
        completed_at = None
    try:
        started_at = datetime.fromisoformat(verdict.get("started_at"))
    except (TypeError, ValueError):
        started_at = None

    for result in results:
        acceptance_id = result.get("acceptance_id")
        status = result.get("status")
        applicable = result.get("applicable")
        if applicable is True and status != "pass":
            errors.append(
                f"{label}: PASS requires applicable {acceptance_id} to pass"
            )
        if applicable is not True:
            errors.append(
                f"{label}: PASS cannot mark task criterion {acceptance_id} "
                "as non-applicable"
            )
        if status == "pass":
            evidence = result.get("evidence", [])
            if not evidence:
                errors.append(f"{label}: PASS {acceptance_id} lacks fresh evidence")
            for item in evidence:
                if item.get("fresh") is not True:
                    errors.append(
                        f"{label}: PASS {acceptance_id} contains non-fresh evidence"
                    )
                observed_at_raw = item.get("observed_at")
                try:
                    observed_at = datetime.fromisoformat(observed_at_raw)
                except (TypeError, ValueError):
                    observed_at = None
                if completed_at is not None and observed_at is not None:
                    try:
                        occurs_after = observed_at > completed_at
                    except TypeError:
                        occurs_after = True
                    if occurs_after:
                        errors.append(
                            f"{label}: evidence for {acceptance_id} occurs after verdict"
                        )
                if started_at is not None and observed_at is not None:
                    try:
                        predates_verification = observed_at < started_at
                    except TypeError:
                        predates_verification = True
                    if predates_verification:
                        errors.append(
                            f"{label}: evidence for {acceptance_id} predates "
                            "verification and is stale"
                        )
                _, path_errors = resolve_artifact(
                    item.get("reference", ""),
                    artifact_root,
                    f"{label}:{acceptance_id}",
                )
                errors.extend(path_errors)

    commands = verdict.get("commands", [])
    if not commands:
        errors.append(f"{label}: PASS requires at least one required command")
    observed_command_ids = [
        command.get("command_id") for command in commands if isinstance(command, dict)
    ]
    if len(observed_command_ids) != len(set(observed_command_ids)):
        errors.append(f"{label}: PASS command ids must be unique")
    if set(observed_command_ids) != set(trusted_commands):
        errors.append(
            f"{label}: PASS commands must exactly match approved plan commands"
        )

    for command in commands:
        command_id = command.get("command_id")
        argv = command.get("argv")
        errors.extend(validate_argv(argv, event_policy, f"{label}:{command_id}"))
        if trusted_commands.get(command_id) != argv:
            errors.append(
                f"{label}: command {command_id} argv differs from approved plan"
            )
        if command.get("required") is not True:
            errors.append(
                f"{label}: approved plan command {command_id} must be required"
            )
        if command.get("required") and command.get("exit_code") != 0:
            errors.append(
                f"{label}: PASS required command failed: {command_id}"
            )
        if command.get("required"):
            if command.get("fresh") is not True:
                errors.append(
                    f"{label}: PASS required command is not fresh: "
                    f"{command_id}"
                )
            try:
                command_observed_at = datetime.fromisoformat(
                    command.get("observed_at")
                )
            except (TypeError, ValueError):
                command_observed_at = None
            if started_at is not None and command_observed_at is not None:
                try:
                    command_is_stale = command_observed_at < started_at
                except TypeError:
                    command_is_stale = True
                if command_is_stale:
                    errors.append(
                        f"{label}: PASS required command predates verification: "
                        f"{command_id}"
                    )
            output_reference = command.get("output_reference")
            if not output_reference:
                errors.append(
                    f"{label}: PASS required command lacks output evidence: "
                    f"{command_id}"
                )
            else:
                _, path_errors = resolve_artifact(
                    output_reference,
                    artifact_root,
                    f"{label}:command",
                )
                errors.extend(path_errors)
    return errors


def validate_finding_semantics(
    finding: dict[str, Any],
    agents: dict[str, dict[str, Any]],
    artifact_root: Path,
    label: str,
    *,
    for_pass: bool,
) -> list[str]:
    errors: list[str] = []
    reviewer_id = finding.get("reviewer")
    reviewer = agents.get(reviewer_id)
    if (
        reviewer_id not in REVIEWER_AGENT_IDS
        or reviewer is None
        or reviewer.get("mode") != "read_only"
    ):
        errors.append(f"{label}: finding reviewer must be a registered review role")

    severity = finding.get("severity")
    status = finding.get("status")
    disposition = finding.get("disposition")
    resolution_evidence = finding.get("resolution_evidence", [])
    resolution_reviewer_id = finding.get("resolution_reviewer")

    if (
        severity in {"critical", "high", "medium"}
        and status in NONTERMINAL_FINDING_STATUSES
        and not disposition
    ):
        errors.append(
            f"{label}: medium-or-higher non-terminal finding requires disposition"
        )

    if status in {"fixed", "verified"}:
        if not isinstance(disposition, str) or len(disposition) < 15:
            errors.append(f"{label}: {status} finding requires concrete disposition")
        if not resolution_evidence:
            errors.append(
                f"{label}: {status} finding requires machine-verifiable "
                "resolution evidence"
            )
        for reference in resolution_evidence:
            _, path_errors = resolve_artifact(reference, artifact_root, label)
            errors.extend(path_errors)
    if status == "verified":
        resolution_reviewer = agents.get(resolution_reviewer_id)
        if (
            resolution_reviewer_id == reviewer_id
            or resolution_reviewer_id != "core.verifier"
            or resolution_reviewer is None
            or resolution_reviewer.get("mode") != "verify_execute"
        ):
            errors.append(
                f"{label}: verified finding requires independent core.verifier"
            )

    if status == "rejected":
        resolution_reviewer = agents.get(resolution_reviewer_id)
        if not isinstance(disposition, str) or len(disposition) < 15:
            errors.append(f"{label}: rejected finding requires concrete disposition")
        if (
            resolution_reviewer_id == reviewer_id
            or resolution_reviewer_id not in REVIEWER_AGENT_IDS
            or resolution_reviewer is None
            or resolution_reviewer.get("mode") != "read_only"
        ):
            errors.append(
                f"{label}: rejected finding requires an independent registered reviewer"
            )

    if (
        for_pass
        and severity in {"critical", "high"}
        and status not in {"verified", "rejected"}
    ):
        errors.append(
            f"{label}: PASS is blocked by {severity} finding in {status} status"
        )
    return errors


def validate_review_verdict_semantics(
    verdict: dict[str, Any],
    task_id: str,
    agents: dict[str, dict[str, Any]],
    artifact_root: Path,
    label: str,
) -> list[str]:
    errors: list[str] = []
    review_type = verdict.get("review_type")
    reviewer_id = verdict.get("reviewer")
    reviewer = agents.get(reviewer_id)
    expected_reviewer = REVIEW_ROLES.get(review_type)
    if (
        reviewer_id != expected_reviewer
        or reviewer is None
        or reviewer.get("mode") != "read_only"
    ):
        errors.append(
            f"{label}: review_type {review_type} requires reviewer {expected_reviewer}"
        )
    if verdict.get("task_id") != task_id:
        errors.append(f"{label}: review verdict task_id does not match run")
    outcome = verdict.get("verdict")
    if outcome in {"PASS", "PARTIAL", "BLOCKED"} and not verdict.get("evidence"):
        errors.append(f"{label}: {outcome} review verdict requires evidence")
    for reference in verdict.get("evidence", []):
        _, path_errors = resolve_artifact(reference, artifact_root, label)
        errors.extend(path_errors)

    valid_findings = 0
    for finding_reference in verdict.get("finding_paths", []):
        finding_path, path_errors = resolve_artifact(
            finding_reference, artifact_root, label
        )
        errors.extend(path_errors)
        if finding_path is None:
            continue
        finding, finding_load_errors = load_resolved_artifact(finding_path, label)
        errors.extend(finding_load_errors)
        if finding is None:
            continue
        finding_label = finding_path.relative_to(artifact_root.resolve()).as_posix()
        finding_schema_errors = schema_errors(
            finding, "finding.schema.json", finding_label
        )
        errors.extend(finding_schema_errors)
        errors.extend(
            validate_finding_semantics(
                finding,
                agents,
                artifact_root,
                finding_label,
                for_pass=outcome == "PASS",
            )
        )
        identity_valid = True
        if finding.get("task_id") != task_id:
            errors.append(f"{label}: finding task_id does not match review verdict")
            identity_valid = False
        if finding.get("reviewer") != reviewer_id:
            errors.append(f"{label}: finding reviewer does not match review verdict")
            identity_valid = False
        if not finding_schema_errors and identity_valid:
            valid_findings += 1
    if outcome == "FAIL" and valid_findings == 0:
        errors.append(f"{label}: FAIL review verdict requires a valid finding")
    return errors


def required_review_types(task: dict[str, Any]) -> set[str]:
    required = {"spec_compliance", "code_quality"}
    if task.get("risk", {}).get("level") in {"high", "critical"}:
        required.add("security")
    if task.get("platform_impact", {}).get("shared_contracts") == "changed":
        required.add("contract")
    return required


def validate_run_record_semantics(
    record: dict[str, Any],
    agents: dict[str, dict[str, Any]],
    event_policy: dict[str, Any],
    artifact_root: Path,
    label: str,
) -> list[str]:
    if record.get("status") != "completed":
        return []

    errors: list[str] = []
    if not record.get("completed_at"):
        errors.append(f"{label}: completed run requires completed_at")

    task_path, path_errors = resolve_artifact(
        record.get("task_envelope", ""), artifact_root, label
    )
    errors.extend(path_errors)
    if task_path is None:
        return errors
    task, task_load_errors = load_resolved_artifact(task_path, label)
    errors.extend(task_load_errors)
    if task is None:
        return errors
    task_label = task_path.relative_to(artifact_root.resolve()).as_posix()
    errors.extend(schema_errors(task, "task-envelope.schema.json", task_label))
    errors.extend(validate_task_semantics(task, task_label))
    if task.get("task_id") != record.get("task_id"):
        errors.append(f"{label}: run task_id does not match task envelope")
    if task.get("status") != "completed":
        errors.append(f"{label}: completed run requires completed task envelope")

    plan_path, plan_path_errors = resolve_artifact(
        record.get("approved_plan", ""), artifact_root, label
    )
    errors.extend(plan_path_errors)
    plan: dict[str, Any] | None = None
    if plan_path is not None:
        plan, plan_load_errors = load_resolved_artifact(plan_path, label)
        errors.extend(plan_load_errors)
        if plan is not None:
            plan_label = plan_path.relative_to(artifact_root.resolve()).as_posix()
            plan_schema_errors = schema_errors(plan, "plan.schema.json", plan_label)
            errors.extend(plan_schema_errors)
            if not plan_schema_errors:
                errors.extend(
                    validate_plan_semantics(
                        plan,
                        task,
                        agents,
                        event_policy,
                        plan_label,
                        require_approved=True,
                    )
                )

    seen_review_types: set[str] = set()
    for reference in record.get("review_verdicts", []):
        review_path, review_path_errors = resolve_artifact(reference, artifact_root, label)
        errors.extend(review_path_errors)
        if review_path is None:
            continue
        review, review_load_errors = load_resolved_artifact(review_path, label)
        errors.extend(review_load_errors)
        if review is None:
            continue
        review_label = review_path.relative_to(artifact_root.resolve()).as_posix()
        errors.extend(
            schema_errors(review, "review-verdict.schema.json", review_label)
        )
        errors.extend(
            validate_review_verdict_semantics(
                review,
                record.get("task_id", ""),
                agents,
                artifact_root,
                review_label,
            )
        )
        if review.get("verdict") == "PASS":
            seen_review_types.add(review.get("review_type"))

    missing_reviews = sorted(required_review_types(task) - seen_review_types)
    if missing_reviews:
        errors.append(f"{label}: completed run lacks PASS reviews: {missing_reviews}")

    for reference in record.get("artifacts", []):
        artifact_path, artifact_path_errors = resolve_artifact(
            reference, artifact_root, label
        )
        errors.extend(artifact_path_errors)
        if artifact_path is None or artifact_path.suffix not in {".yaml", ".yml", ".json"}:
            continue
        finding, finding_load_errors = load_resolved_artifact(artifact_path, label)
        errors.extend(finding_load_errors)
        if finding is None or "finding_id" not in finding:
            continue
        finding_label = artifact_path.relative_to(artifact_root.resolve()).as_posix()
        finding_schema_errors = schema_errors(
            finding, "finding.schema.json", finding_label
        )
        errors.extend(finding_schema_errors)
        if not finding_schema_errors:
            errors.extend(
                validate_finding_semantics(
                    finding,
                    agents,
                    artifact_root,
                    finding_label,
                    for_pass=True,
                )
            )

    verification_path, verification_path_errors = resolve_artifact(
        record.get("verification_verdict", ""), artifact_root, label
    )
    errors.extend(verification_path_errors)
    if verification_path is not None:
        verification, verification_load_errors = load_resolved_artifact(
            verification_path, label
        )
        errors.extend(verification_load_errors)
        if verification is None:
            return errors
        verification_label = verification_path.relative_to(
            artifact_root.resolve()
        ).as_posix()
        errors.extend(
            schema_errors(verification, "verdict.schema.json", verification_label)
        )
        errors.extend(
            validate_verdict_semantics(
                verification,
                task,
                plan,
                agents,
                event_policy,
                artifact_root,
                verification_label,
            )
        )
        if verification.get("verdict") != "PASS":
            errors.append(f"{label}: completed run requires PASS verification")
    return errors


def validate_trusted_pr_control_semantics(
    control: dict[str, Any],
    label: str,
) -> list[str]:
    errors: list[str] = []
    declared_blockers = set(control.get("deterministic_blockers", []))
    unknown_blockers = sorted(declared_blockers - TRUSTED_CONTROL_BLOCKERS)
    if unknown_blockers:
        errors.append(f"{label}: unknown deterministic blockers: {unknown_blockers}")

    diff_lock = control.get("diff_lock", {})
    detected: set[str] = set()
    head_before = diff_lock.get("head_before")
    head_after = diff_lock.get("head_after")
    digest_after = diff_lock.get("digest_after")
    trusted_base = control.get("trusted_base", {})
    if trusted_base.get("commit") != diff_lock.get("base_commit"):
        detected.add("untrusted_base")
    trusted_repository = trusted_base.get("repository")
    if isinstance(trusted_repository, str):
        try:
            normalized_repository = normalize_remote_url(trusted_repository)
        except SnapshotError:
            detected.add("untrusted_base")
        else:
            if normalized_repository != trusted_repository:
                detected.add("untrusted_base")
    if head_before != head_after:
        detected.add("head_changed")
    if diff_lock.get("digest_before") != digest_after:
        detected.add("diff_digest_changed")

    change_run = control.get("change_run", {})
    implementer_identity = change_run.get("implementer_identity")
    if change_run.get("reviewed_head_sha") != head_after:
        detected.add("head_changed")
        errors.append(f"{label}: change run is not bound to the locked head")
    if change_run.get("diff_digest") != digest_after:
        detected.add("diff_digest_changed")
        errors.append(f"{label}: change run is not bound to the locked diff digest")
    changed_paths = change_run.get("changed_paths", [])
    errors.extend(
        validate_scope_paths(
            changed_paths,
            f"{label}:change_run.changed_paths",
            allow_glob=False,
            allow_symbolic=False,
        )
    )

    trust_anchors = control.get("trust_anchors", {})
    anchor_paths = trust_anchors.get("paths", [])
    errors.extend(
        validate_scope_paths(
            anchor_paths,
            f"{label}:trust_anchors.paths",
            allow_glob=True,
            allow_symbolic=False,
        )
    )
    missing_anchors = sorted(MANDATORY_TRUST_ANCHORS - set(anchor_paths))
    if missing_anchors:
        detected.add("trust_anchor_changed_without_meta_review")
        errors.append(
            f"{label}: mandatory trust anchors are missing: {missing_anchors}"
        )
    if (
        trust_anchors.get("profile") != "portable-v1"
        or trust_anchors.get("human_approval_required") is not True
        or trust_anchors.get("meta_review_required") is not True
    ):
        detected.add("trust_anchor_changed_without_meta_review")

    evidence_items = [
        item
        for item in control.get("approval_evidence", [])
        if isinstance(item, dict)
    ]

    def require_bound_approval(kind: str, purpose: str) -> bool:
        candidates = [
            item for item in evidence_items if item.get("kind") == kind
        ]
        if len(candidates) != 1:
            errors.append(
                f"{label}: {purpose} requires exactly one {kind} approval"
            )
            return False
        evidence = candidates[0]
        evidence_errors: list[str] = []
        if evidence.get("reviewer_type") != "human":
            evidence_errors.append("reviewer must be an identified human")
        if evidence.get("reviewer_identity") == implementer_identity:
            evidence_errors.append("reviewer identity must differ from implementer")
        if evidence.get("reviewed_head_sha") != head_after:
            evidence_errors.append("reviewed head SHA is stale or wrong")
        if evidence.get("diff_digest") != digest_after:
            evidence_errors.append("reviewed diff digest is stale or wrong")
        if evidence.get("verdict") != "PASS":
            evidence_errors.append("approval verdict is not PASS")
        _, evidence_path_error = parse_posix_scope(
            evidence.get("evidence_ref"),
            allow_glob=False,
            allow_symbolic=False,
        )
        if evidence_path_error:
            evidence_errors.append("evidence reference is unsafe")
        if evidence_errors:
            errors.extend(
                f"{label}: {purpose} evidence {message}"
                for message in evidence_errors
            )
            return False
        return True

    touched_trust_anchors = sorted(
        path
        for path in changed_paths
        if isinstance(path, str)
        and any(
            path_scope_is_subset(path, anchor)
            for anchor in anchor_paths
            if isinstance(anchor, str)
        )
    )
    if touched_trust_anchors and not require_bound_approval(
        "trust_anchor_meta_review",
        "trust-anchor change",
    ):
        detected.add("trust_anchor_changed_without_meta_review")

    source_trust = control.get("source_trust", {})
    if source_trust.get("origin") == "fork":
        handling = source_trust.get("external_provider_handling")
        if handling == "manual_review":
            if not require_bound_approval(
                "fork_manual_review",
                "fork processing",
            ):
                detected.add("fork_external_processing")
        else:
            detected.add("fork_external_processing")

    permissions = control.get("permissions", {})
    if permissions.get("review") != "read_only":
        detected.add("review_not_read_only")
    if (
        permissions.get("merge") != "write_separate_controller"
        or permissions.get("separated") is not True
    ):
        detected.add("merge_authority_not_separated")

    required_checks = control.get("required_checks", {})
    required_names = required_checks.get("required_names", [])
    results = required_checks.get("results", [])
    result_names = [
        result.get("name") for result in results if isinstance(result, dict)
    ]
    if len(result_names) != len(set(result_names)):
        detected.add("duplicate_required_check")
    missing_checks = sorted(set(required_names) - set(result_names))
    if missing_checks:
        detected.add("missing_required_check")
        errors.append(f"{label}: missing required checks: {missing_checks}")
    unexpected_checks = sorted(set(result_names) - set(required_names))
    if unexpected_checks:
        errors.append(f"{label}: unexpected required-check results: {unexpected_checks}")
    for result in results:
        if not isinstance(result, dict):
            continue
        if result.get("head_sha") != head_after or result.get("latest_attempt") is not True:
            detected.add("stale_check_attempt")
        if result.get("conclusion") != "PASS":
            detected.add("failed_required_check")

    expected_head = control.get("merge_control", {}).get("expected_head")
    if expected_head != head_after:
        detected.add("head_changed")

    missing_declared = sorted(detected - declared_blockers)
    if missing_declared:
        errors.append(
            f"{label}: deterministic blockers are not declared: {missing_declared}"
        )
    stale_declared = sorted(declared_blockers - detected)
    if stale_declared:
        errors.append(
            f"{label}: deterministic blockers lack matching state: {stale_declared}"
        )

    status = control.get("deterministic_status")
    if status == "PASS" and (detected or declared_blockers):
        errors.append(f"{label}: PASS cannot retain deterministic blockers")
    if status == "BLOCKED" and not (detected or declared_blockers):
        errors.append(f"{label}: BLOCKED requires a deterministic blocker")

    dependency_names = [
        dependency.get("name")
        for dependency in control.get("automation_dependencies", [])
        if isinstance(dependency, dict)
    ]
    if len(dependency_names) != len(set(dependency_names)):
        errors.append(f"{label}: automation dependency names must be unique")
    return errors


def validate_consumer_snapshot_manifest_semantics(
    manifest: dict[str, Any],
    label: str,
) -> list[str]:
    include = manifest.get("include", [])
    errors: list[str] = []
    missing = sorted(REQUIRED_CONSUMER_INCLUDES - set(include))
    unknown = sorted(set(include) - REQUIRED_CONSUMER_INCLUDES)
    if missing:
        errors.append(f"{label}: snapshot manifest omits required paths: {missing}")
    if unknown:
        errors.append(f"{label}: snapshot manifest contains unknown paths: {unknown}")
    return errors


def validate_consumer_snapshot_lock_semantics(
    lock: dict[str, Any],
    label: str,
) -> list[str]:
    errors: list[str] = []
    upstream_url = lock.get("upstream_url")
    if isinstance(upstream_url, str):
        try:
            normalized_url = normalize_remote_url(upstream_url)
        except SnapshotError as exc:
            errors.append(f"{label}: invalid upstream URL: {exc}")
            normalized_url = upstream_url
            valid_upstream_url = False
        else:
            valid_upstream_url = True
            if normalized_url != upstream_url:
                errors.append(f"{label}: upstream URL is not canonical")
    else:
        normalized_url = ""
        valid_upstream_url = False
    entries = lock.get("included_paths", [])
    paths = [
        entry.get("path") for entry in entries if isinstance(entry, dict)
    ]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        errors.append(f"{label}: included paths must be sorted and unique")
    for path in paths:
        if not isinstance(path, str):
            continue
        _, path_error = parse_posix_scope(
            path,
            allow_glob=False,
            allow_symbolic=False,
        )
        if path_error:
            errors.append(f"{label}: unsafe included path '{path}': {path_error}")
            continue
        if any(
            path_component_is_sensitive(component)
            for component in path.split("/")
        ):
            errors.append(f"{label}: sensitive included path is forbidden: {path}")
            continue
        if not any(
            path == allowed or path.startswith(f"{allowed}/")
            for allowed in REQUIRED_CONSUMER_INCLUDES
        ):
            errors.append(f"{label}: included path is not canonical: {path}")
    typed_entries = [
        {
            "path": entry.get("path"),
            "mode": entry.get("mode"),
            "sha256": entry.get("sha256"),
        }
        for entry in entries
        if isinstance(entry, dict)
    ]
    invalid_modes = sorted(
        {
            str(entry.get("mode"))
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("mode") not in {"100644", "100755"}
        }
    )
    if invalid_modes:
        errors.append(f"{label}: invalid snapshot modes: {invalid_modes}")
    schema_version = lock.get("schema_version")
    commit = lock.get("commit")
    if valid_upstream_url and all(
        isinstance(value, str)
        for value in (schema_version, normalized_url, commit)
    ):
        expected_identity = snapshot_identity_digest(
            schema_version,
            normalized_url,
            commit,
            typed_entries,
        )
        if lock.get("snapshot_identity_sha256") != expected_identity:
            errors.append(
                f"{label}: snapshot identity hash does not match metadata and entries"
            )
    return errors


def validate_consumer_overlay_semantics(
    overlay: dict[str, Any],
    label: str,
) -> list[str]:
    expected = [
        "consumer_root",
        "project_domain_overlay",
        "pinned_framework",
        "generated_adapter",
    ]
    errors: list[str] = []
    if overlay.get("precedence") != expected:
        errors.append(f"{label}: consumer precedence order is invalid")
    if overlay.get("conflict_resolution") != "stricter_wins_fail_closed":
        errors.append(f"{label}: overlay conflicts must fail closed")
    return errors


def validate_portable_contracts() -> tuple[list[str], int]:
    definitions = [
        (
            ROOT / "consumer" / "snapshot-manifest.json",
            "consumer-snapshot-manifest.schema.json",
            validate_consumer_snapshot_manifest_semantics,
        ),
        (
            ROOT / "consumer" / "examples" / "snapshot-lock.json",
            "consumer-snapshot-lock.schema.json",
            validate_consumer_snapshot_lock_semantics,
        ),
        (
            ROOT / "consumer" / "examples" / "overlay.yaml",
            "consumer-overlay.schema.json",
            validate_consumer_overlay_semantics,
        ),
    ]
    errors: list[str] = []
    for path, schema_name, semantic_validator in definitions:
        relative = path.relative_to(ROOT).as_posix()
        try:
            instance = load_artifact(path)
        except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"{relative}: {exc}")
            continue
        schema_validation_errors = schema_errors(instance, schema_name, relative)
        errors.extend(schema_validation_errors)
        if not schema_validation_errors:
            errors.extend(semantic_validator(instance, relative))
    return errors, len(definitions)


def example_schema(path: Path) -> str | None:
    if path.parent.name == "hook-events":
        return "hook-event.schema.json"
    if path.parent.name == "handoffs":
        return "handoff.schema.json"
    if path.name.startswith("task-envelope"):
        return "task-envelope.schema.json"
    if path.name.startswith("plan."):
        return "plan.schema.json"
    return EXAMPLE_SCHEMAS.get(path.name)


def validate_examples(
    agents: dict[str, dict[str, Any]],
    selected: Path | None = None,
) -> tuple[list[str], int]:
    errors: list[str] = []
    event_policy, event_policy_errors = load_event_policy()
    errors.extend(event_policy_errors)
    errors.extend(validate_event_policy_semantics(event_policy, agents))
    paths = (
        [selected]
        if selected
        else sorted((ROOT / "collaboration" / "examples").rglob("*.yaml"))
    )
    count = 0
    for path in paths:
        if path is None:
            continue
        resolved = path if path.is_absolute() else ROOT / path
        resolved = resolved.resolve()
        if ROOT not in resolved.parents:
            errors.append(f"{path}: example path escapes repository")
            continue
        schema_name = example_schema(resolved)
        if schema_name is None:
            errors.append(f"{resolved.relative_to(ROOT)}: no schema mapping for example")
            continue
        instance = load_yaml(resolved)
        relative = resolved.relative_to(ROOT).as_posix()
        errors.extend(schema_errors(instance, schema_name, relative))
        if resolved.name.startswith("task-envelope"):
            errors.extend(validate_task_semantics(instance, relative))
        elif resolved.name == "finding.yaml":
            errors.extend(
                validate_finding_semantics(
                    instance, agents, ROOT, relative, for_pass=False
                )
            )
        elif resolved.name == "handoff.yaml" or resolved.parent.name == "handoffs":
            errors.extend(validate_handoff_semantics(instance, agents, relative))
        elif schema_name == "plan.schema.json":
            task = load_yaml(ROOT / "collaboration/examples/task-envelope.yaml")
            errors.extend(
                validate_plan_semantics(
                    instance,
                    task,
                    agents,
                    event_policy,
                    relative,
                    require_approved=instance.get("status") == "approved",
                )
            )
        elif resolved.name == "verdict.yaml":
            task = load_yaml(ROOT / "collaboration/examples/task-envelope.yaml")
            plan = load_yaml(ROOT / "collaboration/examples/plan.yaml")
            errors.extend(
                validate_verdict_semantics(
                    instance,
                    task,
                    plan,
                    agents,
                    event_policy,
                    ROOT,
                    relative,
                )
            )
        elif resolved.name == "run-record.yaml":
            errors.extend(
                validate_run_record_semantics(
                    instance, agents, event_policy, ROOT, relative
                )
            )
        elif schema_name == "trusted-pr-control.schema.json":
            errors.extend(validate_trusted_pr_control_semantics(instance, relative))
        elif resolved.parent.name == "hook-events":
            fixture_actor = instance.get("actor", {})
            hook_errors, _ = validate_hook_event_artifact(
                resolved,
                ROOT,
                instance.get("event"),
                fixture_actor.get("agent_id"),
                fixture_actor.get("mode"),
            )
            errors.extend(hook_errors)
        count += 1
    return errors, count


def validate_hooks(manifest_override: dict[str, Any] | None = None) -> list[str]:
    path = ROOT / "hooks" / "hooks.yaml"
    manifest = manifest_override if manifest_override is not None else load_yaml(path)
    errors = schema_errors(manifest, "hooks-manifest.schema.json", "hooks/hooks.yaml")
    hook_ids = [hook.get("id") for hook in manifest.get("hooks", [])]
    if len(hook_ids) != len(set(hook_ids)):
        errors.append("hooks/hooks.yaml: hook ids must be unique")

    event_policy, event_policy_errors = load_event_policy()
    errors.extend(event_policy_errors)
    event_schema = load_json(ROOT / "schemas" / "hook-event.schema.json")
    allowed_events = set(event_schema["properties"]["event"]["enum"])
    gated_events: set[str] = set()
    for hook in manifest.get("hooks", []):
        event = hook.get("event")
        if event not in allowed_events:
            errors.append(f"hooks/hooks.yaml: unknown event '{event}'")
        command = hook.get("command", [])
        required_command = [
            "python3",
            "scripts/validate.py",
            "--hook-event",
            "{event_path}",
            "--artifact-root",
            "{workspace_root}",
            "--expected-event",
            event,
            "--expected-actor",
            "{actor_id}",
            "--expected-mode",
            "{actor_mode}",
        ]
        if command != required_command:
            errors.append(
                f"hooks/hooks.yaml: hook {hook.get('id')} must validate the actual "
                "event and workspace with the expected event"
            )
        if hook.get("blocking") is not True:
            errors.append(
                f"hooks/hooks.yaml: canonical gate {hook.get('id')} must be blocking"
            )
        else:
            gated_events.add(event)
    required_gates = {
        event
        for event, policy in event_policy.get("events", {}).items()
        if policy.get("blocking_required")
    }
    missing_gates = sorted(required_gates - gated_events)
    if missing_gates:
        errors.append(
            f"hooks/hooks.yaml: missing blocking security-critical gates: {missing_gates}"
        )
    return errors


def validate_hook_event_artifact(
    event_path: Path,
    artifact_root: Path,
    expected_event: str | None = None,
    expected_actor: str | None = None,
    expected_mode: str | None = None,
) -> tuple[list[str], dict[str, Any] | None]:
    errors: list[str] = []
    resolved_event, path_errors = resolve_artifact(
        event_path, artifact_root, "hook event"
    )
    errors.extend(path_errors)
    if resolved_event is None:
        return errors, None
    event, event_load_errors = load_resolved_artifact(resolved_event, "hook event")
    errors.extend(event_load_errors)
    if event is None:
        return errors, None

    event_label = resolved_event.relative_to(artifact_root.resolve()).as_posix()
    errors.extend(schema_errors(event, "hook-event.schema.json", event_label))
    event_name = event.get("event")
    if expected_event is not None and event_name != expected_event:
        errors.append(
            f"{event_label}: expected event {expected_event}, received {event_name}"
        )
    payload = event.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    missing_fields = sorted(
        set(EVENT_ARTIFACT_FIELDS.get(event_name, ())) - payload.keys()
    )
    if missing_fields:
        errors.append(
            f"{event_label}: event {event_name} lacks artifacts: {missing_fields}"
        )
        return errors, event

    agent_errors, agents = validate_agent_manifests()
    errors.extend(agent_errors)
    event_policy, event_policy_errors = load_event_policy()
    errors.extend(event_policy_errors)
    actor = event.get("actor")
    actor = actor if isinstance(actor, dict) else {}
    actor_id = actor.get("agent_id")
    if expected_actor is None or expected_mode is None:
        errors.append(
            f"{event_label}: trusted runtime actor identity and mode are required"
        )
    else:
        if actor_id != expected_actor:
            errors.append(
                f"{event_label}: event actor does not match trusted runtime actor"
            )
        if actor.get("mode") != expected_mode:
            errors.append(
                f"{event_label}: event mode does not match trusted runtime mode"
            )
    actor_agent = agents.get(actor_id)
    if actor_agent is None:
        errors.append(f"{event_label}: unknown actor agent '{actor_id}'")
    elif actor_agent.get("mode") != actor.get("mode"):
        errors.append(f"{event_label}: actor mode does not match agent manifest")

    event_rule = event_policy.get("events", {}).get(event_name)
    if event_rule is None:
        errors.append(f"{event_label}: no authorization policy for event {event_name}")
    else:
        if actor.get("mode") not in event_rule.get("allowed_modes", []):
            errors.append(
                f"{event_label}: actor mode {actor.get('mode')} is not allowed "
                f"for {event_name}"
            )
        allowed_agents = event_rule.get("allowed_agents", [])
        if allowed_agents and actor_id not in allowed_agents:
            errors.append(
                f"{event_label}: actor {actor_id} is not allowed for {event_name}"
            )

    task: dict[str, Any] | None = None
    if "task_envelope_path" in payload:
        task_path, task_path_errors = resolve_artifact(
            payload["task_envelope_path"], artifact_root, event_label
        )
        errors.extend(task_path_errors)
        if task_path is not None:
            task, task_load_errors = load_resolved_artifact(task_path, event_label)
            errors.extend(task_load_errors)
            if task is not None:
                task_label = task_path.relative_to(artifact_root.resolve()).as_posix()
                task_schema_errors = schema_errors(
                    task, "task-envelope.schema.json", task_label
                )
                errors.extend(task_schema_errors)
                if not task_schema_errors:
                    errors.extend(validate_task_semantics(task, task_label))
                if task.get("task_id") != event.get("task_id"):
                    errors.append(f"{event_label}: event task_id does not match task")

    handoff: dict[str, Any] | None = None
    if event_rule and event_rule.get("assignment_required"):
        handoff_path, handoff_path_errors = resolve_artifact(
            payload.get("handoff_path", ""), artifact_root, event_label
        )
        errors.extend(handoff_path_errors)
        if handoff_path is not None:
            handoff, handoff_load_errors = load_resolved_artifact(
                handoff_path, event_label
            )
            errors.extend(handoff_load_errors)
            if handoff is not None:
                handoff_label = handoff_path.relative_to(
                    artifact_root.resolve()
                ).as_posix()
                handoff_schema_errors = schema_errors(
                    handoff, "handoff.schema.json", handoff_label
                )
                errors.extend(handoff_schema_errors)
                if not handoff_schema_errors:
                    errors.extend(
                        validate_handoff_semantics(handoff, agents, handoff_label)
                    )
                if handoff.get("to") != actor_id:
                    errors.append(
                        f"{event_label}: event actor must be handoff recipient"
                    )
                if handoff.get("task_id") != event.get("task_id"):
                    errors.append(f"{event_label}: handoff task_id does not match event")
                if handoff.get("run_id") != event.get("run_id"):
                    errors.append(f"{event_label}: handoff run_id does not match event")
                context = handoff.get("context", {})
                if context.get("task_envelope") != payload.get("task_envelope_path"):
                    errors.append(
                        f"{event_label}: handoff task artifact does not match event"
                    )
                if "plan_path" in payload and context.get("plan") != payload.get(
                    "plan_path"
                ):
                    errors.append(
                        f"{event_label}: handoff plan artifact does not match event"
                    )

    plan: dict[str, Any] | None = None
    if "plan_path" in payload and task is not None:
        plan_path, plan_path_errors = resolve_artifact(
            payload.get("plan_path", ""), artifact_root, event_label
        )
        errors.extend(plan_path_errors)
        if plan_path is not None:
            plan, plan_load_errors = load_resolved_artifact(plan_path, event_label)
            errors.extend(plan_load_errors)
            if plan is not None:
                plan_label = plan_path.relative_to(artifact_root.resolve()).as_posix()
                plan_schema_errors = schema_errors(
                    plan, "plan.schema.json", plan_label
                )
                errors.extend(plan_schema_errors)
                if not plan_schema_errors:
                    errors.extend(
                        validate_plan_semantics(
                            plan,
                            task,
                            agents,
                            event_policy,
                            plan_label,
                            require_approved=event_name
                            in {
                                "plan.approved",
                                "implementation.started",
                                "command.requested",
                                "verification.completed",
                            },
                        )
                    )
                if (
                    event_name == "plan.approved"
                    and isinstance(plan.get("approval"), dict)
                    and plan["approval"].get("reviewer") != actor_id
                ):
                    errors.append(
                        f"{event_label}: plan approval actor must match approver"
                    )

    if event_name in WRITE_EVENT_NAMES and task is not None:
        if task.get("status") in {"completed", "blocked", "cancelled"}:
            errors.append(
                f"{event_label}: {task.get('status')} task cannot request writes"
            )
        unknown = sorted(
            name
            for name, impact in task.get("platform_impact", {}).items()
            if impact == "unknown"
        )
        if unknown:
            errors.append(
                f"{event_label}: write gate rejects unknown platform impact: {unknown}"
            )
        if event_name == "implementation.started":
            if task.get("status") not in {"plan_approved", "implementing"}:
                errors.append(
                    f"{event_label}: implementation requires plan_approved task state"
                )
            if not (
                handoff
                and handoff.get("authorized_scope", {}).get("write", [])
            ):
                errors.append(
                    f"{event_label}: implementation assignment requires write scope"
                )

    if (
        event_name == "command.requested"
        and task is not None
        and task.get("status") in {"completed", "blocked", "cancelled"}
    ):
        errors.append(
            f"{event_label}: {task.get('status')} task cannot request commands"
        )

    if event_name == "file.write.requested":
        requested_paths = payload.get("requested_paths")
        if not isinstance(requested_paths, list) or not requested_paths:
            errors.append(f"{event_label}: file write requires requested paths")
            requested_paths = []
        errors.extend(
            validate_scope_paths(
                requested_paths,
                f"{event_label}:requested_paths",
                allow_glob=False,
                allow_symbolic=False,
            )
        )
        manifest_writes = (
            actor_agent.get("path_policy", {}).get("write", [])
            if actor_agent is not None
            else []
        )
        handoff_writes = (
            handoff.get("authorized_scope", {}).get("write", [])
            if handoff is not None
            else []
        )
        for requested in requested_paths:
            if not any(
                path_scope_is_subset(str(requested), str(permitted))
                for permitted in manifest_writes
            ):
                errors.append(
                    f"{event_label}: requested path '{requested}' exceeds actor manifest"
                )
            if not any(
                path_scope_is_subset(str(requested), str(permitted))
                for permitted in handoff_writes
            ):
                errors.append(
                    f"{event_label}: requested path '{requested}' exceeds handoff"
                )

    if event_name == "command.requested":
        command_id = payload.get("command_id")
        argv = payload.get("argv")
        errors.extend(validate_argv(argv, event_policy, event_label))
        trusted_commands = {
            command.get("id"): command.get("argv")
            for command in (plan or {}).get("required_commands", [])
            if isinstance(command, dict)
        }
        if trusted_commands.get(command_id) != argv:
            errors.append(
                f"{event_label}: command argv is not authorized by approved plan"
            )
        authorized_commands = (
            handoff.get("authorized_commands", []) if handoff is not None else []
        )
        if command_id not in authorized_commands:
            errors.append(
                f"{event_label}: command id is not authorized by handoff"
            )

    if event_name == "review.completed":
        review_path, review_path_errors = resolve_artifact(
            payload.get("review_verdict_path", ""), artifact_root, event_label
        )
        errors.extend(review_path_errors)
        if review_path is not None:
            review, review_load_errors = load_resolved_artifact(
                review_path, event_label
            )
            errors.extend(review_load_errors)
            if review is not None:
                review_label = review_path.relative_to(
                    artifact_root.resolve()
                ).as_posix()
                review_schema_errors = schema_errors(
                    review, "review-verdict.schema.json", review_label
                )
                errors.extend(review_schema_errors)
                if not review_schema_errors:
                    errors.extend(
                        validate_review_verdict_semantics(
                            review,
                            event.get("task_id", ""),
                            agents,
                            artifact_root,
                            review_label,
                        )
                    )
                if review.get("reviewer") != actor_id:
                    errors.append(
                        f"{event_label}: review actor must match verdict reviewer"
                    )

    if event_name == "verification.completed" and task is not None:
        verdict_path, verdict_path_errors = resolve_artifact(
            payload.get("verdict_path", ""), artifact_root, event_label
        )
        errors.extend(verdict_path_errors)
        if verdict_path is not None:
            verdict, verdict_load_errors = load_resolved_artifact(
                verdict_path, event_label
            )
            errors.extend(verdict_load_errors)
            if verdict is not None:
                verdict_label = verdict_path.relative_to(
                    artifact_root.resolve()
                ).as_posix()
                verdict_schema_errors = schema_errors(
                    verdict, "verdict.schema.json", verdict_label
                )
                errors.extend(verdict_schema_errors)
                if not verdict_schema_errors:
                    errors.extend(
                        validate_verdict_semantics(
                            verdict,
                            task,
                            plan,
                            agents,
                            event_policy,
                            artifact_root,
                            verdict_label,
                        )
                    )
                if verdict.get("verifier") != actor_id:
                    errors.append(
                        f"{event_label}: verification actor must match verdict verifier"
                    )

    if event_name == "task.completed":
        run_path, run_path_errors = resolve_artifact(
            payload.get("run_record_path", ""), artifact_root, event_label
        )
        errors.extend(run_path_errors)
        if run_path is not None:
            record, record_load_errors = load_resolved_artifact(run_path, event_label)
            errors.extend(record_load_errors)
            if record is not None:
                run_label = run_path.relative_to(artifact_root.resolve()).as_posix()
                record_schema_errors = schema_errors(
                    record, "run-record.schema.json", run_label
                )
                errors.extend(record_schema_errors)
                if not record_schema_errors:
                    errors.extend(
                        validate_run_record_semantics(
                            record, agents, event_policy, artifact_root, run_label
                        )
                    )
                if record.get("run_id") != event.get("run_id"):
                    errors.append(f"{event_label}: run record run_id does not match event")
                if record.get("task_id") != event.get("task_id"):
                    errors.append(
                        f"{event_label}: run record task_id does not match event"
                    )
    return errors, event


def validate_adapter_declarations(
    policy: dict[str, Any],
) -> tuple[list[str], int]:
    errors: list[str] = []
    count = 0
    known_capabilities = set(policy.get("capabilities", []))
    known_tools = set(policy.get("tools", []))
    for path in sorted((ROOT / "adapters").rglob("*.adapter.yaml")):
        relative = path.relative_to(ROOT).as_posix()
        declaration = load_yaml(path)
        errors.extend(
            schema_errors(declaration, "adapter-declaration.schema.json", relative)
        )
        for mapping in declaration.get("tool_mappings", []):
            if mapping.get("capability") not in known_capabilities:
                errors.append(
                    f"{relative}: adapter maps unknown capability "
                    f"'{mapping.get('capability')}'"
                )
            if mapping.get("canonical_tool") not in known_tools:
                errors.append(
                    f"{relative}: adapter maps unknown canonical tool "
                    f"'{mapping.get('canonical_tool')}'"
                )
        enforcement = declaration.get("permission_enforcement", {})
        if declaration.get("automatic_writes"):
            missing = sorted(
                name
                for name in ("mode", "path", "approval", "trusted_identity")
                if enforcement.get(name) is not True
            )
            if missing:
                errors.append(
                    f"{relative}: automatic writes require enforcement: {missing}"
                )
            if declaration.get("compatibility_level", 0) < 3:
                errors.append(
                    f"{relative}: automatic writes require compatibility level 3"
                )
        if declaration.get("automatic_commands"):
            missing = sorted(
                name
                for name in ("mode", "approval", "trusted_identity")
                if enforcement.get(name) is not True
            )
            if missing:
                errors.append(
                    f"{relative}: automatic commands require enforcement: {missing}"
                )
            if declaration.get("compatibility_level", 0) < 3:
                errors.append(
                    f"{relative}: automatic commands require compatibility level 3"
                )
        count += 1
    if count == 0:
        errors.append("adapters: at least one conformance declaration is required")
    return errors, count


def validate_repository(
    selected_example: Path | None = None,
) -> tuple[list[str], dict[str, int]]:
    errors, agents = validate_agent_manifests()
    event_policy, event_policy_errors = load_event_policy()
    errors.extend(event_policy_errors)
    errors.extend(validate_event_policy_semantics(event_policy, agents))
    platform_errors, platform_count = validate_platform_profiles(agents)
    skill_errors, skill_count = validate_skills()
    example_errors, example_count = validate_examples(agents, selected_example)
    portable_errors, portable_count = validate_portable_contracts()
    policy = load_yaml(ROOT / "registries/runtime-policy.yaml")
    adapter_errors, adapter_count = validate_adapter_declarations(policy)
    errors.extend(platform_errors)
    errors.extend(skill_errors)
    errors.extend(example_errors)
    errors.extend(portable_errors)
    errors.extend(validate_hooks())
    errors.extend(adapter_errors)
    counts = {
        "agents": len(agents),
        "platform_profiles": platform_count,
        "skills": skill_count,
        "examples": example_count,
        "adapters": adapter_count,
        "portable_contracts": portable_count,
    }
    return errors, counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--example",
        type=Path,
        help="Validate one known collaboration example with canonical contracts.",
    )
    parser.add_argument(
        "--hook-event",
        type=Path,
        help="Validate one actual canonical hook event and every referenced artifact.",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        help="Workspace root used to resolve hook artifact references.",
    )
    parser.add_argument(
        "--expected-event",
        help="Fail unless the actual hook event has this canonical event name.",
    )
    parser.add_argument(
        "--expected-actor",
        help="Trusted runtime actor id injected by the adapter.",
    )
    parser.add_argument(
        "--expected-mode",
        help="Trusted runtime actor mode injected by the adapter.",
    )
    args = parser.parse_args()

    if args.hook_event:
        if args.artifact_root is None:
            parser.error("--hook-event requires --artifact-root")
        errors, _ = validate_hook_event_artifact(
            args.hook_event,
            args.artifact_root,
            args.expected_event,
            args.expected_actor,
            args.expected_mode,
        )
        counts = None
    else:
        errors, counts = validate_repository(args.example)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if counts is None:
        print(f"Validated hook event: {args.hook_event}")
    else:
        print(
            "Validated "
            f"{counts['agents']} agents, "
            f"{counts['platform_profiles']} platform profiles, "
            f"{counts['skills']} skills, "
            f"{counts['examples']} examples, "
            f"{counts['adapters']} adapter declarations, "
            f"{counts['portable_contracts']} portable contracts, "
            "and the hook manifest."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
