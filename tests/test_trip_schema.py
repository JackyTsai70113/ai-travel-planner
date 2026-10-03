import copy
import json
from pathlib import Path
import unittest

from src.schemas import TripValidationError, validate_trip

TRIP = Path(__file__).parents[1] / "fixtures/trips/japan-5-day-trip-v1.json"
WANHUA = Path(__file__).parents[1] / "trips/wanhua-2026/trip.json"


class NightViewEvidenceSchemaTests(unittest.TestCase):
    def setUp(self):
        self.trip = json.loads(TRIP.read_text(encoding="utf-8"))

    def _evidence(self):
        source = {"source_type": "official", "provider": "Official Park Guide", "source_url": "https://example.test/park", "retrieved_at": "2026-09-01T10:00:00+09:00", "status": "confirmed"}
        fact = lambda status, description: {"status": status, "description": description, "provenance": source}
        point = {"id": "river-entrance", "kind": "entrance", "name": "Viewing deck entrance", "google_maps_url": "https://maps.google.com/?q=river-entrance", "provenance": source}
        return {"observation_point": fact("confirmed", "Riverside viewing deck"), "river_visibility": fact("visible", "River visible from the deck after dusk"), "obstructions": fact("clear", "Sightline has no tree obstruction"), "night_scene": fact("visible", "Bridge lights visible after dusk"), "access_point": {"status": "confirmed", "description": "Viewing deck entrance confirmed", "provenance": source, "navigation_point": point}, "retrieved_at": "2026-09-01T10:00:00+09:00"}

    def test_transport_leg_and_segments_are_runtime_validated(self):
        leg = {"id": "transit-leg", "mode": "mixed", "from_place_id": "origin", "to_place_id": "destination", "departure_at": "2026-04-10T18:00:00+09:00", "arrival_at": "2026-04-10T18:45:00+09:00", "verification_status": "confirmed", "wait_seconds": 120, "transfer_count": 1, "segments": [{"mode": "walk", "departure_at": "2026-04-10T18:00:00+09:00", "arrival_at": "2026-04-10T18:05:00+09:00"}, {"mode": "train", "departure_at": "2026-04-10T18:07:00+09:00", "arrival_at": "2026-04-10T18:45:00+09:00", "line_name": "Airport Line"}]}
        self.trip["candidate_sets"]["transport_legs"].append(leg)
        validate_trip(self.trip)
        invalids = [
            {**leg, "unexpected": True},
            {**leg, "mode": "scooter"},
            {**leg, "mode": []},
            {**leg, "verification_status": []},
            {**leg, "wait_seconds": True},
            {**leg, "cost": "n/a"},
            {**leg, "arrival_at": "2026-04-10T17:59:00+09:00"},
            {**leg, "segments": [{"mode": "train", "departure_at": leg["departure_at"], "arrival_at": leg["arrival_at"], "extra": 1}]},
            {**leg, "segments": [{"mode": "airplane", "departure_at": leg["departure_at"], "arrival_at": leg["arrival_at"]}]},
            {**leg, "segments": [{"mode": [], "departure_at": leg["departure_at"], "arrival_at": leg["arrival_at"]}]},
            {**leg, "segments": [{"mode": "walk", "departure_at": leg["departure_at"], "arrival_at": "2026-04-10T18:30:00+09:00"}, {"mode": "train", "departure_at": "2026-04-10T18:20:00+09:00", "arrival_at": leg["arrival_at"]}]},
            {**leg, "segments": [{"mode": "train", "departure_at": "2026-04-10T18:01:00+09:00", "arrival_at": leg["arrival_at"]}]},
        ]
        for invalid in invalids:
            with self.subTest(invalid=invalid):
                self.trip["candidate_sets"]["transport_legs"] = [invalid]
                with self.assertRaises(TripValidationError):
                    validate_trip(self.trip)

    def test_restaurant_schedule_and_alternatives_reject_unknown_fields(self):
        restaurant = self.trip["candidate_sets"]["restaurants"][0]
        restaurant["schedule"] = {"duration_minutes": 60, "parking_buffer_minutes": 5, "selection_reason": "已驗證營業時間與路線", "alternatives": [{"place_id": "backup", "meal_period": "lunch", "day": 1, "hours_verified": True, "route_verified": True}]}
        backup = copy.deepcopy(restaurant)
        backup["place"]["id"] = "backup"
        backup.pop("schedule")
        self.trip["candidate_sets"]["restaurants"].append(backup)
        restaurant["field_provenance"] = {"price_range": [{"source_type": "official", "provider": "Restaurant", "source_url": "https://example.test/menu", "retrieved_at": "2026-09-01T10:00:00+09:00", "status": "confirmed"}]}
        validate_trip(self.trip)
        restaurant["schedule"]["unexpected"] = True
        with self.assertRaises(TripValidationError):
            validate_trip(self.trip)
        restaurant["schedule"].pop("unexpected")
        restaurant["schedule"]["alternatives"][0]["unexpected"] = True
        with self.assertRaises(TripValidationError):
            validate_trip(self.trip)
        restaurant["schedule"]["alternatives"][0].pop("unexpected")
        restaurant["schedule"]["alternatives"][0]["place_id"] = "missing-backup"
        with self.assertRaises(TripValidationError):
            validate_trip(self.trip)

    def test_night_view_evidence_and_requirement_trace_are_valid(self):
        self.trip["days"][0]["items"][0]["satisfies_constraints"] = ["night-river-view"]
        place_id = self.trip["days"][0]["items"][0]["place_id"]
        place = next(candidate for candidate in self.trip["candidate_sets"]["places"] if candidate["id"] == place_id)
        place["night_view_evidence"] = self._evidence()
        self.trip["preferences"]["hard_constraints"].append({"id": "night-river-view", "kind": "night_river_view", "description": "晚上看得到河流與夜景", "value": {"after": "18:00", "river_visibility": "visible", "obstructions": "clear", "night_scene": "visible"}})
        validate_trip(self.trip)

    def test_night_view_fact_requires_provenance(self):
        self.trip["candidate_sets"]["places"][0]["night_view_evidence"] = self._evidence()
        self.trip["candidate_sets"]["places"][0]["night_view_evidence"]["river_visibility"].pop("provenance")
        with self.assertRaises(TripValidationError):
            validate_trip(self.trip)

    def test_night_view_navigation_point_matches_canonical_navigation_point_contract(self):
        place = self.trip["candidate_sets"]["places"][0]
        place["night_view_evidence"] = self._evidence()
        point = place["night_view_evidence"]["access_point"]["navigation_point"]
        for invalid_point in ("entrance", {"kind": "entrance", "google_maps_url": ""}, {"id": "bad id", "kind": "entrance", "mapcode": "A"}):
            with self.subTest(invalid_point=invalid_point):
                place["night_view_evidence"]["access_point"]["navigation_point"] = invalid_point
                with self.assertRaises(TripValidationError):
                    validate_trip(self.trip)
        place["night_view_evidence"]["access_point"]["navigation_point"] = point

    def test_night_view_navigation_point_rejects_malformed_uri(self):
        place = self.trip["candidate_sets"]["places"][0]
        place["night_view_evidence"] = self._evidence()
        for url in ("https://", "https://example.com:bad"):
            with self.subTest(url=url):
                place["night_view_evidence"]["access_point"]["navigation_point"]["google_maps_url"] = url
                with self.assertRaises(TripValidationError):
                    validate_trip(self.trip)

    def test_night_view_fact_status_must_match_fact_semantics(self):
        place = self.trip["candidate_sets"]["places"][0]
        place["night_view_evidence"] = self._evidence()
        place["night_view_evidence"]["river_visibility"]["status"] = "clear"
        with self.assertRaises(TripValidationError):
            validate_trip(self.trip)

    def test_satisfies_constraints_rejects_duplicate_ids(self):
        item = self.trip["days"][0]["items"][0]
        item["satisfies_constraints"] = ["must-visit", "must-visit"]
        self.trip["preferences"]["hard_constraints"] = [{"id": "must-visit", "kind": "required_location", "description": "Visit the selected attraction", "value": "sample"}]
        with self.assertRaises(TripValidationError):
            validate_trip(self.trip)

    def test_wanhua_night_view_is_explicitly_unknown_and_does_not_require_a_river_view_hotel(self):
        trip = json.loads(WANHUA.read_text(encoding="utf-8"))
        validate_trip(trip)
        park = next(place for place in trip["candidate_sets"]["places"] if place["id"] == "huazhong-riverside-park")
        evidence = park["night_view_evidence"]
        self.assertEqual(evidence["river_visibility"]["status"], "unknown")
        self.assertEqual(evidence["obstructions"]["status"], "unknown")
        self.assertEqual(evidence["night_scene"]["status"], "unknown")
        self.assertEqual(evidence["access_point"]["status"], "unknown")
        self.assertFalse(any(item["id"] == "river-view-stay-budget" for item in trip["preferences"]["hard_constraints"]))
        self.assertFalse(any("satisfies_constraints" in item for day in trip["days"] for item in day["items"]))


if __name__ == "__main__":
    unittest.main()
