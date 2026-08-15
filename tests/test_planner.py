import copy
import json
from datetime import datetime, time, timedelta
from pathlib import Path
import unittest

from src.planner import (
    HardConstraint,
    PlanState,
    PlannerInput,
    ScheduleState,
    SchedulingInput,
    SoftPreference,
    UnverifiedRestaurantHoursPolicy,
    plan,
    schedule,
)
from src.validator import BudgetLimit, OpeningInterval, ValidationContext
from src.conditions import ConditionPolicy, load_condition_snapshot


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

    def test_wednesday_closed_restaurant_is_not_an_acceptable_meal_candidate(self):
        trip = copy.deepcopy(self.trip)
        restaurant = trip["candidate_sets"]["restaurants"][0]
        restaurant["opening_hours"] = {
            "status": "fresh",
            "timezone": "Asia/Tokyo",
            # Monday only.  Wednesday (Python weekday 2) must not be accepted.
            "intervals": [{"weekday": 0, "opens_at": "11:30", "closes_at": "21:00"}],
        }
        trip["days"][4]["date"] = "2026-04-15"
        trip["days"][4]["items"].append({
            "id": "wednesday-meal", "kind": "meal", "place_id": "ramen-shop",
            "start_at": "2026-04-15T12:00:00+09:00", "end_at": "2026-04-15T13:00:00+09:00",
            "selection_status": "selected",
        })
        result = plan(PlannerInput([trip], verified_context()))
        self.assertIsNone(result.best_plan)
        self.assertIn("opening_hours.closed", {item.code for item in result.plans[0].violations})

    def test_split_hours_accepts_only_a_complete_meal_interval(self):
        trip = copy.deepcopy(self.trip)
        restaurant = trip["candidate_sets"]["restaurants"][0]
        restaurant["opening_hours"] = {
            "status": "fresh",
            "timezone": "Asia/Tokyo",
            "intervals": [
                {"weekday": 0, "opens_at": "11:30", "closes_at": "14:00"},
                {"weekday": 0, "opens_at": "17:30", "closes_at": "21:00"},
            ],
        }
        trip["days"][3]["items"].append({
            "id": "monday-dinner", "kind": "meal", "place_id": "ramen-shop",
            "start_at": "2026-04-13T18:00:00+09:00", "end_at": "2026-04-13T19:00:00+09:00",
            "selection_status": "selected",
        })
        result = plan(PlannerInput([trip], verified_context()))
        self.assertIsNotNone(result.best_plan)
        self.assertNotIn("opening_hours.closed", {item.code for item in result.best_plan.violations})

    def test_stale_restaurant_hours_are_unverified_not_assumed_open(self):
        trip = copy.deepcopy(self.trip)
        restaurant = trip["candidate_sets"]["restaurants"][0]
        restaurant["opening_hours"] = {"status": "stale", "timezone": "Asia/Tokyo", "intervals": [{"weekday": 0, "opens_at": "00:00", "closes_at": "23:59"}]}
        trip["days"][3]["items"].append({
            "id": "stale-hours-meal", "kind": "meal", "place_id": "ramen-shop",
            "start_at": "2026-04-13T18:00:00+09:00", "end_at": "2026-04-13T19:00:00+09:00",
            "selection_status": "selected",
        })
        fresh_trip = copy.deepcopy(trip)
        fresh_trip["candidate_sets"]["restaurants"][0]["opening_hours"]["status"] = "fresh"
        result = plan(PlannerInput([trip, fresh_trip], verified_context()))
        self.assertEqual(result.best_plan.trip["candidate_sets"]["restaurants"][0]["opening_hours"]["status"], "fresh")
        stale_plan = next(item for item in result.plans if item.trip["candidate_sets"]["restaurants"][0]["opening_hours"]["status"] == "stale")
        self.assertLess(stale_plan.score, result.best_plan.score)
        self.assertIn("opening_hours.unverified", {item.code for item in stale_plan.violations})

    def test_unverified_restaurant_hours_can_be_configured_as_blocking(self):
        trip = copy.deepcopy(self.trip)
        restaurant = trip["candidate_sets"]["restaurants"][0]
        restaurant["opening_hours"] = {"status": "unverified", "timezone": "Asia/Tokyo", "intervals": []}
        trip["days"][3]["items"].append({
            "id": "unknown-hours-meal", "kind": "meal", "place_id": "ramen-shop",
            "start_at": "2026-04-13T18:00:00+09:00", "end_at": "2026-04-13T19:00:00+09:00",
            "selection_status": "selected",
        })
        result = plan(PlannerInput(
            [trip], verified_context(), max_repair_iterations=0,
            unverified_restaurant_hours_policy=UnverifiedRestaurantHoursPolicy.BLOCK,
        ))
        self.assertIsNone(result.best_plan)
        violation = next(item for item in result.plans[0].violations if item.code == "opening_hours.unverified")
        self.assertEqual(violation.severity, "error")

    def test_scheduler_builds_five_day_route_aware_plan_and_preserves_day_assignments(self):
        trip = copy.deepcopy(self.trip)
        trip["days"] = []
        for index, place in enumerate(trip["candidate_sets"]["places"]):
            if place["id"] in {"tpe", "fuk", "hakata-hotel", "ramen-shop"}:
                continue
            place["schedule"] = {"duration_minutes": 90, "day": index - 2, "required": True, "parking_buffer_minutes": 10, "walking_buffer_minutes": 5}
        restaurant = trip["candidate_sets"]["restaurants"][0]
        restaurant["schedule"] = {"duration_minutes": 60, "day": 2, "required": True}
        context = verified_context()
        routes = dict(context.travel_minutes)
        hours = dict(context.opening_hours)
        hours["ramen-shop"] = [OpeningInterval(weekday, time(8), time(22)) for weekday in range(7)]
        for place_id in ("ohori-park", "dazaifu", "yufuin", "beppu", "canal-city", "ramen-shop"):
            routes[("hakata-hotel", place_id)] = 20
            routes[(place_id, "hakata-hotel")] = 20
        routes[("dazaifu", "ramen-shop")] = 20
        output = schedule(SchedulingInput(trip, ValidationContext(routes, hours, context.budget_limit)))
        candidate = output.best_trip
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.state, ScheduleState.READY)
        self.assertEqual(len(candidate.trip["days"]), 5)
        self.assertEqual(candidate.trip["days"][0]["items"][0]["place_id"], "ohori-park")
        self.assertEqual(candidate.trip["days"][1]["items"][0]["place_id"], "dazaifu")

    def test_scheduler_refuses_closed_or_unknown_operational_facts(self):
        trip = copy.deepcopy(self.trip)
        trip["days"] = []
        trip["candidate_sets"]["places"][3]["schedule"] = {"duration_minutes": 120, "day": 1, "required": True}
        result = schedule(SchedulingInput(trip, ValidationContext()))
        self.assertIsNone(result.best_trip)
        self.assertIn("schedule.route_unknown", {violation.code for violation in result.candidates[0].violations})

    def test_scheduler_keeps_confirmed_reservation_time_unchanged(self):
        trip = copy.deepcopy(self.trip)
        trip["days"] = []
        restaurant = trip["candidate_sets"]["restaurants"][0]
        restaurant["schedule"] = {
            "duration_minutes": 60, "day": 1, "required": True,
            "fixed_start_at": "2026-04-10T12:00:00+09:00", "fixed_end_at": "2026-04-10T13:00:00+09:00",
        }
        hours = {"ramen-shop": [OpeningInterval(weekday, time(8), time(22)) for weekday in range(7)]}
        routes = {("hakata-hotel", "ramen-shop"): 20, ("ramen-shop", "hakata-hotel"): 20}
        candidate = schedule(SchedulingInput(trip, ValidationContext(routes, hours))).best_trip
        self.assertIsNotNone(candidate)
        assert candidate is not None
        item = candidate.trip["days"][0]["items"][0]
        self.assertEqual(item["start_at"], "2026-04-10T12:00:00+09:00")
        self.assertEqual(item["end_at"], "2026-04-10T13:00:00+09:00")

    def test_scheduler_preserves_existing_arrival_and_checkin_anchors(self):
        trip = copy.deepcopy(self.trip)
        trip["candidate_sets"]["places"][3]["schedule"] = {"duration_minutes": 60, "day": 1, "required": True}
        context = verified_context()
        routes = {**context.travel_minutes, ("hakata-hotel", "ohori-park"): 20, ("ohori-park", "hakata-hotel"): 20}
        candidate = schedule(SchedulingInput(trip, ValidationContext(routes, context.opening_hours))).best_trip
        self.assertIsNotNone(candidate)
        assert candidate is not None
        day_one = candidate.trip["days"][0]["items"]
        self.assertEqual([item["id"] for item in day_one[:2]], ["d1-arrival", "d1-checkin"])
        self.assertGreaterEqual(day_one[2]["start_at"], "2026-04-10T15:50:00+09:00")

    def test_weather_soft_penalty_ranks_candidate_without_hard_failure(self):
        context = verified_context()
        context = ValidationContext(
            travel_minutes=context.travel_minutes, opening_hours=context.opening_hours,
            budget_limit=context.budget_limit,
            condition_snapshot=load_condition_snapshot(ROOT / "fixtures/conditions/weather.json"),
            condition_evaluated_at=datetime.fromisoformat("2026-04-10T09:00:00+09:00"),
            condition_policy=ConditionPolicy(max_age=timedelta(days=1)),
        )
        candidate = plan(PlannerInput([self.trip], context)).best_plan
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.score, -3.5)
        self.assertIn("condition.weather.risk", {item.code for item in candidate.violations})

    def test_authoritative_closure_eliminates_candidate(self):
        context = verified_context()
        context = ValidationContext(
            travel_minutes=context.travel_minutes, opening_hours=context.opening_hours,
            budget_limit=context.budget_limit,
            condition_snapshot=load_condition_snapshot(ROOT / "fixtures/conditions/closure.json"),
            condition_evaluated_at=datetime.fromisoformat("2026-04-10T09:00:00+09:00"),
            condition_policy=ConditionPolicy(max_age=timedelta(days=1)),
        )
        result = plan(PlannerInput([self.trip], context))
        self.assertIsNone(result.best_plan)
        self.assertIn("condition.closure.closed", {item.code for item in result.plans[0].violations})


if __name__ == "__main__":
    unittest.main()
