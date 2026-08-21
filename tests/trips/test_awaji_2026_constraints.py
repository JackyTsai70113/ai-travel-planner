import copy
import json
from pathlib import Path
import unittest

from scripts.build_awaji_public_bundle import build_public_bundle
from src.schemas import validate_trip

TRIP_PATH = Path("trips/awaji-naruto-tokushima-kobe-2026/trip.json")
EVIDENCE_PATH = Path("trips/awaji-naruto-tokushima-kobe-2026/evidence.json")
CONDITIONS_PATH = Path("trips/awaji-naruto-tokushima-kobe-2026/conditions.json")


class AwajiTripFixtureTests(unittest.TestCase):
    def setUp(self):
        self.trip = json.loads(TRIP_PATH.read_text(encoding="utf-8"))

    def test_trip_v1_contract(self):
        validate_trip(self.trip)

    def test_trip_date_range(self):
        self.assertEqual(self.trip["date_range"]["start_date"], "2026-08-27")
        self.assertEqual(self.trip["date_range"]["end_date"], "2026-08-31")
        self.assertEqual(len(self.trip["days"]), 5)

    def test_hard_booking_facts(self):
        selected = self.trip["selected"]
        self.assertEqual(selected["flight_ids"], ["xj-834-outbound", "xj-1835-return"])
        self.assertIn("awaji-riverside-hotel", selected["hotel_place_ids"])
        self.assertIn("tokushima-seshi-besso-hotel-2", selected["hotel_place_ids"])
        self.assertIn("royal-park-canvas-kobe-sannomiya", selected["hotel_place_ids"])

        reservation_place = next(place for place in self.trip["candidate_sets"]["places"] if place["id"] == "naruto-ferry-fixed-activity")
        self.assertEqual(reservation_place["resolution"]["state"], "clarification_required")

    def test_fixed_reservation_constraints(self):
        day_two = next(day for day in self.trip["days"] if day["date"] == "2026-08-28")
        fixed = next(item for item in day_two["items"] if item["id"] == "fixed-2026-08-28-17-45")
        self.assertEqual(fixed["start_at"], "2026-08-28T17:45:00+09:00")
        self.assertEqual(fixed["kind"], "visit")
        self.assertEqual(fixed["start_at"], fixed["end_at"])
        self.assertIn("しあわせのパンケーキ", fixed["notes"])
        self.assertIn("地點與持續時間仍待補", fixed["notes"])

    def test_day_five_no_hard_visit(self):
        day_five = next(day for day in self.trip["days"] if day["date"] == "2026-08-31")
        self.assertFalse(any(item.get("kind") == "visit" for item in day_five["items"]))

    def test_scope_visit_uses_awaji_and_naruto_only(self):
        allowed_visit_place_ids = {
            "awaji-nakajima-park",
            "awaji-beach",
            "naruto-whirlpool-viewpoint",
            "naruto-ferry-fixed-activity",
            "awaji-harbor-diner",
        }
        for day in self.trip["days"]:
            for item in day["items"]:
                if item["kind"] == "visit":
                    self.assertIn(item["place_id"], allowed_visit_place_ids)

    def test_no_removed_child_elders_constraints(self):
        serialized = self.trip["preferences"]["hard_constraints"] + self.trip["preferences"]["soft_preferences"]
        payload = " ".join(block["description"] for block in serialized)
        forbidden = ["午睡", "13:00", "13:15", "尿布", "容易入口", "13:00-15:00"]
        for term in forbidden:
            self.assertNotIn(term, payload)

    def test_trip_title_scope(self):
        self.assertEqual(self.trip["title"], "2026 淡路島・鳴門家庭旅行")

    def test_validation_contains_reservation_warning(self):
        self.assertTrue(any(item.get("code") == "RESERVATION_UNCONFIRMED" for item in self.trip["validation"]))

    def test_rewrite_without_fixed_slot_breaks_validation(self):
        mutated = copy.deepcopy(self.trip)
        day_two = next(day for day in mutated["days"] if day["date"] == "2026-08-28")
        fixed = next(item for item in day_two["items"] if item["id"] == "fixed-2026-08-28-17-45")
        fixed["id"] = "day2-visit-1745"
        with self.assertRaises(AssertionError):
            self.assertTrue(any(item["id"] == "fixed-2026-08-28-17-45" for item in day_two["items"]))

    def test_flight_arrival_aware_and_unknown_output(self):
        outbound = next(flight for flight in self.trip["candidate_sets"]["flights"] if flight["id"] == "xj-834-outbound")
        inbound = next(flight for flight in self.trip["candidate_sets"]["flights"] if flight["id"] == "xj-1835-return")
        self.assertIn("notes", outbound)
        self.assertIn("notes", inbound)
        self.assertEqual(outbound["arrival"]["at"], "2026-08-27T10:30:00+09:00")
        self.assertEqual(inbound["departure"]["at"], "2026-08-31T12:45:00+09:00")

    def test_flight_carrier_and_unknown_time_precision_are_distinct(self):
        outbound = next(flight for flight in self.trip["candidate_sets"]["flights"] if flight["id"] == "xj-834-outbound")
        inbound = next(flight for flight in self.trip["candidate_sets"]["flights"] if flight["id"] == "xj-1835-return")
        self.assertEqual(outbound["carrier"], "Starlux")
        self.assertIsNone(outbound["departure"]["at"])
        self.assertEqual(inbound["arrival"]["at"], None)

    def test_no_invalid_source_domains_in_trip_payload(self):
        payload_text = TRIP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("example.invalid", payload_text)
        self.assertNotIn("airline.example.invalid", payload_text)
        self.assertNotIn("github.com/your-org", payload_text)

    def test_public_bundle_evidence_gate_tracks_critical_issues(self):
        trip = json.loads(TRIP_PATH.read_text(encoding="utf-8"))
        bundle = build_public_bundle(trip, TRIP_PATH)
        self.assertIn("evidence_gate", bundle)
        self.assertIn(bundle["evidence_gate"]["status"], {"ok", "error"})
        self.assertIsInstance(bundle["evidence_gate"]["critical_issues"], list)

    def test_selected_facts_have_tracked_evidence(self):
        evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        required_ids = {
            *(
                f"selected-flight/{flight_id}"
                for flight_id in self.trip["selected"]["flight_ids"]
            ),
            *(
                f"selected-hotel/{hotel_id}"
                for hotel_id in self.trip["selected"]["hotel_place_ids"]
            ),
        }
        evidence_ids = set(entry.get("reference_id") for entry in evidence.get("entries", []))
        evidence_ids = set(entry.get("reference_id") for entry in evidence.get("entries", []))
        missing = sorted(required_ids - evidence_ids)
        self.assertEqual(missing, [])

    def test_conditions_include_visibility_and_validity_interval(self):
        conditions = json.loads(CONDITIONS_PATH.read_text(encoding="utf-8"))
        self.assertIn("conditions", conditions)
        for condition in conditions["conditions"]:
            self.assertIn("visibility", condition)
            self.assertIn("official_source", condition)
            self.assertIn("validity", condition)
            self.assertIn("supporting_sources", condition)
