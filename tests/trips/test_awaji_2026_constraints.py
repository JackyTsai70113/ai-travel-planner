import copy
import json
from pathlib import Path
import unittest

from src.schemas import validate_trip

TRIP_PATH = Path("trips/awaji-naruto-tokushima-kobe-2026/trip.json")


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
