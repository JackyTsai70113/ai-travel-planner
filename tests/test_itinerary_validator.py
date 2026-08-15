import copy
from dataclasses import replace
from datetime import datetime, time
from pathlib import Path
import json
import unittest

from src.validator import (
    BudgetLimit,
    OpeningInterval,
    Outcome,
    PlaceConstraint,
    RouteConstraint,
    RuleRegistry,
    ValidationContext,
    validate_itinerary,
)


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


def with_context(**overrides) -> ValidationContext:
    return replace(verified_context(), **overrides)


class ItineraryValidatorTests(unittest.TestCase):
    def setUp(self):
        self.trip = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))

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
        self.assertIn("time.overlap", {item.code for item in result.violations})
        self.assertIn("travel_time.insufficient", {item.code for item in result.violations})

    def test_closed_and_over_budget_fail(self):
        context = verified_context()
        context = with_context(
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

    def test_confirmed_reservation_anchor_drift_is_invalid(self):
        context = with_context(fixed_anchors={"d1-arrival": ("2026-04-10T11:00:00+09:00", "2026-04-10T12:00:00+09:00")})
        result = validate_itinerary(self.trip, context)
        self.assertEqual(result.outcome, Outcome.INVALID)
        self.assertIn("reservation.fixed_anchor_drift", {item.code for item in result.violations})

    def test_temporarily_closed_place_becomes_invalid(self):
        context = with_context(place_constraints={"dazaifu": PlaceConstraint(temporarily_closed=True)})
        result = validate_itinerary(self.trip, context)
        self.assertEqual(result.outcome, Outcome.INVALID)
        self.assertIn("place.temporarily_closed", {item.code for item in result.violations})

    def test_last_admission_and_booking_deadline_are_enforced(self):
        deadline = datetime.fromisoformat("2026-04-12T08:30:00+09:00")
        context = with_context(
            place_constraints={
                "dazaifu": PlaceConstraint(
                    last_admission_at=time(11, 0),
                    booking_deadline=deadline,
                )
            }
        )
        result = validate_itinerary(self.trip, context)
        self.assertEqual(result.outcome, Outcome.INVALID)
        self.assertIn("place.last_admission", {item.code for item in result.violations})

    def test_weather_tide_daylight_block_a_route(self):
        context = with_context(
            route_facts={
                ("yufuin", "beppu"): RouteConstraint(
                    weather_open=False,
                    tide_open=False,
                    daylight_open=False,
                )
            }
        )
        result = validate_itinerary(self.trip, context)
        self.assertEqual(result.outcome, Outcome.INVALID)
        self.assertIn("condition.weather", {item.code for item in result.violations})
        self.assertIn("condition.tide", {item.code for item in result.violations})
        self.assertIn("condition.daylight", {item.code for item in result.violations})

    def test_route_unknown_and_no_route_are_validated(self):
        context = with_context(
            required_transport_pairs=(("fuk", "hakata-hotel"),),
            route_facts={("fuk", "hakata-hotel"): RouteConstraint(status="no_route")},
        )
        result = validate_itinerary(self.trip, context)
        self.assertEqual(result.outcome, Outcome.INVALID)
        self.assertIn("route.no_route", {item.code for item in result.violations})

    def test_required_and_forbidden_locations(self):
        with_required = with_context(required_locations=("nonexistent-place",))
        required_result = validate_itinerary(self.trip, with_required)
        self.assertEqual(required_result.outcome, Outcome.INVALID)
        self.assertIn("location.required", {item.code for item in required_result.violations})

        with_forbidden = with_context(forbidden_locations=("ohori-park",))
        forbidden_result = validate_itinerary(self.trip, with_forbidden)
        self.assertEqual(forbidden_result.outcome, Outcome.INVALID)
        self.assertIn("location.forbidden", {item.code for item in forbidden_result.violations})

    def test_daily_hotel_consistency(self):
        context = with_context(daily_hotel_constraints={1: ("hakata-hotel", "hakata-hotel")})
        result = validate_itinerary(self.trip, context)
        self.assertEqual(result.outcome, Outcome.INVALID)
        self.assertIn("hotel.start", {item.code for item in result.violations})

    def test_arrival_buffer_increases_required_route_time(self):
        trip = copy.deepcopy(self.trip)
        trip["days"][3]["items"][1]["start_at"] = "2026-04-13T12:30:00+09:00"
        trip["days"][3]["items"][1]["end_at"] = "2026-04-13T13:00:00+09:00"
        context = with_context(route_facts={("yufuin", "beppu"): RouteConstraint(minutes=60, arrival_buffer_minutes=30)})
        result = validate_itinerary(trip, context)
        self.assertEqual(result.outcome, Outcome.INVALID)
        self.assertIn("travel_time.insufficient", {item.code for item in result.violations})

    def test_source_freshness_warning_marks_incomplete(self):
        context = with_context(
            place_constraints={"ohori-park": PlaceConstraint(temporarily_closed=False, source_status="reported")},
            require_fresh_critical_facts=True,
        )
        result = validate_itinerary(self.trip, context)
        self.assertEqual(result.outcome, Outcome.INCOMPLETE)
        self.assertIn("fact.unverified", {item.code for item in result.violations})


if __name__ == "__main__":
    unittest.main()
