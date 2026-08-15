import json
from pathlib import Path
import unittest

from src.intent import ConstraintCondition, ConstraintScope, RequestConstraint, TimeWindow, parse_trip_request
from src.planner.contracts import HardConstraint, SoftPreference


FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "intent" / "requests.json").read_text())
FIXTURE_BY_NAME = {fixture["name"]: fixture for fixture in FIXTURES}


class TravelIntentParserTests(unittest.TestCase):
    def test_all_chinese_fixtures_parse_without_itinerary_or_research(self):
        self.assertGreaterEqual(len(FIXTURES), 10)
        for fixture in FIXTURES:
            with self.subTest(fixture=fixture["name"]):
                intent = parse_trip_request(fixture["text"])
                self.assertEqual(intent.raw_text, fixture["text"])
                self.assertFalse(hasattr(intent, "days"))
                self.assertFalse(hasattr(intent, "candidate_sets"))
                self.assertFalse(hasattr(intent, "candidate_trips"))
                self.assertFalse(hasattr(intent, "itinerary"))

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

    def test_day_specific_required_and_afternoon_preferred_stay_scoped(self):
        intent = self._parse("day_specific_places")
        first_day, second_day = intent.request_constraints
        self.assertEqual(
            (first_day.kind, first_day.strength, first_day.subject, first_day.scope),
            ("place", "required", "淺草寺", ConstraintScope(day_number=1)),
        )
        self.assertEqual(
            (second_day.kind, second_day.strength, second_day.subject, second_day.scope, second_day.time_window),
            ("place", "preferred", "上野公園", ConstraintScope(day_number=2), TimeWindow(period="afternoon")),
        )
        self.assertNotIn("淺草寺", intent.required_places)
        self.assertNotIn("上野公園", intent.required_places)
        self.assertFalse(any(item.kind == "required_location" and item.value == "淺草寺" for item in intent.hard_constraints))

    def test_ordering_and_after_checkin_are_normalized_in_source_order(self):
        constraints = self._parse("ordering_after_checkin").request_constraints
        self.assertEqual([(item.kind, item.subject, item.relation, item.object) for item in constraints], [
            ("order", "大阪城", "before", "道頓堀"),
            ("order", "環球影城", "after", "hotel_check_in"),
        ])

    def test_explicit_time_window_and_provenance_are_exact(self):
        intent = self._parse("explicit_time_window")
        constraint = intent.request_constraints[0]
        self.assertEqual(constraint.scope, ConstraintScope(day_number=2))
        self.assertEqual(constraint.time_window, TimeWindow(start="14:00", end="16:30"))
        self.assertEqual((constraint.kind, constraint.strength, constraint.subject), ("place", "required", "清水寺"))
        self.assertTrue(constraint.provenance)
        for source in constraint.provenance:
            self.assertEqual(intent.raw_text[source.start:source.end], source.text)

    def test_explicit_date_selector_is_scoped_with_exact_provenance(self):
        intent = self._parse("explicit_date_selector")
        constraint = next(item for item in intent.request_constraints if item.subject == "金閣寺")
        self.assertEqual(constraint.scope, ConstraintScope(date="2027-09-02"))
        self.assertEqual(constraint.time_window, TimeWindow(period="morning"))
        self.assertEqual((constraint.kind, constraint.strength), ("place", "required"))
        self.assertNotIn("金閣寺", intent.required_places)
        self.assertFalse(any(item.kind == "required_location" and item.value == "金閣寺"
                             for item in intent.hard_constraints))
        self.assertTrue(constraint.provenance)
        for source in constraint.provenance:
            self.assertEqual(intent.raw_text[source.start:source.end], source.text)

    def test_daily_start_and_end_boundaries(self):
        constraints = self._parse("daily_boundaries").request_constraints
        self.assertEqual([(item.kind, item.relation, item.time_window) for item in constraints], [
            ("daily_boundary", "start", TimeWindow(start="09:00")),
            ("daily_boundary", "end", TimeWindow(end="20:30")),
        ])

    def test_child_nap_is_a_required_recurring_window(self):
        constraint = next(item for item in self._parse("child_nap").request_constraints if item.kind == "nap")
        self.assertEqual((constraint.kind, constraint.strength, constraint.time_window),
                         ("nap", "required", TimeWindow(start="13:00", end="15:00")))

    def test_meal_window_and_return_deadline_preserve_order(self):
        constraints = tuple(item for item in self._parse("meal_and_return_deadline").request_constraints
                            if item.kind in {"meal", "return_deadline"})
        self.assertEqual([(item.kind, item.time_window) for item in constraints], [
            ("meal", TimeWindow(start="12:00", end="13:00")),
            ("return_deadline", TimeWindow(end="21:00")),
        ])

    def test_last_day_near_airport_is_scoped_not_a_researched_place(self):
        constraint = next(item for item in self._parse("last_day_near_airport").request_constraints
                          if item.kind == "proximity")
        self.assertEqual(
            (constraint.kind, constraint.strength, constraint.subject, constraint.relation, constraint.scope),
            ("proximity", "required", "airport", "near", ConstraintScope(day_selector="last")),
        )

    def test_weather_and_if_time_allows_are_conditional_preferences(self):
        rainy = next(item for item in self._parse("rainy_day_condition").request_constraints if item.condition)
        optional = next(item for item in self._parse("if_time_allows").request_constraints if item.condition)
        self.assertEqual((rainy.kind, rainy.strength, rainy.subject, rainy.condition),
                         ("place", "preferred", "國立科學博物館", ConstraintCondition("weather", "rain")))
        self.assertEqual((optional.kind, optional.strength, optional.subject, optional.condition),
                         ("place", "optional", "錦市場", ConstraintCondition("time_available")))

    def test_contradiction_and_missing_date_are_machine_readable(self):
        contradiction = self._parse("contradictory_strength")
        missing_date = self._parse("missing_date_with_day_reference")
        issue = next(item for item in contradiction.constraint_issues if item.code == "contradictory_strength")
        self.assertEqual(issue.field, "request_constraints")
        self.assertEqual(len(issue.constraint_ids), 2)
        self.assertTrue(issue.text)
        self.assertTrue(issue.reason)
        self.assertIn("missing_trip_date", {item.code for item in missing_date.constraint_issues})

    def test_other_constraint_validation_issues_have_stable_codes(self):
        invalid_window = parse_trip_request("2027/08/01 到 2027/08/03 去東京，第二天 16:00 到 14:00 去上野公園。")
        contradictory_order = parse_trip_request("2027/08/01 到 2027/08/03 去東京，先去淺草寺再去上野公園，也要先去上野公園再去淺草寺。")
        self.assertIn("invalid_time_window", {item.code for item in invalid_window.constraint_issues})
        self.assertIn("contradictory_order", {item.code for item in contradictory_order.constraint_issues})

    def test_constraint_contract_and_json_serialization(self):
        intent = self._parse("day_specific_places")
        self.assertIsInstance(intent.request_constraints[0], RequestConstraint)
        payload = intent.as_dict()
        first_day = next(item for item in payload["request_constraints"] if item["subject"] == "淺草寺")
        second_day = next(item for item in payload["request_constraints"] if item["subject"] == "上野公園")
        self.assertEqual(first_day["scope"]["day_number"], 1)
        self.assertEqual(second_day["time_window"]["period"], "afternoon")
        self.assertEqual(payload["constraint_issues"], [])
        self.assertEqual(json.loads(json.dumps(payload, ensure_ascii=False))["raw_text"], intent.raw_text)

    def _parse(self, name):
        return parse_trip_request(FIXTURE_BY_NAME[name]["text"])


if __name__ == "__main__":
    unittest.main()
