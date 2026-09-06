from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.cli import plan_site_command
from src.request_site import RequestNotReadyError, assert_request_ready, parse_site_request, publish_request_site, required_request_fields


def _trip() -> dict:
    return {
        "id": "nagoya-autumn-2027", "title": "名古屋賞楓 行程", "local_timezone": "Asia/Tokyo",
        "date_range": {"start_date": "2027-10-20", "end_date": "2027-10-22"},
        "traveler_profile": {"adults": 2, "children": [{"age": 7}]},
        "candidate_sets": {
            "places": [{"id": "castle", "name": "名古屋城", "kind": "poi", "maps_query": "名古屋城"}],
            "restaurants": [{"place": {"id": "restaurant", "name": "山本屋", "kind": "restaurant", "maps_query": "山本屋本店"}}],
            "hotels": [{"place": {"id": "hotel", "name": "名古屋飯店", "kind": "hotel"}}],
            "transport_legs": [{"id": "leg-1", "mode": "driving", "from_place_id": "hotel", "to_place_id": "castle", "status": "confirmed", "estimated_duration_minutes": 20}],
        },
        "selected": {"hotel_place_ids": ["hotel"], "flight_ids": []},
        "days": [{"date": "2027-10-20", "summary": "名古屋城與味噌料理", "items": [{"id": "visit", "kind": "visit", "place_id": "castle", "start_at": "2027-10-20T10:00:00+09:00", "end_at": "2027-10-20T12:00:00+09:00"}]}],
        "preferences": {"hard_constraints": [], "soft_preferences": []},
        "budget": {"currency": "JPY", "categories": {"hotel": {"amount": 30000, "currency": "JPY"}}, "total": {"amount": 30000, "currency": "JPY"}},
        "validation": [],
    }


class RequestSiteTests(unittest.TestCase):
    def test_incomplete_month_only_request_is_blocked_without_inventing_dates(self):
        intent = parse_site_request("我要兩個人 10月去名古屋賞楓")
        self.assertEqual(required_request_fields(intent), ["exact_date_range"])
        self.assertEqual(intent.travelers.adults, 2)
        with self.assertRaisesRegex(RequestNotReadyError, "完整起訖日期"):
            assert_request_ready(intent)

    def test_publish_request_site_projects_canonical_trip_and_preserves_existing_registry(self):
        with TemporaryDirectory() as directory:
            public = Path(directory) / "web/public"
            public.mkdir(parents=True)
            (public / "trip-registry.json").write_text(json.dumps([{"slug": "awaji-2026", "title": "既有行程"}]), encoding="utf-8")
            result = publish_request_site(_trip(), slug="nagoya-autumn-2027", public_root=public)
            self.assertEqual(result.canonical_url, "trips/nagoya-autumn-2027")
            self.assertEqual(result.bundle_path, public / "trips/requested/nagoya-autumn-2027/public-bundle.json")
            bundle = json.loads(result.bundle_path.read_text(encoding="utf-8"))
            self.assertEqual(bundle["trip_id"], "nagoya-autumn-2027")
            self.assertEqual(bundle["places"][0]["name"], "名古屋城")
            self.assertEqual(bundle["transport_legs"][0]["from_place"], "hotel")
            registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
            entry = next(item for item in registry if item["slug"] == "nagoya-autumn-2027")
            self.assertEqual(entry["bundle_source_slug"], "requested/nagoya-autumn-2027")
            self.assertEqual(entry["readiness"], "ready")
            self.assertTrue(any(item["slug"] == "awaji-2026" for item in registry))

    def test_publish_request_site_replaces_only_the_same_slug(self):
        with TemporaryDirectory() as directory:
            public = Path(directory) / "web/public"
            public.mkdir(parents=True)
            trip = _trip()
            publish_request_site(trip, slug="nagoya-autumn-2027", public_root=public)
            trip["title"] = "更新後名古屋賞楓 行程"
            publish_request_site(trip, slug="nagoya-autumn-2027", public_root=public)
            registry = json.loads((public / "trip-registry.json").read_text(encoding="utf-8"))
            self.assertEqual([item["slug"] for item in registry].count("nagoya-autumn-2027"), 1)
            self.assertEqual(registry[0]["title"], "更新後名古屋賞楓 行程")

    def test_plan_site_command_runs_production_then_registers_the_generated_site(self):
        test_case = self

        class Runner:
            def run(self, intent):
                test_case.assertEqual(intent.destinations, ("名古屋",))
                test_case.assertEqual(intent.travelers.adults, 2)
                return SimpleNamespace(succeeded=True, trip=_trip(), trip_path=Path("trips/nagoya/trip.json"), warnings=())

        with TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(request="2027/10/20到2027/10/22 台北出發名古屋，兩個人，賞楓", trip_id="nagoya-autumn-2027", site_slug="nagoya-autumn-2027", trips_directory=str(root / "trips"), site_directory=str(root / "site"), public_root=str(root / "web/public"))
            output = io.StringIO()
            with patch("src.cli.missing_required_configuration", return_value=[]), patch("src.cli.create_production_orchestrator", return_value=Runner()), redirect_stdout(output):
                self.assertEqual(plan_site_command(args), 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["status"], "complete")
            self.assertEqual(payload["canonical_url"], "trips/nagoya-autumn-2027")
            self.assertTrue((root / "web/public/trips/requested/nagoya-autumn-2027/public-bundle.json").exists())


if __name__ == "__main__":
    unittest.main()
