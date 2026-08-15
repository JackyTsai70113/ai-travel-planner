from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from unittest import TestCase

from src.opening_hours import Eligibility, evaluate_opening_hours
from src.restaurant_intelligence import eligible_restaurants, meal_eligibility, reconcile_restaurant_candidates
from src.schemas import TripValidationError, validate_trip
from src.validator import Outcome, validate_itinerary


FIXTURE = Path(__file__).parents[1] / "fixtures/trips/japan-5-day-trip-v1.json"
PROVENANCE = {
    "source_type": "provider", "provider": "recorded", "source_url": "https://example.test/restaurant",
    "retrieved_at": "2026-08-25T00:00:00+00:00", "status": "confirmed",
}


def candidate(place_id="restaurant-x", *, status="fresh", intervals=None, special_hours=None, provenance=None):
    source = provenance or PROVENANCE
    return {
        "place": {"id": place_id, "name": "Restaurant", "kind": "restaurant", "provenance": source},
        "opening_hours": {
            "status": status, "timezone": "Asia/Tokyo",
            "intervals": intervals if intervals is not None else [{"weekday": 2, "opens_at": "11:30", "closes_at": "14:00"}],
            "closed_weekdays": [], "regular_holidays": [], "special_hours": special_hours or [],
            "provenance": source,
        },
        "provenance": source,
    }


def test_timezone_conversion_and_full_split_interval_gate():
    restaurant = candidate(intervals=[
        {"weekday": 2, "opens_at": "11:30", "closes_at": "14:00", "last_order_at": "13:30"},
        {"weekday": 2, "opens_at": "17:30", "closes_at": "21:00"},
    ])
    # Taipei 11:30 is Tokyo 12:30 on Wednesday.
    assert meal_eligibility(
        restaurant,
        datetime.fromisoformat("2026-08-26T11:30:00+08:00"),
        datetime.fromisoformat("2026-08-26T12:30:00+08:00"),
    ) is Eligibility.ELIGIBLE
    assert meal_eligibility(
        restaurant,
        datetime.fromisoformat("2026-08-26T13:00:00+09:00"),
        datetime.fromisoformat("2026-08-26T14:00:00+09:00"),
    ) is Eligibility.ELIGIBLE  # order is placed before the 13:30 cutoff
    assert meal_eligibility(
        restaurant,
        datetime.fromisoformat("2026-08-26T13:31:00+09:00"),
        datetime.fromisoformat("2026-08-26T13:50:00+09:00"),
    ) is Eligibility.CLOSED
    assert meal_eligibility(
        restaurant,
        datetime.fromisoformat("2026-08-26T13:30:00+09:00"),
        datetime.fromisoformat("2026-08-26T18:00:00+09:00"),
    ) is Eligibility.CLOSED  # lunch/dinner split gap


def test_fresh_hours_without_restaurant_timezone_are_unverified():
    restaurant = candidate()
    del restaurant["opening_hours"]["timezone"]
    start = datetime.fromisoformat("2026-08-26T12:00:00+08:00")
    end = datetime.fromisoformat("2026-08-26T13:00:00+08:00")
    assert meal_eligibility(restaurant, start, end) is Eligibility.UNVERIFIED

    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    restaurant["place"]["id"] = "ramen-shop"
    trip["candidate_sets"]["restaurants"] = [restaurant]
    trip["days"][3]["items"].append({
        "id": "missing-timezone-meal", "kind": "meal", "place_id": "ramen-shop",
        "start_at": "2026-04-13T12:00:00+09:00", "end_at": "2026-04-13T13:00:00+09:00",
        "selection_status": "selected",
    })
    result = validate_itinerary(trip)
    assert "opening_hours.unverified" in {violation.code for violation in result.violations}


def test_closed_weekday_and_special_date_states_override_weekly_hours():
    wednesday = (datetime.fromisoformat("2026-08-26T12:00:00+09:00"), datetime.fromisoformat("2026-08-26T13:00:00+09:00"))
    closed = candidate(intervals=[{"weekday": 2, "opens_at": "00:00", "closes_at": "00:00", "closes_day_offset": 1}])
    closed["opening_hours"]["closed_weekdays"] = [2]
    assert meal_eligibility(closed, *wednesday) is Eligibility.CLOSED

    for state, expected in (("closed", Eligibility.CLOSED), ("unverified", Eligibility.UNVERIFIED)):
        special = candidate(special_hours=[{"date": "2026-08-26", "status": state, "intervals": []}])
        assert meal_eligibility(special, *wednesday) is expected
    special_open = candidate(
        intervals=[],
        special_hours=[{"date": "2026-08-26", "status": "open", "intervals": [{"opens_at": "12:00", "closes_at": "13:00"}]}],
    )
    assert meal_eligibility(special_open, *wednesday) is Eligibility.ELIGIBLE


def test_overnight_and_24_hour_intervals_do_not_use_nonstandard_clock_values():
    overnight = candidate(intervals=[{"weekday": 2, "opens_at": "22:00", "closes_at": "02:00", "closes_day_offset": 1}])
    assert evaluate_opening_hours(
        overnight["opening_hours"],
        datetime.fromisoformat("2026-08-26T23:00:00+09:00"),
        datetime.fromisoformat("2026-08-27T01:00:00+09:00"),
    ).eligible
    assert evaluate_opening_hours(
        overnight["opening_hours"],
        datetime.fromisoformat("2026-08-27T00:30:00+09:00"),
        datetime.fromisoformat("2026-08-27T01:30:00+09:00"),
    ).eligible
    always = candidate(intervals=[{"weekday": 2, "opens_at": "00:00", "closes_at": "00:00", "closes_day_offset": 1}])
    assert meal_eligibility(always, datetime.fromisoformat("2026-08-26T00:00:00+09:00"), datetime.fromisoformat("2026-08-26T23:59:00+09:00")) is Eligibility.ELIGIBLE


def test_previous_special_closure_overrides_regular_overnight_hours():
    start = datetime.fromisoformat("2026-08-27T00:30:00+09:00")
    end = datetime.fromisoformat("2026-08-27T01:30:00+09:00")
    regular = [{"weekday": 2, "opens_at": "22:00", "closes_at": "02:00", "closes_day_offset": 1}]
    closed = candidate(intervals=regular, special_hours=[{"date": "2026-08-26", "status": "closed", "intervals": []}])
    unknown = candidate(intervals=regular, special_hours=[{"date": "2026-08-26", "status": "unverified", "intervals": []}])
    assert meal_eligibility(closed, start, end) is Eligibility.CLOSED
    assert meal_eligibility(unknown, start, end) is Eligibility.UNVERIFIED


def test_wednesday_closed_candidate_is_filtered_before_alternative_selection():
    closed = candidate("closed", intervals=[])
    closed["opening_hours"]["closed_weekdays"] = [2]
    open_restaurant = candidate("open")
    selected = eligible_restaurants(
        [closed, open_restaurant],
        datetime.fromisoformat("2026-08-26T12:00:00+09:00"),
        datetime.fromisoformat("2026-08-26T13:00:00+09:00"),
    )
    assert [item["place"]["id"] for item in selected] == ["open"]
    assert eligible_restaurants([candidate(status="stale"), candidate(status="unverified"), candidate(status="conflicting")], *(
        datetime.fromisoformat("2026-08-26T12:00:00+09:00"), datetime.fromisoformat("2026-08-26T13:00:00+09:00")
    )) == []
    temporarily_closed = candidate()
    temporarily_closed["business_status"] = "closed_temporarily"
    assert eligible_restaurants([temporarily_closed], *(
        datetime.fromisoformat("2026-08-26T12:00:00+09:00"), datetime.fromisoformat("2026-08-26T13:00:00+09:00")
    )) == []


def test_official_override_and_same_authority_conflict_are_auditable():
    provider = candidate()
    provider["place"]["address"] = "福岡市中央区"
    provider["place"]["coordinates"] = {"latitude": 33.59, "longitude": 130.40}
    provider["attributions"] = ["Provider credit"]
    provider.update({"rating": 4.7, "rating_source": "Google Places", "review_count": 120, "cuisine": "ramen"})
    official_source = {**PROVENANCE, "source_type": "official", "provider": "Restaurant official site"}
    official = candidate(provenance=official_source, intervals=[{"weekday": 2, "opens_at": "17:00", "closes_at": "20:00"}])
    official.update({"rating": 1.0, "rating_source": "self_claimed", "review_count": 1, "cuisine": "official category"})
    reconciled = reconcile_restaurant_candidates([provider, official])[0]
    assert reconciled["opening_hours"]["intervals"][0]["opens_at"] == "17:00"
    assert len(reconciled["source_provenance"]) == 2
    assert reconciled["alternatives"][0]["field"] == "opening_hours"
    assert reconciled["place"]["address"] == "福岡市中央区"
    assert reconciled["place"]["coordinates"] == {"latitude": 33.59, "longitude": 130.40}
    assert reconciled["place"]["provenance"]["provider"] == "recorded"
    assert reconciled["attributions"] == ["Provider credit"]
    assert (reconciled["rating"], reconciled["rating_source"], reconciled["review_count"], reconciled["cuisine"]) == (
        4.7, "Google Places", 120, "ramen",
    )
    alternative_fields = {alternative["field"] for alternative in reconciled["alternatives"]}
    assert {"rating", "rating_source", "review_count", "cuisine"} <= alternative_fields

    other_official = candidate(provenance={**official_source, "provider": "Official notice"})
    conflict = reconcile_restaurant_candidates([official, other_official])[0]
    assert conflict["opening_hours"]["status"] == "conflicting"
    assert meal_eligibility(conflict, datetime.fromisoformat("2026-08-26T12:00:00+09:00"), datetime.fromisoformat("2026-08-26T13:00:00+09:00")) is Eligibility.UNVERIFIED
    # Equal names never merge unrelated canonical IDs.
    assert len(reconcile_restaurant_candidates([candidate("one"), candidate("two")])) == 2


def test_rating_bundle_and_reconciliation_audit_are_source_coherent_and_idempotent():
    provider_a = candidate()
    provider_a.update({"rating": 4.7, "rating_source": "Provider A"})
    provider_b = candidate(provenance={**PROVENANCE, "provider": "Provider B"})
    provider_b.update({"rating": 3.1, "rating_source": "Provider B", "review_count": 900})

    bundled = reconcile_restaurant_candidates([provider_a, provider_b])[0]
    assert (bundled["rating"], bundled["rating_source"]) == (4.7, "Provider A")
    assert "review_count" not in bundled
    provider_b_alternatives = {
        item["field"]: item
        for item in bundled["alternatives"]
        if item["provenance"]["provider"] == "Provider B"
    }
    assert provider_b_alternatives["review_count"]["value"] == 900

    official_source = {**PROVENANCE, "source_type": "official", "provider": "Restaurant official site"}
    official = candidate(provenance=official_source, intervals=[{"weekday": 2, "opens_at": "17:00", "closes_at": "20:00"}])
    official.update({"rating": 1.0, "rating_source": "self_claimed", "review_count": 1, "cuisine": "official category"})
    provider_a.update({"review_count": 120, "cuisine": "ramen"})
    first = reconcile_restaurant_candidates([provider_a, official])[0]
    second = reconcile_restaurant_candidates([first, official])[0]
    third = reconcile_restaurant_candidates([first])[0]
    assert second["alternatives"] == first["alternatives"]
    assert second["source_provenance"] == first["source_provenance"]
    assert third["alternatives"] == first["alternatives"]
    assert third["source_provenance"] == first["source_provenance"]


def test_validator_uses_candidate_snapshot_as_direct_closed_fallback():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    restaurant = candidate("ramen-shop", intervals=[])
    restaurant["opening_hours"]["closed_weekdays"] = [0]
    trip["candidate_sets"]["restaurants"] = [restaurant]
    trip["days"][3]["items"].append({
        "id": "closed-meal", "kind": "meal", "place_id": "ramen-shop",
        "start_at": "2026-04-13T12:00:00+09:00", "end_at": "2026-04-13T13:00:00+09:00", "selection_status": "selected",
    })
    result = validate_itinerary(trip)
    assert result.outcome is Outcome.INVALID
    assert "opening_hours.closed" in {violation.code for violation in result.violations}


def test_planner_deduplicates_validator_and_candidate_hours_violation():
    from src.planner import PlannerInput, plan

    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    restaurant = candidate("ramen-shop", intervals=[])
    restaurant["opening_hours"]["closed_weekdays"] = [0]
    trip["candidate_sets"]["restaurants"] = [restaurant]
    trip["days"][3]["items"].append({
        "id": "closed-meal", "kind": "meal", "place_id": "ramen-shop",
        "start_at": "2026-04-13T12:00:00+09:00", "end_at": "2026-04-13T13:00:00+09:00",
        "selection_status": "selected",
    })
    result = plan(PlannerInput([trip], max_repair_iterations=0))
    closed = [violation for violation in result.plans[0].violations if violation.code == "opening_hours.closed"]
    assert len(closed) == 1


def test_schema_invariants_reject_bad_rating_dish_and_extended_clock():
    base = json.loads(FIXTURE.read_text(encoding="utf-8"))
    restaurant = base["candidate_sets"]["restaurants"][0]
    restaurant["ratings"] = [{"value": 6, "scale_min": 1, "scale_max": 5, "review_count": 3, "provenance": PROVENANCE}]
    with TestCase().assertRaisesRegex(TripValidationError, "original scale"):
        validate_trip(base)
    unknown_review_count = json.loads(FIXTURE.read_text(encoding="utf-8"))
    unknown_review_count["candidate_sets"]["restaurants"][0]["ratings"] = [{
        "value": 4.5, "scale_min": 1, "scale_max": 5, "provenance": PROVENANCE,
    }]
    validate_trip(unknown_review_count)
    invalid_dish = json.loads(FIXTURE.read_text(encoding="utf-8"))
    invalid_dish["candidate_sets"]["restaurants"][0]["recommended_dishes"] = [{"name": "無來源"}]
    with TestCase().assertRaisesRegex(TripValidationError, "provenance"):
        validate_trip(invalid_dish)
    invalid_clock = json.loads(FIXTURE.read_text(encoding="utf-8"))
    invalid_clock["candidate_sets"]["restaurants"][0]["opening_hours"] = {
        "status": "fresh", "timezone": "Asia/Tokyo", "intervals": [{"weekday": 0, "opens_at": "11:00", "closes_at": "29:00"}],
    }
    with TestCase().assertRaisesRegex(TripValidationError, "23:59"):
        validate_trip(invalid_clock)
