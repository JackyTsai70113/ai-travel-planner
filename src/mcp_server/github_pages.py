"""Publish an explicitly confirmed Canonical Trip to this repository's Pages site."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import re
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from src.request_site import trip_publication_findings, trip_to_public_bundle, trip_to_registry_entry
from src.schemas.validate_trip import validate_trip


_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")
_REGISTRY_PATH = "web/public/trip-registry.json"


class GitHubPublishError(RuntimeError):
    """A sanitized GitHub publishing failure safe to return through MCP."""

    def __init__(self, status_code: int | None, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PublishResult:
    status: str
    repository: str
    slug: str
    url: str
    commit_sha: str | None = None
    deployment_status: str = "pending"


class GitHubPagesPublisher:
    """Create one atomic Git commit containing a public bundle and registry update."""

    def __init__(
        self,
        *,
        token: str,
        repository: str,
        branch: str = "main",
        pages_base_url: str | None = None,
        api_url: str = "https://api.github.com",
        request_json: Callable[..., Mapping[str, Any]] | None = None,
    ) -> None:
        if not token:
            raise ValueError("GitHub token is required")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("repository must use owner/name format")
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
            raise ValueError("branch contains unsupported characters")
        self.token = token
        self.owner, self.name = repository.split("/", 1)
        self.repository = repository
        self.branch = branch
        self.api_url = api_url.rstrip("/")
        self.pages_base_url = (pages_base_url or f"https://{self.owner.lower()}.github.io/{self.name}").rstrip("/")
        if not self.pages_base_url.startswith("https://"):
            raise ValueError("Pages base URL must use HTTPS")
        self.request_json = request_json or _request_json

    def publish(self, trip: Mapping[str, Any], *, slug: str, confirm_overwrite: bool = False) -> PublishResult:
        if not _SLUG.fullmatch(slug):
            raise ValueError("site slug must use lowercase letters, digits, and hyphens")
        validate_trip(dict(trip))
        bundle = trip_to_public_bundle(trip)
        findings = trip_publication_findings(trip)
        entry = trip_to_registry_entry(trip, slug=slug, source_slug=f"requested/{slug}")
        if entry["readiness"] != "ready":
            details = "; ".join(findings) or "Canonical Trip is not ready"
            raise ValueError(f"trip is not ready for public publication: {details}")

        ref = self._request("GET", f"git/ref/heads/{quote(self.branch, safe='')}")
        parent_sha = _required_text(ref.get("object", {}).get("sha"), "branch commit")
        parent = self._request("GET", f"git/commits/{parent_sha}")
        base_tree = _required_text(parent.get("tree", {}).get("sha"), "branch tree")
        registry_file = self._get_contents(_REGISTRY_PATH, parent_sha)
        _, registry_bytes = registry_file
        try:
            registry = json.loads(registry_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubPublishError(None, "GitHub Pages trip registry is not valid JSON") from exc
        if not isinstance(registry, list):
            raise GitHubPublishError(None, "GitHub Pages trip registry has an invalid format")

        bundle_path = f"web/public/trips/requested/{slug}/public-bundle.json"
        source_slug = f"requested/{slug}"
        existing_entry = next((item for item in registry if isinstance(item, dict) and item.get("slug") == slug), None)
        if existing_entry is not None and existing_entry.get("bundle_source_slug") != source_slug:
            raise GitHubPublishError(409, "site slug is already assigned to another Pages source")
        existing_file = self._get_contents_optional(bundle_path, parent_sha)
        bundle_is_current = False
        if existing_file is not None:
            _, existing_bytes = existing_file
            try:
                existing_bundle = json.loads(existing_bytes)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise GitHubPublishError(None, "existing public trip bundle is not valid JSON") from exc
            if not isinstance(existing_bundle, dict):
                raise GitHubPublishError(None, "existing public trip bundle has an invalid format")
            if existing_bundle.get("trip_id") != trip.get("id"):
                raise GitHubPublishError(409, "site slug is already used by a different trip")
            bundle_is_current = _same_public_bundle(existing_bundle, bundle)
            if not bundle_is_current and not confirm_overwrite:
                raise GitHubPublishError(409, "this trip already has a public site; call again with confirm_overwrite=true to replace it")
        elif existing_entry is not None:
            raise GitHubPublishError(409, "registry entry exists but its public bundle is missing")

        if bundle_is_current and existing_entry is not None and _same_registry_entry(existing_entry, entry):
            return PublishResult("already_published", self.repository, slug, self._url(slug), None, "not_required")

        registry = [item for item in registry if not (isinstance(item, dict) and item.get("slug") == slug)]
        registry.append(entry)
        changes = [(_REGISTRY_PATH, _json_bytes(registry))]
        if not bundle_is_current:
            changes.insert(0, (bundle_path, _json_bytes(bundle)))
        tree = []
        for path, content in changes:
            blob = self._request("POST", "git/blobs", {"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"})
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": _required_text(blob.get("sha"), "Git blob")})
        created_tree = self._request("POST", "git/trees", {"base_tree": base_tree, "tree": tree})
        tree_sha = _required_text(created_tree.get("sha"), "Git tree")
        commit = self._request("POST", "git/commits", {
            "message": f"Publish travel itinerary: {slug}",
            "tree": tree_sha,
            "parents": [parent_sha],
        })
        commit_sha = _required_text(commit.get("sha"), "Git commit")
        self._request("PATCH", f"git/refs/heads/{quote(self.branch, safe='')}", {"sha": commit_sha, "force": False})
        return PublishResult("publish_accepted", self.repository, slug, self._url(slug), commit_sha, "pending")

    def _url(self, slug: str) -> str:
        return f"{self.pages_base_url}/trips/{slug}/"

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        try:
            return self.request_json(
                method,
                f"{self.api_url}/repos/{self.repository}/{path.lstrip('/')}",
                self.token,
                payload,
            )
        except GitHubPublishError:
            raise
        except Exception as exc:
            raise GitHubPublishError(None, "GitHub API request failed; verify connectivity and repository permissions") from exc

    def _get_contents_optional(self, path: str, ref: str) -> tuple[str, bytes] | None:
        try:
            result = self._request("GET", f"contents/{quote(path, safe='/')}?ref={quote(ref, safe='')}")
        except GitHubPublishError as exc:
            if exc.status_code == 404:
                return None
            raise
        return _decode_content(result)

    def _get_contents(self, path: str, ref: str) -> tuple[str, bytes]:
        result = self._get_contents_optional(path, ref)
        if result is None:
            raise GitHubPublishError(404, "required GitHub Pages trip registry was not found")
        return result


def _decode_content(value: Mapping[str, Any]) -> tuple[str, bytes]:
    if value.get("encoding") != "base64" or not isinstance(value.get("content"), str):
        raise GitHubPublishError(None, "GitHub content response is incomplete")
    try:
        content = base64.b64decode(value["content"], validate=False)
    except (ValueError, TypeError) as exc:
        raise GitHubPublishError(None, "GitHub content response is malformed") from exc
    return _required_text(value.get("sha"), "file blob"), content


def _same_public_bundle(existing: Any, proposed: Mapping[str, Any]) -> bool:
    if not isinstance(existing, dict):
        return False
    existing = json.loads(json.dumps(existing))
    candidate = json.loads(json.dumps(proposed))
    for value in (existing, candidate):
        meta = value.get("meta")
        if isinstance(meta, dict):
            meta.pop("generated_at", None)
    return existing == candidate


def _same_registry_entry(existing: Any, proposed: Mapping[str, Any]) -> bool:
    if not isinstance(existing, dict):
        return False
    existing = json.loads(json.dumps(existing))
    candidate = json.loads(json.dumps(proposed))
    for value in (existing, candidate):
        value.pop("last_generated", None)
        value.pop("last_verified", None)
    return existing == candidate


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise GitHubPublishError(None, f"GitHub API omitted {label}")
    return value


def _request_json(method: str, url: str, token: str, payload: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ai-travel-planner-mcp",
        **({"Content-Type": "application/json"} if body is not None else {}),
    })
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
    except HTTPError as exc:
        # Do not return GitHub's error body; it can contain request or repo data.
        raise GitHubPublishError(exc.code, f"GitHub API rejected the publishing request (HTTP {exc.code})") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise GitHubPublishError(None, "GitHub API is unavailable; retry after connectivity is restored") from exc
    if not isinstance(result, Mapping):
        raise GitHubPublishError(None, "GitHub API returned an invalid response")
    return result
