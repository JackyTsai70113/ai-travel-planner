from __future__ import annotations

import base64
import json
import unittest
from pathlib import Path

from src.mcp_server.github_pages import (
    GitHubPagesPublisher,
    GitHubPublishError,
    PublishResult,
)
from src.google_places_storage import durable_trip
from src.request_site import trip_publication_findings, trip_to_public_bundle, trip_to_registry_entry

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
        for index, day in enumerate(self.trip["days"], start=1):
            day["items"].append({
                "id": f"lunch-day-{index}", "kind": "meal", "place_id": "ramen-shop",
                "start_at": f"{day['date']}T12:00:00+09:00", "end_at": f"{day['date']}T13:00:00+09:00",
                "selection_status": "selected",
            })

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

    def test_unselected_google_poi_warning_is_visible_but_does_not_block_publication(self):
        trip = json.loads(json.dumps(self.trip))
        place = trip["candidate_sets"]["places"][0]
        place["google_place_id"] = "ChIJ-unselected"
        place["provenance"] = {"source_type": "provider", "provider": "Google Places API (New)"}
        trip["validation"] = [{
            "code": "schedule.poi_candidate_unselected", "severity": "warning",
            "message": f"候選景點「{place['name']}」未排入：未能驗證所需的營業時間或路線。",
            "path": f"/candidate_sets/places/{place['id']}/schedule",
        }]
        stored = durable_trip(trip)
        self.assertEqual([], trip_publication_findings(stored))
        entry = trip_to_registry_entry(stored, slug="demo-trip", source_slug="requested/demo-trip")
        self.assertEqual("incomplete", entry["readiness"])

        fake = FakeGitHub()
        result = self.publisher(fake).publish(trip, slug="demo-trip")
        self.assertEqual("publish_accepted", result.status)
        blobs = [json.loads(base64.b64decode(call[2]["content"])) for call in fake.calls if call[0] == "POST" and call[1].endswith("/git/blobs")]
        bundle = next(value for value in blobs if value.get("trip_id") == trip["id"])
        self.assertEqual("schedule.poi_candidate_unselected", bundle["validation"][0]["code"])
        self.assertIn("Google Places 候選未排入", bundle["validation"][0]["message"])
        self.assertNotIn(place["name"], json.dumps(bundle, ensure_ascii=False))

    def test_incomplete_trip_can_publish_only_as_an_incomplete_preview(self):
        trip = json.loads(json.dumps(self.trip))
        trip["budget"]["total_status"] = "incomplete"
        trip["validation"] = [
            {"code": "meal.period_unselected", "severity": "warning", "message": "尚有餐段未安排", "path": "/days/0"},
            {"code": "budget.incomplete", "severity": "warning", "message": "費用尚未完整估算", "path": "/budget"},
        ]
        fake = FakeGitHub()

        result = self.publisher(fake).publish(trip, slug="demo-trip")

        self.assertEqual("publish_accepted", result.status)
        blobs = [json.loads(base64.b64decode(call[2]["content"])) for call in fake.calls if call[0] == "POST" and call[1].endswith("/git/blobs")]
        bundle = next(value for value in blobs if value.get("trip_id") == trip["id"])
        registry = next(value for value in blobs if isinstance(value, list))
        self.assertEqual("warning", bundle["status"])
        self.assertEqual("preview", registry[0]["status"])
        self.assertEqual("incomplete", registry[0]["readiness"])
        self.assertEqual({"meal.period_unselected", "budget.incomplete"}, {item["code"] for item in bundle["validation"]})

    def test_publication_strips_google_places_details_but_preserves_place_ids(self):
        trip = json.loads(json.dumps(self.trip))
        trip["candidate_sets"]["places"][0]["provenance"] = {
            "source_type": "provider", "provider": "Google Places API (New)",
            "retrieved_at": "2026-10-08T00:00:00+00:00", "status": "confirmed",
        }
        fake = FakeGitHub()

        trip["candidate_sets"]["places"][0]["google_place_id"] = "ChIJ-place"
        result = self.publisher(fake).publish(trip, slug="demo-trip")
        self.assertEqual("publish_accepted", result.status)
        bundle_calls = [call for call in fake.calls if "public-bundle.json" in str(call)]
        self.assertTrue(bundle_calls)
        self.assertNotIn("Dazaifu", json.dumps(bundle_calls, ensure_ascii=False))

    def test_publication_strips_google_sourced_field_when_candidate_has_other_source(self):
        trip = json.loads(json.dumps(self.trip))
        place = trip["candidate_sets"]["places"][0]
        place["provenance"] = {
            "source_type": "official", "provider": "Nagoya City",
            "retrieved_at": "2026-10-08T00:00:00+00:00", "status": "confirmed",
        }
        place["field_provenance"] = {
            "name": [{
                "source_type": "provider", "provider": "Google Places API (New)",
                "retrieved_at": "2026-10-08T00:00:00+00:00", "status": "confirmed",
            }],
        }
        place["name"] = "Google Field Name"
        fake = FakeGitHub()

        trip["candidate_sets"]["places"][0]["google_place_id"] = "ChIJ-place"
        self.publisher(fake).publish(trip, slug="demo-trip")
        blobs = [json.loads(base64.b64decode(call[2]["content"])) for call in fake.calls if call[0] == "POST" and call[1].endswith("/git/blobs")]
        writes = json.dumps(blobs, ensure_ascii=False)
        self.assertNotIn("Google Field Name", writes)
        self.assertIn("ChIJ-place", writes)

    def test_allows_overnight_trip_without_lodging(self):
        trip = json.loads(json.dumps(self.trip))
        trip["selected"]["hotel_place_ids"] = []
        trip["validation"] = [{
            "code": "schedule.hotel_missing", "severity": "warning",
            "message": "lodging was not supplied", "path": "/selected/hotel_place_ids",
        }]
        fake = FakeGitHub()
        result = self.publisher(fake).publish(trip, slug="demo-trip")
        self.assertEqual(result.status, "publish_accepted")

    def test_refuses_selected_lodging_not_found_in_hotel_candidates(self):
        trip = json.loads(json.dumps(self.trip))
        trip["selected"]["hotel_place_ids"] = ["ghost-hotel"]
        fake = FakeGitHub()
        with self.assertRaisesRegex(ValueError, "selected lodging does not match a hotel candidate"):
            self.publisher(fake).publish(trip, slug="demo-trip")
        self.assertEqual(fake.calls, [])

    def test_refuses_day_without_scheduled_meal(self):
        trip = json.loads(json.dumps(self.trip))
        trip["days"][2]["items"] = [item for item in trip["days"][2]["items"] if item["kind"] != "meal"]
        fake = FakeGitHub()
        with self.assertRaisesRegex(ValueError, "day 3 has no scheduled meal"):
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

    def test_idempotent_publish_requires_bundle_and_registry_to_match(self):
        bundle = trip_to_public_bundle(self.trip)
        entry = trip_to_registry_entry(self.trip, slug="demo-trip", source_slug="requested/demo-trip")
        fake = FakeGitHub(registry=[entry], bundle=bundle)

        result = self.publisher(fake).publish(self.trip, slug="demo-trip")

        self.assertEqual(result.status, "already_published")
        self.assertFalse(any(call[0] in {"POST", "PATCH"} for call in fake.calls))

    def test_same_bundle_with_missing_registry_entry_repairs_the_registry(self):
        fake = FakeGitHub(bundle=trip_to_public_bundle(self.trip))

        result = self.publisher(fake).publish(self.trip, slug="demo-trip")

        self.assertEqual(result.status, "publish_accepted")
        self.assertEqual([item["path"] for item in fake.tree["tree"]], ["web/public/trip-registry.json"])

    def test_same_bundle_with_stale_registry_entry_repairs_metadata(self):
        entry = trip_to_registry_entry(self.trip, slug="demo-trip", source_slug="requested/demo-trip")
        entry["title"] = "舊標題"
        fake = FakeGitHub(registry=[entry], bundle=trip_to_public_bundle(self.trip))

        result = self.publisher(fake).publish(self.trip, slug="demo-trip")

        self.assertEqual(result.status, "publish_accepted")
        self.assertEqual([item["path"] for item in fake.tree["tree"]], ["web/public/trip-registry.json"])


if __name__ == "__main__":
    unittest.main()
