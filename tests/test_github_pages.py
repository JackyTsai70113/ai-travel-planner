from __future__ import annotations

import base64
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from src.mcp_server.github_pages import GitHubPagesPublisher, GitHubPublishError, PublishResult
from src.request_site import trip_to_public_bundle


FIXTURE = Path(__file__).parents[1] / "fixtures/trips/japan-5-day-trip-v1.json"


class FakeGitHub:
    def __init__(self, registry=None, bundle=None):
        self.registry = registry if registry is not None else []
        self.bundle = bundle
        self.calls = []
        self.blob_count = 0

    def __call__(self, method, url, token, payload=None):
        assert token == "private-token"
        self.calls.append((method, url, payload))
        if method == "GET" and url.endswith("/git/ref/heads/main"):
            return {"object": {"sha": "parent-sha"}}
        if method == "GET" and url.endswith("/git/commits/parent-sha"):
            return {"tree": {"sha": "base-tree"}}
        if method == "GET" and "/contents/web/public/trip-registry.json?" in url:
            return self._contents("registry-sha", self.registry)
        if method == "GET" and "/contents/web/public/trips/requested/demo-trip/public-bundle.json?" in url:
            if self.bundle is None:
                raise GitHubPublishError(404, "not found")
            return self._contents("existing-bundle-sha", self.bundle)
        if method == "POST" and url.endswith("/git/blobs"):
            self.blob_count += 1
            return {"sha": f"blob-{self.blob_count}"}
        if method == "POST" and url.endswith("/git/trees"):
            self.tree = payload
            return {"sha": "new-tree"}
        if method == "POST" and url.endswith("/git/commits"):
            self.commit = payload
            return {"sha": "new-commit"}
        if method == "PATCH" and url.endswith("/git/refs/heads/main"):
            self.ref_update = payload
            return {"object": {"sha": payload["sha"]}}
        raise AssertionError(f"unexpected GitHub request: {method} {url}")

    @staticmethod
    def _contents(sha, value):
        content = json.dumps(value, ensure_ascii=False).encode("utf-8")
        return {"sha": sha, "encoding": "base64", "content": base64.b64encode(content).decode("ascii")}


class GitHubPagesPublisherTests(unittest.TestCase):
    def setUp(self):
        self.trip = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def publisher(self, fake):
        return GitHubPagesPublisher(
            token="private-token",
            repository="JackyTsai70113/ai-travel-planner",
            request_json=fake,
        )

    def test_publish_atomically_writes_allowlisted_bundle_and_registry(self):
        fake = FakeGitHub()

        result = self.publisher(fake).publish(self.trip, slug="demo-trip")

        self.assertEqual(result, PublishResult(
            "publish_accepted", "JackyTsai70113/ai-travel-planner", "demo-trip",
            "https://jackytsai70113.github.io/ai-travel-planner/trips/demo-trip/", "new-commit", "pending",
        ))
        self.assertEqual([item["path"] for item in fake.tree["tree"]], [
            "web/public/trips/requested/demo-trip/public-bundle.json",
            "web/public/trip-registry.json",
        ])
        self.assertEqual(fake.commit["parents"], ["parent-sha"])
        self.assertEqual(fake.ref_update, {"sha": "new-commit", "force": False})
        self.assertEqual(len([call for call in fake.calls if call[0] == "PATCH"]), 1)

    def test_rejects_invalid_slug_before_github_writes(self):
        fake = FakeGitHub()
        with self.assertRaises(ValueError):
            self.publisher(fake).publish(self.trip, slug="../private")
        self.assertEqual(fake.calls, [])

    def test_refuses_trip_with_validation_findings(self):
        trip = {**self.trip, "validation": [{
            "code": "lodging.missing", "severity": "warning", "message": "lodging unavailable", "path": "/candidate_sets/hotels",
        }]}
        fake = FakeGitHub()
        with self.assertRaisesRegex(ValueError, "not ready for public publication"):
            self.publisher(fake).publish(trip, slug="demo-trip")
        self.assertEqual(fake.calls, [])

    def test_rejects_slug_collision_with_a_different_trip(self):
        fake = FakeGitHub(bundle={"trip_id": "someone-elses-trip"})
        with self.assertRaisesRegex(GitHubPublishError, "different trip"):
            self.publisher(fake).publish(self.trip, slug="demo-trip")
        self.assertFalse(any(call[0] in {"POST", "PATCH"} for call in fake.calls))

    def test_existing_same_trip_requires_explicit_overwrite_when_changed(self):
        existing = trip_to_public_bundle(self.trip)
        existing["title"] = "Old public title"
        fake = FakeGitHub(bundle=existing)
        with self.assertRaisesRegex(GitHubPublishError, "confirm_overwrite=true"):
            self.publisher(fake).publish(self.trip, slug="demo-trip")
        self.assertFalse(any(call[0] in {"POST", "PATCH"} for call in fake.calls))

    def test_overwrite_same_trip_only_when_explicitly_confirmed(self):
        existing = trip_to_public_bundle(self.trip)
        existing["title"] = "Old public title"
        fake = FakeGitHub(bundle=existing)

        result = self.publisher(fake).publish(self.trip, slug="demo-trip", confirm_overwrite=True)

        self.assertEqual(result.status, "publish_accepted")
        self.assertEqual(fake.ref_update["force"], False)


if __name__ == "__main__":
    unittest.main()
