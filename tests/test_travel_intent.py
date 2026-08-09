import json
from pathlib import Path
import unittest

from src.intent import parse_trip_request
from src.planner.contracts import HardConstraint, SoftPreference


FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "intent" / "requests.json").read_text())


class TravelIntentParserTests(unittest.TestCase):
    def test_all_chinese_fixtures_parse_without_itinerary_or_research(self):
        self.assertGreaterEqual(len(FIXTURES), 5)
        for fixture in FIXTURES:
            with self.subTest(fixture=fixture["name"]):
                intent = parse_trip_request(fixture["text"])
                self.assertEqual(intent.raw_text, fixture["text"])
                self.assertFalse(hasattr(intent, "days"))
                self.assertFalse(hasattr(intent, "candidate_sets"))

    def test_japanese_place_dates_child_budget_and_provenance(self):
        intent = parse_trip_request(FIXTURES[0]["text"])
        self.assertEqual(intent.destinations, ("東京", "東京迪士尼"))
        self.assertEqual((intent.start_date, intent.end_date), ("2026-04-01", "2026-04-05"))
        self.assertEqual(intent.travelers.adults, 2)
        self.assertEqual(intent.travelers.children, 1)
        self.assertEqual(intent.travelers.child_ages, (6,))
        self.assertEqual((intent.budget_amount, intent.currency), (80000, "TWD"))
        self.assertEqual(intent.transport, ("transit",))
        self.assertEqual(intent.required_places, ("東京迪士尼",))
        self.assertEqual(intent.soft_preferences, (SoftPreference("low-fatigue", "low_fatigue"),))
        self.assertEqual(intent.provenance["budget"][0].text, "預算8萬台幣")
        self.assertEqual(intent.raw_text[intent.provenance["budget"][0].start:intent.provenance["budget"][0].end], "預算8萬台幣")

    def test_mixed_preferences_map_to_existing_planner_contracts(self):
        intent = parse_trip_request(FIXTURES[1]["text"])
        self.assertEqual((intent.duration_days, intent.duration_nights), (5, 4))
        self.assertEqual(intent.transport, ("drive", "transit", "mixed"))
        self.assertEqual(intent.required_places, ("京都",))
        self.assertEqual(intent.forbidden_places, ("奈良",))
        self.assertIn(HardConstraint("required-京都", "required_location", "京都"), intent.hard_constraints)
        self.assertIn(HardConstraint("forbidden-奈良", "forbidden_location", "奈良"), intent.hard_constraints)
        hard, soft = intent.planner_constraints()
        self.assertEqual(hard, intent.hard_constraints)
        self.assertEqual(soft, intent.soft_preferences)

    def test_missing_fields_are_explicit_not_guessed(self):
        intent = parse_trip_request(FIXTURES[2]["text"])
        self.assertEqual(intent.destinations, ("北海道",))
        self.assertIsNone(intent.duration_days)
        self.assertIsNone(intent.budget_amount)
        self.assertEqual({field.field for field in intent.missing_fields}, {"dates_or_duration", "travelers", "budget"})

    def test_required_and_forbidden_places_and_soft_pace(self):
        intent = parse_trip_request(FIXTURES[4]["text"])
        self.assertEqual(intent.destinations, ("福岡",))
        self.assertEqual(intent.forbidden_places, ("拉麵",))
        self.assertEqual((intent.budget_amount, intent.currency), (50000, "JPY"))
        self.assertEqual(intent.pace, "packed")
        self.assertEqual(intent.soft_preferences, ())

    def test_conflicting_transport_is_marked_ambiguous(self):
        intent = parse_trip_request("東京三天，2大，預算3萬，自駕又搭電車")
        self.assertTrue(any(item.field == "transport" for item in intent.ambiguous_fields))

    def test_rejects_empty_request(self):
        with self.assertRaises(ValueError):
            parse_trip_request("  ")


if __name__ == "__main__":
    unittest.main()
