from __future__ import annotations

import json
from pathlib import Path
import unittest

from src.schemas.validate_trip import validate_trip


ROOT = Path(__file__).resolve().parents[2]
TRIP_PATH = ROOT / "trips/wanhua-2026/trip.json"


class Wanhua2026ConstraintsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trip = json.loads(TRIP_PATH.read_text(encoding="utf-8"))

    def test_trip_is_a_valid_three_day_one_adult_trip(self) -> None:
        validate_trip(self.trip)
        self.assertEqual(self.trip["date_range"], {"start_date": "2026-09-30", "end_date": "2026-10-02"})
        self.assertEqual(self.trip["traveler_profile"], {"adults": 1, "children": []})
        self.assertEqual([day["date"] for day in self.trip["days"]], ["2026-09-30", "2026-10-01", "2026-10-02"])

    def test_lodging_and_ticket_claims_remain_honest(self) -> None:
        hotel = self.trip["candidate_sets"]["hotels"][0]
        self.assertEqual(hotel["price_status"], "unverified")
        self.assertIn("未建立訂單", hotel["provenance"]["note"])
        self.assertEqual(self.trip["budget"]["categories"]["core-tickets"], {"amount": 0, "currency": "TWD"})
        self.assertTrue(any("付費展演" in item.get("notes", "") for day in self.trip["days"] for item in day["items"]))

    def test_core_official_sources_and_metro_cost_are_recorded(self) -> None:
        places = {place["id"]: place for place in self.trip["candidate_sets"]["places"]}
        for place_id in ("bopiliao", "red-house", "longshan-temple", "qizhang-station"):
            self.assertEqual(places[place_id]["provenance"]["source_type"], "official")
            self.assertTrue(places[place_id]["provenance"]["source_url"].startswith("https://"))
        legs = self.trip["candidate_sets"]["transport_legs"]
        self.assertEqual(sum(leg["cost"]["amount"] for leg in legs if leg["mode"] == "train"), 60)
        self.assertEqual(self.trip["budget"]["categories"]["metro"], {"amount": 60, "currency": "TWD"})

    def test_day_one_timing_and_visible_place_notes_agree(self) -> None:
        places = {place["id"]: place for place in self.trip["candidate_sets"]["places"]}
        day_one = {item["id"]: item for item in self.trip["days"][0]["items"]}
        self.assertEqual(day_one["d1-red-house"]["start_at"], "2026-09-30T11:00:00+08:00")
        self.assertIn("安排 11:00 入館", places["red-house"]["opening_hours_note"])
        self.assertEqual(day_one["d1-huazhong-riverside-night-view"]["start_at"], "2026-09-30T19:35:00+08:00")
        self.assertEqual(day_one["d1-huazhong-riverside-night-view"]["end_at"], "2026-09-30T20:45:00+08:00")
        self.assertIn("安排 19:35–20:45", places["huazhong-riverside-park"]["opening_hours_note"])
        self.assertEqual(day_one["d1-ximen-station-to-red-house"]["transport_leg_id"], "ximen-station-to-red-house")


if __name__ == "__main__":
    unittest.main()
