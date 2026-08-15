import copy
import json
from dataclasses import replace
from datetime import time
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from src.planner import PlanState, PlannerInput, plan
from src.reservations import EvidenceKind, ReservationType, ResolutionIssue, ResolutionState, load_recorded_fixtures, plan_with_reservations
from src.validator import BudgetLimit, OpeningInterval, ValidationContext


ROOT = Path(__file__).parents[1]


class ReservationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = load_recorded_fixtures()

    def test_recorded_fixtures_cover_types_and_offline_input_kinds(self):
        self.assertEqual({item.reservation_type for item in self.fixtures}, set(ReservationType))
        self.assertEqual(
            set(EvidenceKind),
            {item.evidence_kind for item in self.fixtures},
        )
        self.assertTrue(all(len(item.provenance.artifact_sha256) == 64 for item in self.fixtures))

    def test_resolution_reports_missing_place_timezone_and_conflicting_time(self):
        hotel, attraction = self.fixtures[1], self.fixtures[3]
        self.assertEqual(hotel.resolution_state, ResolutionState.PENDING)
        self.assertIn(ResolutionIssue.MISSING_PLACE, hotel.resolution_issues)
        self.assertEqual(attraction.resolution_state, ResolutionState.CONFLICT)
        self.assertIn(ResolutionIssue.MISSING_TIMEZONE, attraction.resolution_issues)
        self.assertIn(ResolutionIssue.CONFLICTING_TIME, attraction.resolution_issues)

    def test_reported_times_compare_instants_and_naive_values_need_timezone(self):
        restaurant = self.fixtures[0]
        equivalent = replace(restaurant, reported_times=("2026-04-11T10:00:00+09:00", "2026-04-11T01:00:00+00:00"))
        self.assertNotIn(ResolutionIssue.CONFLICTING_TIME, equivalent.resolution_issues)
        naive = replace(restaurant, reported_times=("2026-04-11T10:00:00",))
        self.assertIn(ResolutionIssue.MISSING_TIMEZONE, naive.resolution_issues)

    def test_explicit_iana_timezone_is_required_and_must_match_offsets(self):
        restaurant = self.fixtures[0]
        self.assertEqual(restaurant.resolution_state, ResolutionState.READY)
        self.assertNotIn(ResolutionIssue.TIMEZONE_MISMATCH, restaurant.resolution_issues)
        missing = replace(restaurant, timezone=None)
        self.assertIn(ResolutionIssue.MISSING_TIMEZONE, missing.resolution_issues)
        self.assertEqual(missing.resolution_state, ResolutionState.PENDING)
        invalid = replace(restaurant, timezone="Mars/Olympus_Mons")
        self.assertIn(ResolutionIssue.INVALID_TIMEZONE, invalid.resolution_issues)
        self.assertEqual(invalid.resolution_state, ResolutionState.PENDING)
        mismatch = replace(restaurant, start_at="2026-04-11T10:00:00+00:00", end_at="2026-04-11T12:00:00+00:00")
        self.assertIn(ResolutionIssue.TIMEZONE_MISMATCH, mismatch.resolution_issues)
        self.assertEqual(mismatch.resolution_state, ResolutionState.PENDING)

    def test_dst_nonexistent_local_time_is_rejected_but_fall_back_folds_are_valid(self):
        restaurant = self.fixtures[0]
        for offset in ("-05:00", "-04:00"):
            nonexistent = replace(
                restaurant,
                timezone="America/New_York",
                start_at=f"2026-03-08T02:15:00{offset}",
                end_at="2026-03-08T03:15:00-04:00",
            )
            self.assertIn(ResolutionIssue.TIMEZONE_MISMATCH, nonexistent.resolution_issues)
            self.assertIsNone(nonexistent.planner_bindings())
        for offset in ("-04:00", "-05:00"):
            fall_fold = replace(
                restaurant,
                timezone="America/New_York",
                start_at=f"2026-11-01T01:15:00{offset}",
                end_at=f"2026-11-01T01:45:00{offset}",
            )
            self.assertEqual(fall_fold.resolution_state, ResolutionState.READY)
            self.assertIsNotNone(fall_fold.planner_bindings())

    def test_duration_derives_end_and_cancellation_deadline_requires_timezone(self):
        restaurant = self.fixtures[0]
        duration_only = replace(restaurant, end_at=None, duration_minutes=90)
        self.assertEqual(duration_only.effective_end_at, "2026-04-11T11:30:00+09:00")
        self.assertNotIn(ResolutionIssue.MISSING_TIME, duration_only.resolution_issues)
        cancellation = replace(restaurant, cancellation_deadline="2026-04-10T18:00:00")
        self.assertIn(ResolutionIssue.MISSING_CANCELLATION_TIMEZONE, cancellation.resolution_issues)
        with self.assertRaisesRegex(ValueError, "duration_minutes"):
            replace(restaurant, duration_minutes=0)
        with self.assertRaisesRegex(ValueError, "arrival_buffer_minutes"):
            replace(restaurant, arrival_buffer_minutes=-1)
        with self.assertRaisesRegex(ValueError, "reported_times"):
            replace(restaurant, reported_times=("not-a-time",))

    def test_only_resolved_confirmed_evidence_converts_and_binding_is_redacted(self):
        restaurant = self.fixtures[0]
        constraint, overrides = restaurant.planner_bindings()
        self.assertEqual((constraint.kind, constraint.strict), ("fixed_time", True))
        self.assertEqual(constraint.value, {"item_id": "d2-park", "start_at": restaurant.start_at, "end_at": restaurant.end_at})
        serialized = json.dumps([constraint.value, *overrides])
        for secret in (restaurant.confirmation_number, restaurant.traveler_name, restaurant.raw_evidence, "token=secret"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(overrides[0]["provenance"]["source_url"], "https://booking.example/reservation")
        self.assertIn(restaurant.id, overrides[0]["provenance"]["note"])
        self.assertIn(restaurant.provenance.artifact_sha256, overrides[0]["provenance"]["note"])
        self.assertIsNone(self.fixtures[1].planner_bindings())
        self.assertIsNone(self.fixtures[3].planner_bindings())
        self.assertIsNone(self.fixtures[4].planner_bindings())
        flight_constraint, _ = self.fixtures[2].planner_bindings()
        self.assertEqual(flight_constraint.value["item_id"], "d1-arrival")

    def test_public_binding_url_drops_query_and_fragment_and_rejects_userinfo(self):
        restaurant = self.fixtures[0]
        provenance = replace(restaurant.provenance, source_url="https://booking.example/path?token=secret#private")
        _, overrides = replace(restaurant, provenance=provenance).planner_bindings()
        self.assertEqual(overrides[0]["provenance"]["source_url"], "https://booking.example/path")
        unsafe = replace(restaurant, provenance=replace(provenance, source_url="https://user:password@booking.example/path"))
        with self.assertRaisesRegex(ValueError, "userinfo"):
            unsafe.planner_bindings()

    def test_reservation_id_must_be_safe_for_derived_trip_ids(self):
        restaurant = self.fixtures[0]
        for invalid_id in ("", "Booking", "booking code"):
            with self.subTest(invalid_id=invalid_id), self.assertRaisesRegex(ValueError, "Trip schema pattern"):
                replace(restaurant, id=invalid_id)
        with self.assertRaisesRegex(ValueError, "provider"):
            replace(restaurant, provider="   ")

    def test_overrides_are_trip_schema_compatible_and_repair_does_not_move_anchor(self):
        reservation = self.fixtures[0]
        trip = json.loads((ROOT / "fixtures/trips/japan-5-day-trip-v1.json").read_text(encoding="utf-8"))
        legacy_override = {
            "id": "reservation-legacy-hotel",
            "path": "/selected/hotel_place_ids",
            "value": ["hakata-hotel"],
            "preserve_on_replan": True,
            "provenance": {"source_type": "user_input", "provider": "traveler", "retrieved_at": "2026-01-20T09:00:00+09:00", "status": "confirmed"},
        }
        trip["overrides"].append(legacy_override)
        trip["overrides"].extend(reservation.overrides_for(1, 0))
        # Force a later item into an overlap. Repair may move that item, but not
        # the confirmed reservation anchor preserved by the two overrides.
        later = copy.deepcopy(trip["days"][1]["items"][0])
        later.update({"id": "after-reservation", "place_id": "dazaifu", "start_at": "2026-04-11T11:00:00+09:00", "end_at": "2026-04-11T13:00:00+09:00"})
        trip["days"][1]["items"].append(later)
        schema = json.loads((ROOT / "src/schemas/trip_v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(trip)
        hours = {place: [OpeningInterval(day, time(8), time(22)) for day in range(7)] for place in ("ohori-park", "dazaifu", "yufuin", "beppu", "canal-city")}
        context = ValidationContext(travel_minutes={("ohori-park", "dazaifu"): 30, ("fuk", "hakata-hotel"): 180, ("yufuin", "beppu"): 60}, opening_hours=hours, budget_limit=BudgetLimit(200000, "JPY"))
        result = plan_with_reservations(PlannerInput([trip], context, max_repair_iterations=2), [reservation])
        candidate = result.best_plan
        self.assertEqual(candidate.state, PlanState.REPAIRED)
        anchor = candidate.trip["days"][1]["items"][0]
        self.assertEqual((anchor["start_at"], anchor["end_at"]), (reservation.start_at, reservation.end_at))
        self.assertEqual(candidate.trip["days"][1]["items"][1]["start_at"], "2026-04-11T12:30:00+09:00")
        self.assertEqual([item["path"] for item in candidate.trip["overrides"][-2:]], ["/days/1/items/0/start_at", "/days/1/items/0/end_at"])
        self.assertIn(legacy_override, candidate.trip["overrides"])
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(candidate.trip)

    def test_anchor_is_restored_even_when_it_is_the_repair_target_and_plan_fails(self):
        reservation = self.fixtures[0]
        trip = json.loads((ROOT / "fixtures/trips/japan-5-day-trip-v1.json").read_text(encoding="utf-8"))
        previous = copy.deepcopy(trip["days"][1]["items"][0])
        previous.update({"id": "before-anchor", "place_id": "dazaifu", "start_at": "2026-04-11T09:30:00+09:00", "end_at": "2026-04-11T10:30:00+09:00"})
        trip["days"][1]["items"].insert(0, previous)
        hours = {place: [OpeningInterval(day, time(8), time(22)) for day in range(7)] for place in ("ohori-park", "dazaifu", "yufuin", "beppu", "canal-city")}
        context = ValidationContext(travel_minutes={("dazaifu", "ohori-park"): 0, ("fuk", "hakata-hotel"): 180, ("yufuin", "beppu"): 60}, opening_hours=hours, budget_limit=BudgetLimit(200000, "JPY"))
        candidate = plan_with_reservations(PlannerInput([trip], context, max_repair_iterations=2), [reservation]).plans[0]
        self.assertEqual(candidate.state, PlanState.FAILED)
        anchor = candidate.trip["days"][1]["items"][1]
        self.assertEqual((anchor["start_at"], anchor["end_at"]), (reservation.start_at, reservation.end_at))
        self.assertIn("time.overlap", {violation.code for violation in candidate.violations})


if __name__ == "__main__":
    unittest.main()
