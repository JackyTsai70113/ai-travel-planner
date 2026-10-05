import copy
import json
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import unittest
from types import SimpleNamespace
from zoneinfo import ZoneInfo

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
from src.planner.scheduler import _add_elapsed_minutes, _anchors, _in_trip_timezone, _is_open
from src.validator import BudgetLimit, OpeningInterval, ValidationContext
from src.conditions import ConditionPolicy, ConditionSnapshot, ConditionStatus, load_condition_snapshot


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

    def test_scheduler_sequence_opening_hours_use_trip_timezone_and_fail_closed_on_malformed_values(self):
        request = SimpleNamespace(
            trip={"local_timezone": "Asia/Tokyo"},
            validation_context=ValidationContext(opening_hours={"night-poi": [OpeningInterval(6, time(9), time(11))]}),
        )
        start = datetime.fromisoformat("2026-11-01T00:30:00+00:00")
        end = datetime.fromisoformat("2026-11-01T01:30:00+00:00")

        self.assertTrue(_is_open("night-poi", start, end, request))

        self.assertFalse(_is_open("night-poi", datetime.fromisoformat("2026-11-01T09:30:00"), datetime.fromisoformat("2026-11-01T10:30:00"), request))

        for invalid_offset in (True, 1.5, 2):
            invalid_interval = SimpleNamespace(weekday=6, opens_at=time(9), closes_at=time(11), closes_day_offset=invalid_offset)
            invalid_request = SimpleNamespace(trip={"local_timezone": "Asia/Tokyo"}, validation_context=ValidationContext(opening_hours={"night-poi": [invalid_interval]}))
            self.assertFalse(_is_open("night-poi", start, end, invalid_request))

        malformed = SimpleNamespace(
            trip={"local_timezone": "Asia/Tokyo"},
            validation_context=ValidationContext(opening_hours={"night-poi": [{"weekday": 6, "opens_at": "bad", "closes_at": "bad"}]}),
        )
        self.assertFalse(_is_open("night-poi", start, end, malformed))
        malformed.trip["local_timezone"] = "not/a-real-zone"
        self.assertFalse(_is_open("night-poi", start, end, malformed))
        for malformed_interval in (
            {"weekday": 6, "opens_at": "bad", "closes_at": "bad"},
            {"weekday": True, "opens_at": "09:00", "closes_at": "11:00"},
            {"weekday": 6, "opens_at": "09:00", "closes_at": "11:00", "closes_day_offset": True},
            {"weekday": 6, "opens_at": "09:00", "closes_at": "11:00", "closes_day_offset": 1.5},
        ):
            bad_snapshot = SimpleNamespace(
                trip={"local_timezone": "Asia/Tokyo"},
                validation_context=ValidationContext(opening_hours={"night-poi": {
                    "status": "fresh", "timezone": "Asia/Tokyo", "intervals": [malformed_interval],
                }}),
            )
            self.assertFalse(_is_open("night-poi", start, end, bad_snapshot))

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

    def test_night_river_view_requires_confirmed_facts_and_evening_visit(self):
        from src.planner.planner import _hard_constraint_violations, _record_constraint_satisfaction

        source = {"source_type": "official", "provider": "Official Park Guide", "source_url": "https://example.test/park", "retrieved_at": "2026-09-01T10:00:00+08:00", "status": "confirmed"}
        fact = lambda status, description: {"status": status, "description": description, "provenance": source}
        evidence = {"observation_point": fact("confirmed", "Riverside viewing deck"),
                    "river_visibility": fact("visible", "River visible from the deck at night"),
                    "obstructions": fact("clear", "No tree canopy blocks the sightline"),
                    "night_scene": fact("visible", "Bridge lights visible after dusk"),
                    "access_point": {"status": "confirmed", "description": "Entrance verified", "provenance": source,
                                     "navigation_point": {"id": "river-entrance", "kind": "entrance", "google_maps_url": "https://maps.google.com/?q=river-entrance", "provenance": source}},
                    "retrieved_at": "2026-09-01T10:00:00+08:00"}
        trip = {"local_timezone": "Asia/Taipei", "candidate_sets": {"places": [{"id": "river-park", "night_view_evidence": evidence}]},
                "days": [{"items": [{"kind": "visit", "place_id": "river-park", "start_at": "2026-10-01T19:00:00+08:00", "end_at": "2026-10-01T20:00:00+08:00"}]}]}
        constraint = HardConstraint("night-river-view", "night_river_view", {"after": "18:00"})

        self.assertEqual(_hard_constraint_violations(trip, [constraint]), [])
        _record_constraint_satisfaction(trip, [constraint])
        self.assertEqual(trip["days"][0]["items"][0]["satisfies_constraints"], ["night-river-view"])
        trip["days"][0]["items"].append({"kind": "visit", "place_id": "other-place", "start_at": "2026-10-01T20:00:00+08:00", "end_at": "2026-10-01T21:00:00+08:00", "satisfies_constraints": ["night-river-view", "other-constraint"]})
        _record_constraint_satisfaction(trip, [constraint])
        self.assertEqual(trip["days"][0]["items"][0]["satisfies_constraints"], ["night-river-view"])
        self.assertEqual(trip["days"][0]["items"][1]["satisfies_constraints"], ["other-constraint"])
        _record_constraint_satisfaction(trip, [constraint])
        self.assertEqual(trip["days"][0]["items"][0]["satisfies_constraints"], ["night-river-view"])
        unknown = copy.deepcopy(trip)
        unknown["candidate_sets"]["places"][0]["night_view_evidence"]["river_visibility"]["status"] = "unknown"
        self.assertTrue(_hard_constraint_violations(unknown, [constraint]))
        daylight = copy.deepcopy(trip)
        daylight["days"][0]["items"][0]["start_at"] = "2026-10-01T17:00:00+08:00"
        self.assertTrue(_hard_constraint_violations(daylight, [constraint]))
        daylight["days"][0]["items"][0]["start_at"] = "2026-10-01T19:00:00+00:00"
        self.assertTrue(_hard_constraint_violations(daylight, [constraint]))

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
        trip["date_range"] = {"start_date": "2026-04-10", "end_date": "2026-04-14"}
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

    def test_scheduler_uses_elapsed_time_across_dst_fold(self):
        trip = copy.deepcopy(self.trip)
        trip["days"] = [{"date": "2026-11-01", "items": [{
            "id": "fold-anchor", "kind": "event", "place_id": "anchor-station",
            "start_at": "2026-11-01T01:30:00-04:00", "end_at": "2026-11-01T01:50:00-04:00",
        }]}]
        trip["date_range"] = {"start_date": "2026-11-01", "end_date": "2026-11-01"}
        trip["local_timezone"] = "America/New_York"
        poi = next(place for place in trip["candidate_sets"]["places"] if place["id"] == "ohori-park")
        poi["schedule"] = {"duration_minutes": 15, "day": 1, "required": True}
        for place in trip["candidate_sets"]["places"]:
            if place["id"] != "ohori-park":
                place["schedule"] = {"selected": False}
        for meal in trip["candidate_sets"]["restaurants"]:
            meal["schedule"] = {"selected": False}
        context = ValidationContext(
            travel_minutes={("anchor-station", "ohori-park"): 30, ("ohori-park", "hakata-hotel"): 0},
            opening_hours={"ohori-park": [OpeningInterval(6, time(1), time(2))]},
        )

        result = schedule(SchedulingInput(trip, context, daily_start="00:00", daily_end="23:00"))

        self.assertIsNotNone(result.best_trip)
        assert result.best_trip is not None
        visit = next(item for item in result.best_trip.trip["days"][0]["items"] if item["place_id"] == "ohori-park")
        self.assertEqual(visit["start_at"], "2026-11-01T01:20:00-05:00")
        self.assertEqual(visit["end_at"], "2026-11-01T01:35:00-05:00")
        self.assertEqual(
            (datetime.fromisoformat(visit["end_at"]).astimezone(timezone.utc)
             - datetime.fromisoformat(visit["start_at"]).astimezone(timezone.utc)).total_seconds(),
            900,
        )

    def test_scheduler_orders_immutable_anchors_by_absolute_time_across_dst_fold(self):
        trip = {"days": [{"date": "2026-11-01", "items": [
            {"kind": "event", "place_id": "first", "start_at": "2026-11-01T01:45:00-04:00", "end_at": "2026-11-01T01:50:00-04:00"},
            {"kind": "event", "place_id": "second", "start_at": "2026-11-01T01:15:00-05:00", "end_at": "2026-11-01T01:20:00-05:00"},
        ]}]}
        violations = []

        anchors = _anchors(trip, violations)

        self.assertEqual(violations, [])
        self.assertEqual([item["place_id"] for item in anchors["2026-11-01"]], ["first", "second"])

    def test_scheduler_converts_parsed_prior_item_to_trip_zone_before_elapsed_route(self):
        zone = ZoneInfo("America/New_York")
        previous_end = _in_trip_timezone("2026-11-01T01:50:00-04:00", zone)

        arrival = _add_elapsed_minutes(previous_end, 30)

        self.assertEqual(arrival.isoformat(), "2026-11-01T01:20:00-05:00")

    def test_unroutable_optional_meal_is_skipped_without_failing_required_schedule(self):
        trip = copy.deepcopy(self.trip)
        poi = next(place for place in trip["candidate_sets"]["places"] if place["id"] == "ohori-park")
        poi["schedule"] = {"duration_minutes": 90, "day": 1, "required": True}
        restaurant = trip["candidate_sets"]["restaurants"][0]
        restaurant["schedule"] = {"duration_minutes": 60, "day": 1, "meal_period": "lunch", "required": False}
        routes = {("hakata-hotel", poi["id"]): 15, (poi["id"], "hakata-hotel"): 15}
        hours = {poi["id"]: tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7))}
        result = schedule(SchedulingInput(trip, ValidationContext(routes, hours)))
        self.assertIsNotNone(result.best_trip)
        self.assertNotIn("meal", {item["kind"] for item in result.best_trip.trip["days"][0]["items"]})
        self.assertIn("meal.route_unknown", {item.code for item in result.best_trip.violations})

    def test_optional_meal_without_hotel_return_route_does_not_fail_day(self):
        trip = copy.deepcopy(self.trip)
        poi = next(place for place in trip["candidate_sets"]["places"] if place["id"] == "ohori-park")
        poi["schedule"] = {"duration_minutes": 90, "day": 1, "required": True}
        restaurant = trip["candidate_sets"]["restaurants"][0]
        restaurant["schedule"] = {"duration_minutes": 60, "day": 1, "meal_period": "lunch", "required": False}
        routes = {("hakata-hotel", poi["id"]): 15, (poi["id"], restaurant["place"]["id"]): 15, (poi["id"], "hakata-hotel"): 15}
        hours = {poi["id"]: tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7)), restaurant["place"]["id"]: tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7))}
        result = schedule(SchedulingInput(trip, ValidationContext(routes, hours)))
        self.assertIsNotNone(result.best_trip)
        self.assertNotIn("meal", {item["kind"] for item in result.best_trip.trip["days"][0]["items"]})
        self.assertIn("meal.hotel_return_unverified", {item.code for item in result.best_trip.violations})

    def test_optional_meal_uses_verified_alternative_when_primary_is_closed(self):
        trip = copy.deepcopy(self.trip)
        trip["days"] = []
        trip["date_range"] = {"start_date": "2026-04-10", "end_date": "2026-04-10"}
        trip["selected"]["hotel_place_ids"] = ["hakata-hotel"]
        poi = next(place for place in trip["candidate_sets"]["places"] if place["id"] == "ohori-park")
        poi["schedule"] = {"duration_minutes": 60, "day": 1, "required": True}
        trip["candidate_sets"]["places"] = [poi]
        primary = copy.deepcopy(trip["candidate_sets"]["restaurants"][0])
        primary["place"]["id"] = "primary-meal"
        primary["schedule"] = {"duration_minutes": 60, "day": 1, "meal_period": "lunch", "required": False,
                               "fixed_start_at": "2026-04-10T12:30:00+09:00", "fixed_end_at": "2026-04-10T13:30:00+09:00",
                               "selected": True, "alternatives": [{"place_id": "backup-meal", "meal_period": "lunch", "day": 1, "hours_verified": True, "route_verified": True}]}
        backup = copy.deepcopy(primary)
        backup["place"]["id"] = "backup-meal"
        backup["schedule"] = {**primary["schedule"], "selected": False}
        trip["candidate_sets"]["restaurants"] = [primary, backup]
        hotel = "hakata-hotel"
        routes = {(hotel, poi["id"]): 10, (poi["id"], "primary-meal"): 10, (poi["id"], "backup-meal"): 10,
                  ("backup-meal", hotel): 10, (poi["id"], hotel): 10}
        hours = {poi["id"]: tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7)),
                 "primary-meal": tuple(OpeningInterval(day, time(0), time(0)) for day in range(7)),
                 "backup-meal": tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7))}
        result = schedule(SchedulingInput(trip, ValidationContext(routes, hours)))
        assert result.best_trip is not None
        meals = [item["place_id"] for item in result.best_trip.trip["days"][0]["items"] if item["kind"] == "meal"]
        self.assertEqual(["backup-meal"], meals)
        self.assertNotIn("meal.closed_or_unverified", {item.code for item in result.best_trip.violations})

    def test_optional_meal_uses_alternative_when_primary_fixed_end_does_not_fit(self):
        trip = copy.deepcopy(self.trip)
        trip["days"] = []
        trip["date_range"] = {"start_date": "2026-04-10", "end_date": "2026-04-10"}
        poi = next(place for place in trip["candidate_sets"]["places"] if place["id"] == "ohori-park")
        poi["schedule"] = {"duration_minutes": 60, "day": 1, "required": True}
        trip["candidate_sets"]["places"] = [poi]
        primary = copy.deepcopy(self.trip["candidate_sets"]["restaurants"][0])
        primary["place"]["id"] = "primary-meal"
        primary["schedule"] = {"duration_minutes": 60, "day": 1, "meal_period": "lunch", "required": False,
                               "fixed_start_at": "2026-04-10T12:30:00+09:00", "fixed_end_at": "2026-04-10T13:00:00+09:00",
                               "selected": True, "alternatives": [{"place_id": "backup-meal", "meal_period": "lunch", "day": 1, "hours_verified": True, "route_verified": True}]}
        backup = copy.deepcopy(primary)
        backup["place"]["id"] = "backup-meal"
        backup["schedule"] = {"duration_minutes": 45, "fixed_end_at": "2026-04-10T13:15:00+09:00", "selected": False}
        trip["candidate_sets"]["restaurants"] = [primary, backup]
        hotel = "hakata-hotel"
        routes = {(hotel, poi["id"]): 10, (poi["id"], "primary-meal"): 10, (poi["id"], "backup-meal"): 10,
                  ("primary-meal", hotel): 10, ("backup-meal", hotel): 10, (poi["id"], hotel): 10}
        hours = {poi["id"]: tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7)),
                 "primary-meal": tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7)),
                 "backup-meal": tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7))}
        result = schedule(SchedulingInput(trip, ValidationContext(routes, hours)))
        assert result.best_trip is not None
        meals = [item["place_id"] for item in result.best_trip.trip["days"][0]["items"] if item["kind"] == "meal"]
        self.assertEqual(["backup-meal"], meals)
        self.assertFalse(result.best_trip.trip["candidate_sets"]["restaurants"][0]["schedule"]["selected"])
        self.assertTrue(result.best_trip.trip["candidate_sets"]["restaurants"][1]["schedule"]["selected"])
        self.assertIn("午餐安排", result.best_trip.trip["candidate_sets"]["restaurants"][1]["schedule"]["selection_reason"])

    def test_scheduler_ignores_alternatives_without_matching_verification(self):
        from src.planner.scheduler import _activities

        trip = copy.deepcopy(self.trip)
        primary = trip["candidate_sets"]["restaurants"][0]
        primary["schedule"] = {"duration_minutes": 60, "day": 1, "meal_period": "lunch", "selected": True,
                               "alternatives": [
                                   {"place_id": "unverified-backup", "meal_period": "lunch", "day": 1, "hours_verified": False, "route_verified": True},
                                   {"place_id": "wrong-slot-backup", "meal_period": "dinner", "day": 1, "hours_verified": True, "route_verified": True},
                               ]}
        backups = []
        for place_id in ("unverified-backup", "wrong-slot-backup"):
            backup = copy.deepcopy(primary)
            backup["place"]["id"] = place_id
            backup["schedule"] = {"duration_minutes": 60, "selected": False}
            backups.append(backup)
        trip["candidate_sets"]["restaurants"] = [primary, *backups]
        activities = _activities(trip, [])
        self.assertNotIn("unverified-backup", {activity["id"] for activity in activities})
        self.assertNotIn("wrong-slot-backup", {activity["id"] for activity in activities})

    def test_optional_meal_uses_alternative_when_primary_return_route_is_missing(self):
        trip = copy.deepcopy(self.trip)
        trip["days"] = []
        trip["date_range"] = {"start_date": "2026-04-10", "end_date": "2026-04-10"}
        poi = next(place for place in trip["candidate_sets"]["places"] if place["id"] == "ohori-park")
        poi["schedule"] = {"duration_minutes": 60, "day": 1, "required": True}
        trip["candidate_sets"]["places"] = [poi]
        trip["candidate_sets"]["restaurants"] = []
        primary = copy.deepcopy(self.trip["candidate_sets"]["restaurants"][0])
        primary["place"]["id"] = "primary-meal"
        primary["schedule"] = {"duration_minutes": 60, "day": 1, "meal_period": "lunch", "required": False,
                               "fixed_start_at": "2026-04-10T12:30:00+09:00", "fixed_end_at": "2026-04-10T13:30:00+09:00",
                               "selected": True, "alternatives": [{"place_id": "backup-meal", "meal_period": "lunch", "day": 1, "hours_verified": True, "route_verified": True}]}
        backup = copy.deepcopy(primary)
        backup["place"]["id"] = "backup-meal"
        backup["schedule"] = {**primary["schedule"], "selected": False}
        trip["candidate_sets"]["restaurants"] = [primary, backup]
        hotel = "hakata-hotel"
        routes = {(hotel, poi["id"]): 10, (poi["id"], "primary-meal"): 10, (poi["id"], "backup-meal"): 10,
                  ("backup-meal", hotel): 10, (poi["id"], hotel): 10}
        hours = {poi["id"]: tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7)),
                 "primary-meal": tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7)),
                 "backup-meal": tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7))}
        result = schedule(SchedulingInput(trip, ValidationContext(routes, hours)))
        assert result.best_trip is not None
        meals = [item["place_id"] for item in result.best_trip.trip["days"][0]["items"] if item["kind"] == "meal"]
        self.assertEqual(["backup-meal"], meals)
        self.assertFalse(result.best_trip.trip["candidate_sets"]["restaurants"][0]["schedule"]["selected"])
        self.assertTrue(result.best_trip.trip["candidate_sets"]["restaurants"][1]["schedule"]["selected"])

    def test_same_restaurant_alternative_is_used_at_most_once_across_trip(self):
        trip = copy.deepcopy(self.trip)
        trip["days"] = []
        trip["date_range"] = {"start_date": "2026-04-10", "end_date": "2026-04-11"}
        pois = [place for place in trip["candidate_sets"]["places"] if place["id"] in {"ohori-park", "dazaifu"}]
        trip["candidate_sets"]["places"] = pois
        for day, poi in enumerate(pois, start=1):
            poi["schedule"] = {"duration_minutes": 60, "day": day, "required": True}
        trip["candidate_sets"]["restaurants"] = []
        primary_meals = []
        for day in (1, 2):
            primary = copy.deepcopy(self.trip["candidate_sets"]["restaurants"][0])
            primary_id = f"primary-{day}"
            meal_date = f"2026-04-{9 + day}"
            primary["place"]["id"] = primary_id
            primary["schedule"] = {"duration_minutes": 60, "day": day, "meal_period": "lunch", "required": False,
                                   "fixed_start_at": f"{meal_date}T12:30:00+09:00", "fixed_end_at": f"{meal_date}T13:30:00+09:00",
                                   "selected": True, "alternatives": [{"place_id": "shared-backup", "meal_period": "lunch", "day": day, "hours_verified": True, "route_verified": True}]}
            primary_meals.append(primary)
        backup = copy.deepcopy(primary_meals[0])
        backup["place"]["id"] = "shared-backup"
        backup["schedule"] = {"duration_minutes": 60, "selected": False}
        trip["candidate_sets"]["restaurants"] = [*primary_meals, backup]
        hotel = "hakata-hotel"
        routes = {}
        hours = {"shared-backup": tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7))}
        for day, poi in enumerate(pois, start=1):
            routes[(hotel, poi["id"])] = routes[(poi["id"], hotel)] = 10
            routes[(poi["id"], f"primary-{day}")] = routes[(poi["id"], "shared-backup")] = 10
            hours[poi["id"]] = tuple(OpeningInterval(weekday, time(0), time(23, 59)) for weekday in range(7))
            hours[f"primary-{day}"] = tuple(OpeningInterval(weekday, time(0), time(0)) for weekday in range(7))
        routes[("shared-backup", hotel)] = 10
        result = schedule(SchedulingInput(trip, ValidationContext(routes, hours)))
        assert result.best_trip is not None
        scheduled = [[item["place_id"] for item in day["items"] if item["kind"] == "meal"]
                     for day in result.best_trip.trip["days"]]
        self.assertEqual([["shared-backup"], []], scheduled)
        self.assertEqual(1, sum(place_id == "shared-backup" for day in scheduled for place_id in day))

    def test_return_fallback_removes_each_trailing_meal_until_last_route_is_verified(self):
        trip = copy.deepcopy(self.trip)
        trip["days"] = []
        poi = next(place for place in trip["candidate_sets"]["places"] if place["id"] == "ohori-park")
        poi["schedule"] = {"duration_minutes": 60, "day": 1, "required": True}
        source = trip["candidate_sets"]["restaurants"][0]
        lunch = copy.deepcopy(source)
        dinner = copy.deepcopy(source)
        lunch["place"]["id"] = "lunch-shop"
        dinner["place"]["id"] = "dinner-shop"
        lunch["schedule"] = {"duration_minutes": 45, "day": 1, "required": False, "meal_period": "lunch"}
        dinner["schedule"] = {"duration_minutes": 45, "day": 1, "required": False, "meal_period": "dinner"}
        trip["candidate_sets"]["restaurants"] = [lunch, dinner]
        hotel = "hakata-hotel"
        routes = {(hotel, poi["id"]): 5, (poi["id"], hotel): 5, (poi["id"], "lunch-shop"): 5,
                  ("lunch-shop", "dinner-shop"): 5}
        hours = {poi["id"]: tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7)),
                 "lunch-shop": tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7)),
                 "dinner-shop": tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7))}
        result = schedule(SchedulingInput(trip, ValidationContext(routes, hours)))
        assert result.best_trip is not None
        self.assertEqual(["visit"], [item["kind"] for item in result.best_trip.trip["days"][0]["items"]])
        self.assertEqual(2, sum(item.code == "meal.hotel_return_unverified" for item in result.best_trip.violations))

    def test_three_day_plan_keeps_breakfast_lunch_dinner_in_verified_windows(self):
        trip = copy.deepcopy(self.trip)
        trip["days"] = []
        trip["date_range"] = {"start_date": "2026-04-10", "end_date": "2026-04-12"}
        trip["candidate_sets"]["places"] = [place for place in trip["candidate_sets"]["places"] if place.get("kind") == "poi"]
        hotels = trip["selected"]["hotel_place_ids"]
        hotel_id = hotels[0]
        places = trip["candidate_sets"]["places"][:3]
        trip["candidate_sets"]["places"] = places
        places[2]["id"] = "verified-waterfront-viewpoint"
        places[2]["night_view_evidence"] = {"night_scene": {"status": "visible"}, "river_visibility": {"status": "visible"}, "obstructions": {"status": "clear"}}
        routes = {}
        hours = {}
        for day_index, place in enumerate(places, start=1):
            place["schedule"] = {"duration_minutes": 90, "day": day_index, "required": True}
            if day_index == 3:
                place["schedule"].update({"duration_minutes": 60, "fixed_start_at": "2026-04-12T18:00:00+09:00", "fixed_end_at": "2026-04-12T19:00:00+09:00"})
            hours[place["id"]] = tuple(OpeningInterval(day, time(0), time(23, 59)) for day in range(7))
        meals = []
        for day_index, meal_date in enumerate(("2026-04-10", "2026-04-11", "2026-04-12"), start=1):
            for period, starts in (("breakfast", "08:00"), ("lunch", "12:30"), ("dinner", "18:30")):
                place_id = f"meal-{day_index}-{period}"
                provenance = {"source_type": "provider", "provider": "recorded restaurant feed", "retrieved_at": "2026-04-01T00:00:00+09:00", "status": "confirmed"}
                meal_start = "19:30" if day_index == 3 and period == "dinner" else starts
                meals.append({"place": {"id": place_id, "name": place_id, "kind": "restaurant", "provenance": provenance}, "provenance": provenance,
                    "schedule": {"duration_minutes": 60, "day": day_index, "meal_period": period, "required": False, "fixed_start_at": f"{meal_date}T{meal_start}:00+09:00", "fixed_end_at": f"{meal_date}T{int(meal_start[:2])+1:02d}:{meal_start[3:]}:00+09:00"},
                    "opening_hours": {"status": "fresh", "timezone": "Asia/Tokyo", "intervals": [{"weekday": day, "opens_at": "07:00", "closes_at": "22:00"} for day in range(7)]}})
                hours[place_id] = tuple(OpeningInterval(day, time(7), time(22)) for day in range(7))
        trip["candidate_sets"]["restaurants"] = meals
        for place in [hotel_id, *(item["id"] for item in places), *(item["place"]["id"] for item in meals)]:
            for destination in [hotel_id, *(item["id"] for item in places), *(item["place"]["id"] for item in meals)]:
                if place != destination:
                    routes[(place, destination)] = 5
        result = schedule(SchedulingInput(trip, ValidationContext(routes, hours), daily_start="07:00", daily_end="21:00"))
        self.assertIsNotNone(result.best_trip)
        for day in result.best_trip.trip["days"]:
            meal_items = [item for item in day["items"] if item["kind"] == "meal"]
            self.assertEqual(3, len(meal_items))
            expected_dinner = "19:30" if day["date"] == "2026-04-12" else "18:30"
            self.assertEqual(["08:00", "12:30", expected_dinner], [item["start_at"][11:16] for item in meal_items])
        river_day = result.best_trip.trip["days"][2]
        river = next(item for item in river_day["items"] if item["place_id"] == "verified-waterfront-viewpoint")
        dinner = next(item for item in river_day["items"] if item["kind"] == "meal" and item["start_at"].startswith("2026-04-12T19:30"))
        self.assertEqual(("18:00", "19:00"), (river["start_at"][11:16], river["end_at"][11:16]))
        self.assertGreaterEqual(dinner["start_at"], river["end_at"])

    def test_scheduler_preserves_itinerary_as_partial_when_lodging_is_unselected(self):
        trip = copy.deepcopy(self.trip)
        trip["days"] = []
        trip["selected"]["hotel_place_ids"] = []
        place = next(item for item in trip["candidate_sets"]["places"] if item["id"] == "ohori-park")
        place["schedule"] = {"duration_minutes": 60, "day": 1, "required": True}
        context = verified_context()
        output = schedule(SchedulingInput(trip, context))
        candidate = output.best_trip
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.state, ScheduleState.PARTIAL)
        self.assertEqual(candidate.trip["days"][0]["items"][0]["place_id"], "ohori-park")
        self.assertTrue(any(item["code"] == "schedule.hotel_missing" for item in candidate.trip["validation"]))
        self.assertIn("schedule.origin_unknown", {item.code for item in candidate.violations})

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

    def _scheduler_condition_case(self, fixture_or_snapshot, daily_start="09:00", evaluated_at="2026-04-10T09:00:00+09:00"):
        trip = copy.deepcopy(self.trip)
        trip["days"] = []
        ohori = next(place for place in trip["candidate_sets"]["places"] if place["id"] == "ohori-park")
        ohori["schedule"] = {"duration_minutes": 60, "day": 2, "required": True}
        context = ValidationContext(
            travel_minutes={
                ("hakata-hotel", "ohori-park"): 20,
                ("ohori-park", "hakata-hotel"): 20,
            },
            opening_hours={"ohori-park": [OpeningInterval(weekday, time(8), time(22)) for weekday in range(7)]},
            condition_snapshot=(
                load_condition_snapshot(ROOT / f"fixtures/conditions/{fixture_or_snapshot}.json")
                if isinstance(fixture_or_snapshot, str) else fixture_or_snapshot
            ),
            condition_evaluated_at=datetime.fromisoformat(evaluated_at) if evaluated_at else None,
            condition_policy=ConditionPolicy(max_age=timedelta(days=1)),
        )
        return schedule(SchedulingInput(trip, context, daily_start=daily_start))

    def test_scheduler_rejects_tide_placement_outside_authoritative_window(self):
        result = self._scheduler_condition_case("tide")
        self.assertIsNone(result.best_trip)
        self.assertIn("condition.tide.outside_window", {item.code for item in result.candidates[0].violations})
        self.assertNotIn("schedule.route_unknown", {item.code for item in result.candidates[0].violations})

    def test_scheduler_accepts_tide_placement_inside_authoritative_window(self):
        result = self._scheduler_condition_case("tide", daily_start="09:10")
        candidate = result.best_trip
        self.assertIsNotNone(candidate)
        assert candidate is not None
        item = candidate.trip["days"][1]["items"][0]
        self.assertEqual(item["start_at"], "2026-04-11T09:30:00+09:00")
        self.assertEqual(candidate.state, ScheduleState.READY)

    def test_scheduler_keeps_weather_soft_risk_schedulable(self):
        result = self._scheduler_condition_case("weather")
        candidate = result.best_trip
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.state, ScheduleState.READY)
        self.assertEqual(candidate.trip["days"][1]["items"][0]["start_at"], "2026-04-11T09:20:00+09:00")
        self.assertIn("condition.weather.risk", {item.code for item in candidate.violations})

    def test_scheduler_keeps_stale_and_unknown_condition_warnings_visible(self):
        stale = self._scheduler_condition_case("weather", evaluated_at="2026-04-11T09:00:01+09:00").best_trip
        self.assertIsNotNone(stale)
        assert stale is not None
        self.assertIn("condition.stale", {item.code for item in stale.violations})

        weather = load_condition_snapshot(ROOT / "fixtures/conditions/weather.json")
        unknown = replace(weather.records[0], status=ConditionStatus.UNKNOWN)
        unknown_candidate = self._scheduler_condition_case(ConditionSnapshot((unknown,))).best_trip
        self.assertIsNotNone(unknown_candidate)
        assert unknown_candidate is not None
        self.assertIn("condition.unverified", {item.code for item in unknown_candidate.violations})

    def test_scheduler_snapshot_without_evaluated_at_is_ready_but_unverified(self):
        candidate = self._scheduler_condition_case("weather", evaluated_at=None).best_trip
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertIn("condition.unverified", {item.code for item in candidate.violations})


if __name__ == "__main__":
    unittest.main()
