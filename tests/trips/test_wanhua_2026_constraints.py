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
        self.assertEqual(hotel["price_status"], "warning")
        self.assertIn("未建立訂單", hotel["provenance"]["note"])
        self.assertEqual(self.trip["budget"]["categories"]["core-tickets"], {"amount": 0, "currency": "TWD"})
        self.assertEqual(self.trip["selected"]["hotel_place_ids"], [])
        self.assertIn("河景", hotel["room_type"])
        self.assertIn("NT$6,000", hotel["provenance"]["note"])
        self.assertIn("已淘汰", hotel["provenance"]["note"])

    def test_nearby_lodging_leads_do_not_pass_the_river_view_gate(self) -> None:
        hotels = {hotel["place"]["id"]: hotel for hotel in self.trip["candidate_sets"]["hotels"]}
        self.assertFalse(hotels["hotel-wholesome"]["river_view_eligible"])
        self.assertFalse(hotels["hotel-caesar-metro"]["river_view_eligible"])
        self.assertEqual(hotels["hotel-wholesome"]["price_status"], "unverified")
        self.assertEqual(hotels["hotel-caesar-metro"]["price_status"], "unverified")
        self.assertEqual(hotels["hotel-manka"]["provenance"]["source_type"], "user_input")
        self.assertEqual(hotels["hotel-longshan-business"]["provenance"]["source_type"], "user_input")

    def test_core_official_sources_and_metro_cost_are_recorded(self) -> None:
        places = {place["id"]: place for place in self.trip["candidate_sets"]["places"]}
        for place_id in ("bopiliao", "red-house", "longshan-temple", "qizhang-station"):
            self.assertEqual(places[place_id]["provenance"]["source_type"], "official")
            self.assertTrue(places[place_id]["provenance"]["source_url"].startswith("https://"))
        legs = self.trip["candidate_sets"]["transport_legs"]
        self.assertEqual(sum(leg["cost"]["amount"] for leg in legs if leg["mode"] == "train"), 60)
        self.assertEqual(self.trip["budget"]["categories"]["metro"], {"amount": 60, "currency": "TWD"})

    def test_only_evening_leisure_is_scheduled_and_night_safety_is_visible(self) -> None:
        places = {place["id"]: place for place in self.trip["candidate_sets"]["places"]}
        day_one = {item["id"]: item for item in self.trip["days"][0]["items"]}
        leisure = [
            item for day in self.trip["days"][:2] for item in day["items"]
            if item["kind"] in {"visit", "meal"}
        ]
        self.assertTrue(leisure)
        self.assertTrue(all(item["start_at"][11:16] >= "18:00" for item in leisure))
        self.assertEqual(day_one["d1-huazhong-riverside-night-view"]["start_at"], "2026-09-30T18:50:00+08:00")
        self.assertEqual(day_one["d1-huazhong-riverside-night-view"]["end_at"], "2026-09-30T20:00:00+08:00")
        self.assertIn("18:50–20:00", places["huazhong-riverside-park"]["opening_hours_note"])
        self.assertIn("4.0 km", self.trip["candidate_sets"]["hotels"][0]["distance_notes"][-1])
        return_leg = next(leg for leg in self.trip["candidate_sets"]["transport_legs"] if leg["id"] == "huaxi-to-hotel")
        self.assertIn("照明正常", return_leg["provenance"]["note"])


if __name__ == "__main__":
    unittest.main()
