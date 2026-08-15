import copy
import json
from datetime import datetime, time, timedelta
from pathlib import Path
import unittest

from src.validator import BudgetLimit, OpeningInterval, Outcome, RuleRegistry, ValidationContext, validate_itinerary
from src.conditions import ConditionPolicy, load_condition_snapshot


FIXTURE = Path(__file__).parents[1] / "fixtures/trips/japan-5-day-trip-v1.json"


def verified_context() -> ValidationContext:
    hours = {}
    for place_id in ("ohori-park", "dazaifu", "yufuin", "beppu", "canal-city"):
        hours[place_id] = [OpeningInterval(weekday, time(8), time(22)) for weekday in range(7)]
    return ValidationContext(
        travel_minutes={
            ("fuk", "hakata-hotel"): 180,
            ("yufuin", "beppu"): 60,
        },
        opening_hours=hours,
        budget_limit=BudgetLimit(200000, "JPY"),
    )


class ItineraryValidatorTests(unittest.TestCase):
    def setUp(self):
        self.trip = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_complete_fixture_passes(self):
        result = validate_itinerary(self.trip, verified_context())
        self.assertEqual(result.outcome, Outcome.VALID)
        self.assertEqual(result.violations, ())
        self.assertEqual(result.as_dict(), {"outcome": "valid", "violations": []})

    def test_overlap_and_insufficient_travel_fail(self):
        trip = copy.deepcopy(self.trip)
        trip["days"][3]["items"][1]["start_at"] = "2026-04-13T11:30:00+09:00"
        result = validate_itinerary(trip, verified_context())
        self.assertEqual(result.outcome, Outcome.INVALID)
        self.assertEqual({item.code for item in result.violations}, {"time.overlap", "travel_time.insufficient"})

    def test_closed_and_over_budget_fail(self):
        context = verified_context()
        context = ValidationContext(
            travel_minutes=context.travel_minutes,
            opening_hours={**context.opening_hours, "ohori-park": [OpeningInterval(5, time(8), time(9))]},
            budget_limit=BudgetLimit(100000, "JPY"),
        )
        result = validate_itinerary(self.trip, context)
        self.assertEqual(result.outcome, Outcome.INVALID)
        self.assertEqual({item.code for item in result.violations}, {"opening_hours.closed", "budget.exceeded"})

    def test_unknown_derived_facts_are_incomplete(self):
        result = validate_itinerary(self.trip)
        self.assertEqual(result.outcome, Outcome.INCOMPLETE)
        self.assertIn("travel_time.unverified", {item.code for item in result.violations})
        self.assertIn("opening_hours.unverified", {item.code for item in result.violations})

    def test_registry_accepts_extension(self):
        registry = RuleRegistry()
        registry.register(lambda trip, context: [])
        self.assertEqual(validate_itinerary(self.trip, registry=registry).outcome, Outcome.VALID)

    def test_tide_window_violation_prevents_finalization(self):
        context = verified_context()
        snapshot = load_condition_snapshot(Path(__file__).parents[1] / "fixtures/conditions/tide.json")
        trip = copy.deepcopy(self.trip)
        trip["days"][1]["items"][0]["end_at"] = "2026-04-11T13:00:00+09:00"
        context = ValidationContext(
            travel_minutes=context.travel_minutes, opening_hours=context.opening_hours,
            budget_limit=context.budget_limit, condition_snapshot=snapshot,
            condition_evaluated_at=datetime.fromisoformat("2026-04-10T09:00:00+09:00"),
            condition_policy=ConditionPolicy(max_age=timedelta(days=1)),
        )
        result = validate_itinerary(trip, context)
        self.assertEqual(result.outcome, Outcome.INVALID)
        self.assertIn("condition.tide.outside_window", {item.code for item in result.violations})

    def test_condition_snapshot_without_evaluated_at_is_unverified(self):
        context = verified_context()
        context = ValidationContext(
            travel_minutes=context.travel_minutes, opening_hours=context.opening_hours,
            budget_limit=context.budget_limit,
            condition_snapshot=load_condition_snapshot(Path(__file__).parents[1] / "fixtures/conditions/weather.json"),
        )
        result = validate_itinerary(self.trip, context)
        self.assertEqual(result.outcome, Outcome.INCOMPLETE)
        self.assertIn("condition.unverified", {item.code for item in result.violations})


if __name__ == "__main__":
    unittest.main()
