import copy
import json
from datetime import time
from pathlib import Path
import unittest

from src.planner import HardConstraint, PlanState, PlannerInput, SoftPreference, plan
from src.validator import BudgetLimit, OpeningInterval, ValidationContext


ROOT = Path(__file__).parents[1]
TRIP_FIXTURE = ROOT / "fixtures/trips/japan-5-day-trip-v1.json"
SCENARIOS = ROOT / "tests/fixtures/planner"


def verified_context(limit=200000):
    hours = {
        place_id: [OpeningInterval(weekday, time(8), time(22)) for weekday in range(7)]
        for place_id in ("ohori-park", "dazaifu", "yufuin", "beppu", "canal-city")
    }
    return ValidationContext(
        travel_minutes={("fuk", "hakata-hotel"): 180, ("yufuin", "beppu"): 60},
        opening_hours=hours,
        budget_limit=BudgetLimit(limit, "JPY"),
    )


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.trip = json.loads(TRIP_FIXTURE.read_text(encoding="utf-8"))

    def _scenario(self, name):
        return json.loads((SCENARIOS / f"{name}.json").read_text(encoding="utf-8"))

    def test_normal_fixture_is_ready_and_ranked_by_soft_preference(self):
        scenario = self._scenario("normal")
        result = plan(PlannerInput([self.trip], verified_context(), soft_preferences=[SoftPreference("low-fatigue", "low_fatigue")]))
        candidate = result.best_plan
        self.assertEqual(candidate.state.value, scenario["expected_state"])
        self.assertLess(candidate.score, 0)
        self.assertEqual(candidate.violations, ())

    def test_time_conflict_fixture_repairs_only_violating_item_and_revalidates(self):
        scenario = self._scenario("time-conflict")
        trip = copy.deepcopy(self.trip)
        item = trip["days"][3]["items"][1]
        item["start_at"] = scenario["start_at"]
        result = plan(PlannerInput([trip], verified_context(), max_repair_iterations=2))
        candidate = result.best_plan
        repaired = candidate.trip["days"][3]["items"][1]
        self.assertEqual(candidate.state.value, scenario["expected_state"])
        self.assertEqual(candidate.repair_iterations, 1)
        self.assertEqual(repaired["start_at"], "2026-04-13T13:00:00+09:00")
        self.assertEqual(repaired["end_at"], "2026-04-13T17:30:00+09:00")
        self.assertEqual(candidate.violations, ())

    def test_strict_budget_fixture_returns_explicit_failure(self):
        scenario = self._scenario("strict-budget")
        result = plan(PlannerInput([self.trip], verified_context(scenario["limit"])))
        candidate = result.plans[0]
        self.assertEqual(candidate.state.value, scenario["expected_state"])
        self.assertIsNone(result.best_plan)
        self.assertIn("budget.exceeded", {violation.code for violation in candidate.violations})

    def test_hard_constraints_precede_soft_scoring(self):
        constraints = [
            HardConstraint("must-visit", "required_location", "ohori-park"),
            HardConstraint("no-shopping", "forbidden_location", "canal-city"),
        ]
        result = plan(PlannerInput([self.trip], verified_context(), hard_constraints=constraints))
        self.assertEqual(result.plans[0].state, PlanState.FAILED)
        self.assertIn("constraint.forbidden_location", {v.code for v in result.plans[0].violations})

    def test_preserved_override_wins_over_candidate_mutation(self):
        trip = copy.deepcopy(self.trip)
        trip["selected"]["hotel_place_ids"] = []
        result = plan(PlannerInput([trip], verified_context()))
        self.assertEqual(result.best_plan.trip["selected"]["hotel_place_ids"], ["hakata-hotel"])

    def test_fixed_and_daily_duration_constraints_are_checked(self):
        constraints = [
            HardConstraint("arrival", "fixed_time", {"item_id": "d1-arrival", "start_at": "2026-04-10T11:00:00+09:00", "end_at": "2026-04-10T12:00:00+09:00"}),
            HardConstraint("short-day", "max_daily_duration", 30),
        ]
        result = plan(PlannerInput([self.trip], verified_context(), hard_constraints=constraints))
        self.assertEqual(result.plans[0].state, PlanState.FAILED)
        self.assertEqual({v.code for v in result.plans[0].violations}, {"constraint.fixed_time", "constraint.max_daily_duration"})


if __name__ == "__main__":
    unittest.main()
