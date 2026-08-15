"""Export and verify a deterministic, pinned framework snapshot."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = "1.0"
FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")
GIT_OBJECT_ID = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
REMOTE_USER = re.compile(r"^[A-Za-z0-9._-]+$")
REMOTE_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9._~-]+$")
REMOTE_HOST_LABEL = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
SCP_REMOTE = re.compile(
    r"^(?P<user>[A-Za-z0-9._-]+)@"
    r"(?P<host>[A-Za-z0-9.-]+):"
    r"(?P<path>[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*)$"
)
CANONICAL_ALLOWLIST = frozenset(
    {
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
)
FORBIDDEN_EXACT_PARTS = frozenset(
    {
        ".git",
        "artifacts",
        "adapters",
        "generated",
        "__pycache__",
    }
)
SENSITIVE_PATH_TOKENS = frozenset(
    {
        "credential",
        "credentials",
        "secret",
        "secrets",
        "token",
        "tokens",
        "key",
        "keys",
    }
)
SENSITIVE_COMPOUNDS = frozenset(
    {
        "apikey",
        "accesskey",
        "privatekey",
        "secretkey",
        "authtoken",
        "accesstoken",
        "credentialstore",
        "secretstore",
    }
)
SENSITIVE_FILENAMES = frozenset({"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"})
SENSITIVE_SUFFIXES = (".key", ".pem", ".p12", ".pfx")


@dataclass
class TargetLocation:
    path: Path
    parent: Path
    name: str
    parent_fd: int
    parent_identity: tuple[int, int]

    def close(self) -> None:
        os.close(self.parent_fd)


class SnapshotError(ValueError):
    """Report a deterministic snapshot policy violation."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def snapshot_identity_digest(
    schema_version: str,
    upstream_url: str,
    commit: str,
    entries: list[dict[str, str]],
) -> str:
    identity = {
        "schema_version": schema_version,
        "upstream_url": normalize_remote_url(upstream_url),
        "commit": commit,
        "included_paths": entries,
    }
    return sha256_bytes(canonical_json(identity))


def path_component_is_sensitive(component: str) -> bool:
    lowered = component.casefold()
    if lowered == ".env" or lowered.startswith(".env."):
        return True
    if lowered in SENSITIVE_FILENAMES or lowered.endswith(SENSITIVE_SUFFIXES):
        return True
    camel_split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", component).casefold()
    tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", camel_split)
        if token
    }
    compact = "".join(tokens)
    return bool(
        tokens & SENSITIVE_PATH_TOKENS
        or compact in SENSITIVE_COMPOUNDS
    )


def validate_relative_path(value: Any, *, label: str = "path") -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotError(f"{label} must be a non-empty relative path")
    if "\x00" in value or "\\" in value:
        raise SnapshotError(f"{label} contains a forbidden separator or NUL")
    pure = PurePosixPath(value)
    parts = value.split("/")
    if pure.is_absolute() or value.startswith("/"):
        raise SnapshotError(f"{label} must not be absolute: {value}")
    if any(part in {"", ".", ".."} for part in parts):
        raise SnapshotError(f"{label} contains traversal or empty segments: {value}")
    if any(not SAFE_SEGMENT.fullmatch(part) for part in parts):
        raise SnapshotError(f"{label} contains an unsafe segment: {value}")
    if any(part.casefold() in FORBIDDEN_EXACT_PARTS for part in parts):
        raise SnapshotError(f"{label} contains a forbidden path component: {value}")
    if any(path_component_is_sensitive(part) for part in parts):
        raise SnapshotError(f"{label} contains a sensitive path component: {value}")
    return pure.as_posix()


def validate_remote_host(host: str) -> str:
    lowered = host.casefold()
    if (
        not lowered
        or len(lowered) > 253
        or lowered == "localhost"
        or lowered.endswith((".localhost", ".local"))
    ):
        raise SnapshotError("remote host is not portable")
    try:
        ipaddress.ip_address(lowered)
    except ValueError:
        labels = lowered.split(".")
        if len(labels) < 2 or any(
            not REMOTE_HOST_LABEL.fullmatch(label) for label in labels
        ):
            raise SnapshotError("remote host is not a portable DNS name")
    else:
        raise SnapshotError("IP-literal remotes are not portable")
    return lowered


def validate_remote_path(path: str, *, absolute: bool) -> str:
    if absolute:
        if not path.startswith("/"):
            raise SnapshotError("remote URI path must be absolute")
        path = path[1:]
    elif path.startswith("/"):
        raise SnapshotError("SCP-like remote path must be relative")
    segments = path.split("/")
    if not path or any(
        segment in {"", ".", ".."}
        or not REMOTE_PATH_SEGMENT.fullmatch(segment)
        for segment in segments
    ):
        raise SnapshotError("remote path contains unsafe or empty segments")
    return f"/{path}" if absolute else path


def normalize_remote_url(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotError("remote URL must be a non-empty string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise SnapshotError("remote URL contains control characters")
    if any(character.isspace() for character in value):
        raise SnapshotError("remote URL contains whitespace")
    if "?" in value or "#" in value:
        raise SnapshotError("remote URL query and fragment are forbidden")

    scp_match = SCP_REMOTE.fullmatch(value)
    if scp_match:
        host = validate_remote_host(scp_match.group("host"))
        path = validate_remote_path(scp_match.group("path"), absolute=False)
        return f"{scp_match.group('user')}@{host}:{path}"

    parsed = urlsplit(value)
    scheme = parsed.scheme.casefold()
    if scheme not in {"https", "ssh"}:
        raise SnapshotError("remote URL must use https://, ssh://, or SCP-like form")
    if not parsed.hostname:
        raise SnapshotError("remote URL host is required")
    host = validate_remote_host(parsed.hostname)
    try:
        port = parsed.port
    except ValueError as exc:
        raise SnapshotError("remote URL port is invalid") from exc
    if port is not None and not 1 <= port <= 65535:
        raise SnapshotError("remote URL port is invalid")

    user = parsed.username
    if parsed.password is not None:
        raise SnapshotError("remote URL must not contain a password")
    if scheme == "https" and user is not None:
        raise SnapshotError("HTTPS remote URL must not contain userinfo")
    if scheme == "ssh" and user is not None and not REMOTE_USER.fullmatch(user):
        raise SnapshotError("SSH remote username is invalid")

    path = validate_remote_path(parsed.path, absolute=True)
    default_port = 443 if scheme == "https" else 22
    port_suffix = f":{port}" if port is not None and port != default_port else ""
    user_prefix = f"{user}@" if user else ""
    return f"{scheme}://{user_prefix}{host}{port_suffix}{path}"


def load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"{label} is not readable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SnapshotError(f"{label} must be a JSON object")
    return value


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    if set(manifest) != {"schema_version", "include"}:
        raise SnapshotError("snapshot manifest has unknown or missing fields")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise SnapshotError("snapshot manifest schema_version is unsupported")
    include = manifest.get("include")
    if not isinstance(include, list) or not include:
        raise SnapshotError("snapshot manifest include must be a non-empty array")
    if len(include) != len({str(item) for item in include}):
        raise SnapshotError("snapshot manifest include paths must be unique")
    validated: list[str] = []
    for item in include:
        path_value = validate_relative_path(item, label="manifest include")
        if path_value not in CANONICAL_ALLOWLIST:
            raise SnapshotError(f"manifest includes unknown canonical path: {item}")
        validated.append(path_value)
    missing = sorted(CANONICAL_ALLOWLIST - set(validated))
    if missing:
        raise SnapshotError(f"snapshot manifest omits required paths: {missing}")
    return validated


def load_manifest(path: Path) -> list[str]:
    return validate_manifest(load_json_object(path, label="snapshot manifest"))


def load_manifest_blob(value: bytes) -> list[str]:
    try:
        manifest = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotError("snapshot manifest blob is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise SnapshotError("snapshot manifest blob must be a JSON object")
    return validate_manifest(manifest)


def safe_git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    environment.update(
        {
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ATTR_NOSYSTEM": "1",
        }
    )
    return environment


def safe_git_command(source: Path, *args: str) -> list[str]:
    return [
        "git",
        "--no-replace-objects",
        "-C",
        str(source),
        *args,
    ]


def run_git(source: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        safe_git_command(source, *args),
        capture_output=True,
        text=True,
        check=False,
        env=safe_git_environment(),
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise SnapshotError(detail)
    return result.stdout


def is_within(candidate: Path, parent: Path) -> bool:
    resolved_candidate = candidate.resolve()
    resolved_parent = parent.resolve()
    return (
        resolved_candidate == resolved_parent
        or resolved_parent in resolved_candidate.parents
    )


def directory_open_flags() -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise SnapshotError("platform lacks required no-follow directory primitives")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def open_directory_nofollow(path: Path) -> int:
    absolute = absolute_path(path)
    flags = directory_open_flags()
    anchor = absolute.anchor
    if not anchor:
        raise SnapshotError(f"directory path has no absolute anchor: {path}")
    current_fd = os.open(anchor, flags)
    try:
        for component in absolute.parts[1:]:
            next_fd = os.open(component, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
    except OSError as exc:
        os.close(current_fd)
        raise SnapshotError(
            f"directory chain is missing, non-directory, or symlinked: {path}"
        ) from exc
    return current_fd


def file_identity(file_stat: os.stat_result) -> tuple[int, int]:
    return file_stat.st_dev, file_stat.st_ino


def leaf_stat(location: TargetLocation) -> os.stat_result | None:
    try:
        return os.stat(
            location.name,
            dir_fd=location.parent_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None


def open_target_location(path: Path, *, label: str) -> TargetLocation:
    target = absolute_path(path)
    if target == Path(target.anchor) or not target.name:
        raise SnapshotError(f"{label} must not be a filesystem root")
    parent_fd = open_directory_nofollow(target.parent)
    parent_stat = os.fstat(parent_fd)
    location = TargetLocation(
        path=target,
        parent=target.parent,
        name=target.name,
        parent_fd=parent_fd,
        parent_identity=file_identity(parent_stat),
    )
    existing = leaf_stat(location)
    if existing is not None:
        location.close()
        kind = "symlink" if stat.S_ISLNK(existing.st_mode) else "existing path"
        raise SnapshotError(f"{label} must be absent; found {kind}")
    return location


def confirm_target_parent(
    location: TargetLocation,
    *,
    label: str,
    require_leaf_absent: bool,
) -> None:
    confirmation_fd = open_directory_nofollow(location.parent)
    try:
        if file_identity(os.fstat(confirmation_fd)) != location.parent_identity:
            raise SnapshotError(f"{label} parent identity changed")
    finally:
        os.close(confirmation_fd)
    if require_leaf_absent and leaf_stat(location) is not None:
        raise SnapshotError(f"{label} appeared during export")


def validate_targets(
    source: Path,
    output_dir: Path,
    lock_path: Path,
) -> tuple[TargetLocation, TargetLocation]:
    output_path = absolute_path(output_dir)
    lock_path = absolute_path(lock_path)
    if is_within(output_path, source) or is_within(lock_path, source):
        raise SnapshotError("snapshot output and lock must remain outside source repo")
    if is_within(lock_path, output_path):
        raise SnapshotError("snapshot lock must remain outside snapshot output")

    output = open_target_location(output_path, label="snapshot output")
    try:
        lock = open_target_location(lock_path, label="snapshot lock")
    except Exception:
        output.close()
        raise
    return output, lock


def validate_source(source: Path, source_ref: str) -> tuple[str, str]:
    if not source.is_dir():
        raise SnapshotError("source repo does not exist")
    if not FULL_COMMIT.fullmatch(source_ref):
        raise SnapshotError("source ref must be a full lowercase 40-hex commit")
    if run_git(source, "rev-parse", "--is-inside-work-tree").strip() != "true":
        raise SnapshotError("source path is not a git worktree")
    head = run_git(source, "rev-parse", "HEAD").strip()
    if head != source_ref:
        raise SnapshotError("source ref must exactly match checked-out HEAD")
    resolved_ref = run_git(
        source,
        "rev-parse",
        "--verify",
        f"{source_ref}^{{commit}}",
    ).strip()
    if resolved_ref != source_ref:
        raise SnapshotError("source ref does not resolve to the checked-out commit")
    if run_git(source, "status", "--porcelain=v1", "--untracked-files=all"):
        raise SnapshotError("source repo must be clean before export")
    raw_upstream_url = run_git(
        source,
        "config",
        "--get",
        "remote.origin.url",
    ).strip()
    if not raw_upstream_url:
        raise SnapshotError("source repo must declare remote.origin.url")
    upstream_url = normalize_remote_url(raw_upstream_url)
    return head, upstream_url


def matches_include(path: str, includes: list[str]) -> bool:
    return any(path == item or path.startswith(f"{item}/") for item in includes)


def run_git_bytes(source: Path, *args: str) -> bytes:
    result = subprocess.run(
        safe_git_command(source, *args),
        capture_output=True,
        check=False,
        env=safe_git_environment(),
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SnapshotError(detail or "git command failed")
    return result.stdout


def selected_git_files(
    source: Path,
    commit: str,
    includes: list[str],
) -> list[dict[str, str]]:
    output = run_git_bytes(
        source,
        "ls-tree",
        "-rz",
        "--full-tree",
        commit,
        "--",
        *includes,
    )
    selected: list[dict[str, str]] = []
    for raw_record in output.split(b"\0"):
        if not raw_record:
            continue
        metadata, separator, raw_path = raw_record.partition(b"\t")
        if not separator:
            raise SnapshotError("git tree returned malformed output")
        try:
            mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
            path = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise SnapshotError("git tree contains unportable metadata or path") from exc
        normalized = validate_relative_path(path, label="tracked path")
        if not matches_include(normalized, includes):
            raise SnapshotError(f"git tree returned an unknown path: {normalized}")
        if mode == "120000":
            raise SnapshotError(f"symlink is forbidden in snapshot: {normalized}")
        if object_type != "blob" or mode not in {"100644", "100755"}:
            raise SnapshotError(f"non-regular git object is forbidden: {normalized}")
        if not GIT_OBJECT_ID.fullmatch(object_id):
            raise SnapshotError(f"git tree returned an invalid blob id: {normalized}")
        selected.append({"path": normalized, "mode": mode, "object_id": object_id})
    if not selected:
        raise SnapshotError("snapshot manifest selected no tracked files")
    for include in includes:
        if not any(
            item["path"] == include
            or item["path"].startswith(f"{include}/")
            for item in selected
        ):
            raise SnapshotError(f"manifest path is missing from source commit: {include}")
    selected_paths = [item["path"] for item in selected]
    if len(selected_paths) != len(set(selected_paths)):
        raise SnapshotError("snapshot contains duplicate tracked paths")
    return sorted(selected, key=lambda item: item["path"])


def read_git_blob(source: Path, object_id: str) -> bytes:
    if not GIT_OBJECT_ID.fullmatch(object_id):
        raise SnapshotError("refusing invalid git blob id")
    return run_git_bytes(source, "cat-file", "blob", object_id)


def build_lock(
    upstream_url: str,
    commit: str,
    entries: list[dict[str, str]],
) -> dict[str, Any]:
    normalized_url = normalize_remote_url(upstream_url)
    lock = {
        "schema_version": SCHEMA_VERSION,
        "upstream_url": normalized_url,
        "commit": commit,
        "included_paths": entries,
    }
    lock["snapshot_identity_sha256"] = snapshot_identity_digest(
        SCHEMA_VERSION,
        normalized_url,
        commit,
        entries,
    )
    return lock


def write_all(file_fd: int, value: bytes) -> None:
    view = memoryview(value)
    while view:
        written = os.write(file_fd, view)
        if written <= 0:
            raise SnapshotError("failed to write staged snapshot content")
        view = view[written:]


def create_staging_directory(
    location: TargetLocation,
) -> tuple[str, int, tuple[int, int]]:
    for _attempt in range(32):
        name = f".{location.name}.staging-{secrets.token_hex(12)}"
        try:
            os.mkdir(name, 0o700, dir_fd=location.parent_fd)
        except FileExistsError:
            continue
        try:
            stage_fd = os.open(
                name,
                directory_open_flags(),
                dir_fd=location.parent_fd,
            )
        except OSError:
            os.rmdir(name, dir_fd=location.parent_fd)
            raise
        return name, stage_fd, file_identity(os.fstat(stage_fd))
    raise SnapshotError("could not allocate a unique snapshot staging directory")


def open_or_create_child_directory(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    child_fd = os.open(name, directory_open_flags(), dir_fd=parent_fd)
    os.fchmod(child_fd, 0o755)
    return child_fd


def write_staged_snapshot_file(
    stage_fd: int,
    relative: str,
    content: bytes,
    git_mode: str,
) -> None:
    parts = PurePosixPath(relative).parts
    current_fd = os.dup(stage_fd)
    try:
        for component in parts[:-1]:
            child_fd = open_or_create_child_directory(current_fd, component)
            os.close(current_fd)
            current_fd = child_fd
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        file_fd = os.open(parts[-1], flags, 0o600, dir_fd=current_fd)
        try:
            write_all(file_fd, content)
            os.fchmod(file_fd, 0o755 if git_mode == "100755" else 0o644)
            os.fsync(file_fd)
        finally:
            os.close(file_fd)
    finally:
        os.close(current_fd)


def create_staging_file(
    location: TargetLocation,
    content: bytes,
) -> tuple[str, tuple[int, int]]:
    for _attempt in range(32):
        name = f".{location.name}.staging-{secrets.token_hex(12)}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            file_fd = os.open(name, flags, 0o600, dir_fd=location.parent_fd)
        except FileExistsError:
            continue
        completed = False
        try:
            write_all(file_fd, content)
            os.fchmod(file_fd, 0o644)
            os.fsync(file_fd)
            identity = file_identity(os.fstat(file_fd))
            completed = True
        finally:
            os.close(file_fd)
            if not completed:
                os.unlink(name, dir_fd=location.parent_fd)
        return name, identity
    raise SnapshotError("could not allocate a unique snapshot lock staging file")


def remove_tree_at(
    parent_fd: int,
    name: str,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> None:
    try:
        current_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if expected_identity is not None and file_identity(current_stat) != expected_identity:
        return
    if not stat.S_ISDIR(current_stat.st_mode) or stat.S_ISLNK(current_stat.st_mode):
        os.unlink(name, dir_fd=parent_fd)
        return
    child_fd = os.open(name, directory_open_flags(), dir_fd=parent_fd)
    try:
        for entry in list(os.scandir(child_fd)):
            entry_stat = os.stat(
                entry.name,
                dir_fd=child_fd,
                follow_symlinks=False,
            )
            if stat.S_ISDIR(entry_stat.st_mode) and not stat.S_ISLNK(
                entry_stat.st_mode
            ):
                remove_tree_at(child_fd, entry.name)
            else:
                os.unlink(entry.name, dir_fd=child_fd)
    finally:
        os.close(child_fd)
    os.rmdir(name, dir_fd=parent_fd)


def unlink_at_if_matching(
    parent_fd: int,
    name: str,
    identity: tuple[int, int],
) -> None:
    try:
        current_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if file_identity(current_stat) == identity:
        os.unlink(name, dir_fd=parent_fd)


def export_snapshot(
    source_repo: Path,
    source_ref: str,
    output_dir: Path,
    lock_path: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    source = source_repo.resolve()
    output, lock_target = validate_targets(source, output_dir, lock_path)
    stage_name: str | None = None
    stage_identity: tuple[int, int] | None = None
    stage_fd: int | None = None
    lock_stage_name: str | None = None
    lock_stage_identity: tuple[int, int] | None = None
    published_output_identity: tuple[int, int] | None = None
    published_lock_identity: tuple[int, int] | None = None
    try:
        commit, upstream_url = validate_source(source, source_ref)
        selected_manifest = (
            manifest_path.resolve()
            if manifest_path is not None
            else source / "consumer" / "snapshot-manifest.json"
        )
        if not is_within(selected_manifest, source):
            raise SnapshotError("snapshot manifest must be inside source repo")
        manifest_relative = validate_relative_path(
            selected_manifest.relative_to(source).as_posix(),
            label="snapshot manifest path",
        )
        manifest_record = selected_git_files(
            source,
            commit,
            [manifest_relative],
        )[0]
        includes = load_manifest_blob(
            read_git_blob(source, manifest_record["object_id"])
        )
        selected = selected_git_files(source, commit, includes)

        entries: list[dict[str, str]] = []
        immutable_files: dict[str, tuple[bytes, str]] = {}
        for item in selected:
            content = read_git_blob(source, item["object_id"])
            immutable_files[item["path"]] = (content, item["mode"])
            entries.append(
                {
                    "path": item["path"],
                    "mode": item["mode"],
                    "sha256": sha256_bytes(content),
                }
            )
        if run_git(source, "rev-parse", "HEAD").strip() != commit or run_git(
            source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            raise SnapshotError("source repo changed during export")
        lock = build_lock(upstream_url, commit, entries)

        confirm_target_parent(
            output,
            label="snapshot output",
            require_leaf_absent=True,
        )
        confirm_target_parent(
            lock_target,
            label="snapshot lock",
            require_leaf_absent=True,
        )
        stage_name, stage_fd, stage_identity = create_staging_directory(output)
        for relative, (content, git_mode) in immutable_files.items():
            write_staged_snapshot_file(
                stage_fd,
                relative,
                content,
                git_mode,
            )
        os.fchmod(stage_fd, 0o755)
        os.fsync(stage_fd)
        os.close(stage_fd)
        stage_fd = None
        lock_stage_name, lock_stage_identity = create_staging_file(
            lock_target,
            canonical_json(lock),
        )

        confirm_target_parent(
            output,
            label="snapshot output",
            require_leaf_absent=True,
        )
        confirm_target_parent(
            lock_target,
            label="snapshot lock",
            require_leaf_absent=True,
        )
        validate_snapshot(
            output.parent / stage_name,
            lock_target.parent / lock_stage_name,
        )

        confirm_target_parent(
            output,
            label="snapshot output",
            require_leaf_absent=True,
        )
        confirm_target_parent(
            lock_target,
            label="snapshot lock",
            require_leaf_absent=True,
        )
        os.rename(
            stage_name,
            output.name,
            src_dir_fd=output.parent_fd,
            dst_dir_fd=output.parent_fd,
        )
        published_output_identity = stage_identity
        stage_name = None
        output_stat = leaf_stat(output)
        if (
            output_stat is None
            or not stat.S_ISDIR(output_stat.st_mode)
            or file_identity(output_stat) != published_output_identity
        ):
            raise SnapshotError("published snapshot output identity changed")

        os.link(
            lock_stage_name,
            lock_target.name,
            src_dir_fd=lock_target.parent_fd,
            dst_dir_fd=lock_target.parent_fd,
            follow_symlinks=False,
        )
        published_lock_identity = lock_stage_identity
        unlink_at_if_matching(
            lock_target.parent_fd,
            lock_stage_name,
            lock_stage_identity,
        )
        lock_stage_name = None
        confirm_target_parent(
            output,
            label="snapshot output",
            require_leaf_absent=False,
        )
        confirm_target_parent(
            lock_target,
            label="snapshot lock",
            require_leaf_absent=False,
        )
        validate_snapshot(output.path, lock_target.path)
        return lock
    except (OSError, SnapshotError) as exc:
        if published_lock_identity is not None:
            unlink_at_if_matching(
                lock_target.parent_fd,
                lock_target.name,
                published_lock_identity,
            )
        if published_output_identity is not None:
            remove_tree_at(
                output.parent_fd,
                output.name,
                expected_identity=published_output_identity,
            )
        if lock_stage_name is not None and lock_stage_identity is not None:
            unlink_at_if_matching(
                lock_target.parent_fd,
                lock_stage_name,
                lock_stage_identity,
            )
        if stage_name is not None and stage_identity is not None:
            remove_tree_at(
                output.parent_fd,
                stage_name,
                expected_identity=stage_identity,
            )
        if isinstance(exc, SnapshotError):
            raise
        raise SnapshotError(f"snapshot export failed safely: {exc}") from exc
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        output.close()
        lock_target.close()


def validate_lock(lock: dict[str, Any]) -> list[dict[str, str]]:
    required = {
        "schema_version",
        "upstream_url",
        "commit",
        "included_paths",
        "snapshot_identity_sha256",
    }
    if set(lock) != required:
        raise SnapshotError("snapshot lock has unknown or missing fields")
    if lock.get("schema_version") != SCHEMA_VERSION:
        raise SnapshotError("snapshot lock schema_version is unsupported")
    upstream_url = lock.get("upstream_url")
    if not isinstance(upstream_url, str) or not upstream_url:
        raise SnapshotError("snapshot lock upstream_url is required")
    normalized_url = normalize_remote_url(upstream_url)
    if normalized_url != upstream_url:
        raise SnapshotError("snapshot lock upstream URL is not canonical")
    if not isinstance(lock.get("commit"), str) or not FULL_COMMIT.fullmatch(
        lock["commit"]
    ):
        raise SnapshotError("snapshot lock commit must be full lowercase 40-hex")
    entries = lock.get("included_paths")
    if not isinstance(entries, list) or not entries:
        raise SnapshotError("snapshot lock included_paths must be non-empty")
    normalized: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "mode", "sha256"}:
            raise SnapshotError(
                "snapshot lock entry must contain path, mode, and sha256"
            )
        path = validate_relative_path(entry.get("path"), label="lock path")
        mode = entry.get("mode")
        if mode not in {"100644", "100755"}:
            raise SnapshotError(f"snapshot lock has invalid mode for {path}")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise SnapshotError(f"snapshot lock has invalid hash for {path}")
        if not matches_include(path, list(CANONICAL_ALLOWLIST)):
            raise SnapshotError(f"snapshot lock contains unknown path: {path}")
        normalized.append({"path": path, "mode": mode, "sha256": digest})
    paths = [entry["path"] for entry in normalized]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise SnapshotError("snapshot lock paths must be sorted and unique")
    expected_identity_digest = snapshot_identity_digest(
        SCHEMA_VERSION,
        normalized_url,
        lock["commit"],
        normalized,
    )
    if lock.get("snapshot_identity_sha256") != expected_identity_digest:
        raise SnapshotError("snapshot lock identity hash mismatch")
    return normalized


def snapshot_files(snapshot_dir: Path) -> list[str]:
    snapshot_fd = open_directory_nofollow(snapshot_dir)
    os.close(snapshot_fd)
    files: list[str] = []
    for path in sorted(snapshot_dir.rglob("*")):
        path_stat = path.lstat()
        if stat.S_ISLNK(path_stat.st_mode):
            raise SnapshotError(
                f"symlink is forbidden in committed snapshot: {path}"
            )
        if stat.S_ISDIR(path_stat.st_mode):
            continue
        if not stat.S_ISREG(path_stat.st_mode):
            raise SnapshotError(f"non-regular snapshot entry is forbidden: {path}")
        relative = path.relative_to(snapshot_dir).as_posix()
        files.append(validate_relative_path(relative, label="snapshot path"))
    return files


def read_snapshot_file_nofollow(
    snapshot_dir: Path,
    entry: dict[str, str],
) -> bytes:
    root_fd = open_directory_nofollow(snapshot_dir)
    current_fd = root_fd
    file_fd: int | None = None
    try:
        parts = PurePosixPath(entry["path"]).parts
        for component in parts[:-1]:
            next_fd = os.open(
                component,
                directory_open_flags(),
                dir_fd=current_fd,
            )
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd

        path_stat = os.stat(
            parts[-1],
            dir_fd=current_fd,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(path_stat.st_mode):
            raise SnapshotError(
                f"snapshot path is not a regular file: {entry['path']}"
            )
        expected_permissions = 0o755 if entry["mode"] == "100755" else 0o644
        if stat.S_IMODE(path_stat.st_mode) != expected_permissions:
            raise SnapshotError(
                f"snapshot mode mismatch: {entry['path']} "
                f"expected {expected_permissions:04o}, "
                f"found {stat.S_IMODE(path_stat.st_mode):04o}"
            )

        file_fd = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=current_fd,
        )
        opened_stat = os.fstat(file_fd)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or file_identity(opened_stat) != file_identity(path_stat)
            or stat.S_IMODE(opened_stat.st_mode) != expected_permissions
        ):
            raise SnapshotError(
                f"snapshot file identity or mode changed: {entry['path']}"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        final_stat = os.fstat(file_fd)
        if (
            file_identity(final_stat) != file_identity(opened_stat)
            or stat.S_IMODE(final_stat.st_mode) != expected_permissions
        ):
            raise SnapshotError(
                f"snapshot file identity or mode changed: {entry['path']}"
            )
        return b"".join(chunks)
    except OSError as exc:
        raise SnapshotError(
            f"snapshot path is missing, unsafe, or symlinked: {entry['path']}"
        ) from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def load_lock_nofollow(lock_path: Path) -> dict[str, Any]:
    absolute = absolute_path(lock_path)
    parent_fd = open_directory_nofollow(absolute.parent)
    try:
        lock_stat = os.stat(
            absolute.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(lock_stat.st_mode):
            raise SnapshotError("snapshot lock path is symlinked")
        flags = os.O_RDONLY | os.O_NOFOLLOW
        file_fd = os.open(absolute.name, flags, dir_fd=parent_fd)
        try:
            file_stat = os.fstat(file_fd)
            if not stat.S_ISREG(file_stat.st_mode):
                raise SnapshotError("snapshot lock must be a regular file")
            with os.fdopen(os.dup(file_fd), encoding="utf-8") as handle:
                value = json.load(handle)
        finally:
            os.close(file_fd)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"snapshot lock is not readable JSON: {exc}") from exc
    finally:
        os.close(parent_fd)
    if not isinstance(value, dict):
        raise SnapshotError("snapshot lock must be a JSON object")
    return value


def validate_snapshot(snapshot_dir: Path, lock_path: Path) -> dict[str, Any]:
    snapshot_dir = absolute_path(snapshot_dir)
    lock_path = absolute_path(lock_path)
    lock = load_lock_nofollow(lock_path)
    entries = validate_lock(lock)
    expected = [entry["path"] for entry in entries]
    actual = snapshot_files(snapshot_dir)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        unknown = sorted(set(actual) - set(expected))
        raise SnapshotError(
            f"snapshot file set mismatch; missing={missing}, unknown={unknown}"
        )
    for entry in entries:
        actual_hash = sha256_bytes(
            read_snapshot_file_nofollow(snapshot_dir, entry)
        )
        if actual_hash != entry["sha256"]:
            raise SnapshotError(f"snapshot hash mismatch: {entry['path']}")
    confirmation_fd = open_directory_nofollow(snapshot_dir)
    os.close(confirmation_fd)
    confirmation_lock = load_lock_nofollow(lock_path)
    if confirmation_lock != lock:
        raise SnapshotError("snapshot lock changed during validation")
    return lock


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--source-repo", type=Path, required=True)
    export_parser.add_argument("--source-ref", required=True)
    export_parser.add_argument("--output-dir", type=Path, required=True)
    export_parser.add_argument("--lock-path", type=Path, required=True)
    export_parser.add_argument("--manifest", type=Path)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--snapshot-dir", type=Path, required=True)
    validate_parser.add_argument("--lock-path", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "export":
            lock = export_snapshot(
                args.source_repo,
                args.source_ref,
                args.output_dir,
                args.lock_path,
                args.manifest,
            )
            print(
                f"Exported {len(lock['included_paths'])} files at {lock['commit']}"
            )
        else:
            lock = validate_snapshot(args.snapshot_dir, args.lock_path)
            print(
                f"Validated {len(lock['included_paths'])} files at {lock['commit']}"
            )
    except SnapshotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
