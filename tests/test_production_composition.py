from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.application.production import (
    ProductionDependencies,
    ProductionIncompleteError,
    _add_elapsed_minutes,
    _assign_route_aware_poi_schedule,
    _candidate_trips,
    _google_flights_search_summary,
    _google_flights_search_url,
    _routing_context,
    _select_hotel_candidate,
    create_production_orchestrator,
)
from src.cli import plan_command
from src.intent import parse_trip_request
from src.orchestrator import StageName, StageStatus
from src.planner import schedule as route_aware_schedule
from src.schemas import validate_trip
from src.sources import SourceAdapter
from src.sources.routing import PlaceRef, Route, RouteProvenance, RouteStatus
from src.validator import OpeningInterval, ValidationContext

ENVIRONMENT = {
    "GOOGLE_MAPS_API_KEY": "google-secret",
    "YOUTUBE_API_KEY": "youtube-secret",
    "OPENROUTESERVICE_API_KEY": "ors-secret",
}


class RecordedGoogle(SourceAdapter):
    name = "recorded-google"

    def __init__(self):
        self.queries = []

    def fetch(self, query):
        self.queries.append(query)
        now = "2026-01-01T00:00:00+09:00"
        provenance = {"source_type": "provider", "provider": "Recorded Google Places", "source_url": "https://example.test/places", "retrieved_at": now, "status": "confirmed"}
        hours = {"status": "fresh", "timezone": "Asia/Tokyo", "intervals": [{"weekday": day, "opens_at": "08:00", "closes_at": "22:00"} for day in range(7)], "provenance": provenance}
        places = [("places", {"id": f"poi-{number}", "name": f"POI {number}", "kind": "poi", "primary_type": "museum", "coordinates": {"latitude": 34.1 + number / 10000, "longitude": 134.2}, "opening_hours": hours, "provenance": provenance}) for number in range(12)]
        restaurant = {"place": {"id": "restaurant-1", "name": "Open restaurant", "kind": "restaurant", "coordinates": {"latitude": 34.1, "longitude": 134.1}, "provenance": provenance}, "rating": 4.5, "review_count": 100, "opening_hours": {"status": "fresh", "timezone": "Asia/Tokyo", "intervals": [{"weekday": day, "opens_at": "09:00", "closes_at": "21:00"} for day in range(7)]}, "provenance": provenance}
        return [*places, ("restaurants", restaurant)]


class RecordedTaiwanGoogle(RecordedGoogle):
    def fetch(self, query):
        results = super().fetch(query)
        for collection, candidate in results:
            target = candidate["place"] if collection == "restaurants" else candidate
            target["coordinates"] = {"latitude": 25.04, "longitude": 121.51}
            if collection == "restaurants":
                candidate["opening_hours"]["timezone"] = "Asia/Taipei"
        return results


class RecordedYouTube:
    name = "recorded-youtube"

    def fetch_evidence(self, query):
        return []


class RecordedCompleteRouting:
    def fetch(self, origin, destination, mode):
        return self.fetch_matrix((origin, destination), mode)[(mode.value, origin.place_id, destination.place_id)]

    def fetch_matrix(self, places, mode):
        refs = tuple(places)
        now = datetime.now(timezone.utc)
        return {
            (mode.value, origin.place_id, destination.place_id): Route(
                origin, destination, mode, RouteStatus.AVAILABLE,
                RouteProvenance("recorded-routing", now, note="Deterministic route fixture"),
                duration_seconds=600, distance_meters=5000,
            )
            for origin in refs for destination in refs if origin != destination
        }


class BrokenYouTube(RecordedYouTube):
    def fetch_evidence(self, query):
        raise RuntimeError("recorded YouTube timeout")


def _runner(tmp_path, *, youtube=None, google=None, environment=ENVIRONMENT):
    dependencies = ProductionDependencies(
        google=google or RecordedGoogle(), youtube=youtube or RecordedYouTube(),
        routing_provider=RecordedCompleteRouting(),
    )
    return create_production_orchestrator(
        trip_id="recorded-trip", trips_directory=tmp_path / "trips", site_directory=tmp_path / "site",
        environment=environment, dependencies=dependencies,
    )


def test_recorded_production_composition_runs_pipeline_and_persists_canonical_outputs(tmp_path):
    intent = parse_trip_request("2026/4/10到2026/4/14 台北出發德島五天四夜，2大，預算8萬日圓，自駕")
    result = _runner(tmp_path).run(intent)

    assert result.succeeded
    assert result.trip_path == tmp_path / "trips" / "recorded-trip" / "trip.json"
    assert result.render_path == tmp_path / "site" / "recorded-trip" / "index.html"
    persisted = result.trip_path.read_text(encoding="utf-8")
    trip = json.loads(persisted)
    assert trip["selected"]["flight_ids"] == []
    assert trip["candidate_sets"]["flights"] == []
    assert "google.com/travel/flights?" in trip["flight_search_url"]
    assert "開啟 Google Flights 搜尋航班" in result.render_path.read_text(encoding="utf-8")
    assert "台北 → 德島" in trip["flight_search_summary"]
    assert trip["local_timezone"] == "Asia/Tokyo"
    assert trip["budget"]["currency"] == "JPY"
    assert trip["budget"]["limit_status"] == "limited"
    assert trip["budget"]["limit"] == {"amount": 80000, "currency": "JPY"}
    assert "預算上限 JPY 80,000" in result.render_path.read_text(encoding="utf-8")
    assert "google-secret" not in persisted
    assert result.render_path.exists()


def test_nested_provider_failure_is_visible_to_orchestrator_without_losing_trip(tmp_path):
    intent = parse_trip_request("2026/4/10到2026/4/14 台北出發德島五天四夜，2大，預算8萬日圓，自駕")
    result = _runner(tmp_path, youtube=BrokenYouTube()).run(intent)

    assert result.succeeded
    research = result.stage(StageName.RESEARCH)
    assert research.status is StageStatus.SUCCEEDED
    assert any(
        warning.code == "research.provider_failed"
        and "recorded-youtube" in warning.message
        and "recorded YouTube timeout" in warning.message
        for warning in research.warnings
    )


def test_production_runs_without_youtube_key_and_reports_optional_source_unavailable(tmp_path):
    environment = {key: value for key, value in ENVIRONMENT.items() if key != "YOUTUBE_API_KEY"}
    runner = create_production_orchestrator(
        trip_id="without-youtube", trips_directory=tmp_path / "trips", site_directory=tmp_path / "site",
        environment=environment,
        dependencies=ProductionDependencies(
            google=RecordedGoogle(),
            routing_provider=RecordedCompleteRouting(),
        ),
    )
    intent = parse_trip_request("2026/4/10到2026/4/14 台北出發德島五天四夜，2大，預算8萬日圓，自駕")

    result = runner.run(intent)

    assert result.succeeded
    research = result.stage(StageName.RESEARCH)
    assert research.status is StageStatus.SUCCEEDED
    assert any("YOUTUBE_API_KEY is not configured" in warning.message for warning in research.warnings)


def test_kurashiki_unlimited_budget_is_not_confused_with_incomplete_cost_coverage(tmp_path):
    request = "日本岡山縣倉敷五天四夜。日期：2026/11/01～2026/11/05。出發地：桃園國際機場。旅客：6位成人、1位2歲幼兒。預算：暫不設限制。交通方式：自駕。"
    intent = parse_trip_request(request)
    result = _runner(tmp_path).run(intent)

    assert result.succeeded
    assert intent.budget_status == "unlimited"
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert trip["selected"]["hotel_place_ids"] == []
    assert trip["budget"]["total_status"] == "incomplete"


def test_kurashiki_five_day_fixture_schedules_pois_and_lunch_without_lodging():
    request = "日本岡山縣倉敷五天四夜。日期：2026/11/01～2026/11/05。出發地：桃園國際機場。旅客：6位成人、1位2歲幼兒。預算：暫不設限制。交通方式：自駕。"
    intent = parse_trip_request(request)
    provenance = {"source_type": "provider", "provider": "Recorded Places", "source_url": "https://example.test/places", "retrieved_at": "2026-10-01T00:00:00+09:00", "status": "confirmed"}
    hours = {"status": "fresh", "timezone": "Asia/Tokyo", "intervals": [{"weekday": day, "opens_at": "08:00", "closes_at": "22:00"} for day in range(7)], "provenance": provenance}
    anchors = {
        0: {"duration_minutes": 75, "duration_basis": "provider", "day": 1, "selected": True, "required": True, "fixed_start_at": "2026-11-01T09:30:00+09:00", "fixed_end_at": "2026-11-01T10:45:00+09:00"},
        1: {"duration_minutes": 75, "duration_basis": "provider", "day": 1, "selected": True, "required": True, "fixed_start_at": "2026-11-01T14:00:00+09:00", "fixed_end_at": "2026-11-01T15:15:00+09:00"},
    }
    poi_records = [("places", {"id": f"kurashiki-poi-{number}", "name": f"倉敷景點 {number}", "kind": "poi", "primary_type": "museum", "coordinates": {"latitude": 34.6 + number / 10000, "longitude": 133.77}, "opening_hours": hours, **({"schedule": anchors[number]} if number in anchors else {}), "provenance": provenance}) for number in range(12)]
    refs = [PlaceRef(candidate["id"], candidate["coordinates"]["latitude"], candidate["coordinates"]["longitude"]) for _, candidate in poi_records]
    restaurants = [{"place": {"id": f"kurashiki-restaurant-{number}", "name": f"倉敷餐廳 {number}", "kind": "restaurant", "coordinates": {"latitude": 34.6, "longitude": 133.77}, "provenance": provenance}, "opening_hours": {"status": "fresh", "timezone": "Asia/Tokyo", "intervals": [{"weekday": day, "opens_at": "09:00", "closes_at": "21:00"} for day in range(7)]}, "rating": 4.5, "review_count": 50, "provenance": provenance} for number in range(10)]
    refs.extend(PlaceRef(item["place"]["id"], 34.6, 133.77) for item in restaurants)
    routes = {(origin.place_id, destination.place_id): 10 for origin in refs for destination in refs if origin != destination}
    opening = {ref.place_id: tuple(OpeningInterval(day, time(8), time(22)) for day in range(7)) for ref in refs}

    records = [*(SimpleNamespace(collection=collection, candidate=candidate) for collection, candidate in poi_records),
               *(SimpleNamespace(collection="restaurants", candidate=item) for item in restaurants)]
    with patch("src.application.production.schedule", wraps=route_aware_schedule) as scheduler:
        trip, = _candidate_trips("kurashiki-recorded", intent, records, ValidationContext(routes, opening))
    scheduler.assert_called_once()
    validate_trip(trip)

    visits_by_day = [[item for item in day["items"] if item["kind"] == "visit"] for day in trip["days"]]
    assert len(poi_records) >= 10
    assert all(len(visits) >= 2 for visits in visits_by_day)
    scheduled_meals = [item for day in trip["days"] for item in day["items"] if item["kind"] == "meal"]
    assert len(scheduled_meals) == 10
    assert all(any(item["kind"] == "meal" for item in day["items"]) for day in trip["days"])
    assert trip["selected"]["hotel_place_ids"] == []
    assert trip["candidate_sets"]["places"][0]["schedule"]["duration_basis"] == "provider"
    assert trip["candidate_sets"]["places"][0]["schedule"]["fixed_start_at"] == "2026-11-01T09:30:00+09:00"
    assert trip["candidate_sets"]["places"][1]["schedule"]["fixed_start_at"] == "2026-11-01T14:00:00+09:00"
    assert all(trip["candidate_sets"]["places"][number]["schedule"]["duration_basis"] == "planning_estimate" for number in range(2, 12))
    assert all(item["end_at"] > item["start_at"] for day in visits_by_day for item in day)
    assert trip["budget"]["limit_status"] == "unlimited"
    assert "limit" not in trip["budget"]
    assert trip["budget"]["total_status"] == "incomplete"



def test_route_aware_assignment_reserves_weekday_limited_pois_for_constrained_days():
    start = date(2026, 11, 2)  # Monday
    places = [{"id": name, "name": name, "kind": "poi", "schedule": {"duration_minutes": 60, "duration_basis": "provider"}}
              for name in ("common-a", "common-b", "monday-c", "monday-d")]
    hours = {
        "common-a": tuple(OpeningInterval(day, time(8), time(22)) for day in (0, 1)),
        "common-b": tuple(OpeningInterval(day, time(8), time(22)) for day in (0, 1)),
        "monday-c": (OpeningInterval(0, time(8), time(22)),),
        "monday-d": (OpeningInterval(0, time(8), time(22)),),
    }
    ids = ["hotel", *(place["id"] for place in places)]
    routes = {(origin, destination): 10 for origin in ids for destination in ids if origin != destination}
    routes.update({("hotel", "common-a"): 1, ("common-a", "common-b"): 1, ("common-b", "hotel"): 1})

    _assign_route_aware_poi_schedule(places, 2, start, "Asia/Tokyo", "hotel", ValidationContext(routes, hours))

    assert {place["id"] for place in places if place["schedule"]["day"] == 1} == {"monday-c", "monday-d"}
    assert {place["id"] for place in places if place["schedule"]["day"] == 2} == {"common-a", "common-b"}


def test_production_preserves_overnight_opening_interval_offset_in_routing_context():
    intent = parse_trip_request("2026/11/01到2026/11/01 倉敷一日，2大")
    poi = {"id": "overnight-poi", "name": "Night Museum", "kind": "poi", "coordinates": {"latitude": 34.6, "longitude": 133.77},
           "opening_hours": {"status": "fresh", "timezone": "Asia/Tokyo", "intervals": [{"weekday": 6, "opens_at": "18:00", "closes_at": "01:00", "closes_day_offset": 1}]},
           "provenance": {"source_type": "provider", "provider": "Recorded Places", "retrieved_at": "2026-10-01T00:00:00+09:00", "status": "confirmed"}}
    record = SimpleNamespace(collection="places", candidate=poi)

    context = _routing_context([record], RecordedCompleteRouting(), intent)

    assert context.opening_hours["overnight-poi"] == (OpeningInterval(6, time(18), time(1), 1),)

    poi["opening_hours"]["intervals"][0]["opens_at"] = "18:00+09:00"
    malformed_context = _routing_context([record], RecordedCompleteRouting(), intent)
    assert "overnight-poi" not in malformed_context.opening_hours


def test_production_visit_end_uses_elapsed_time_across_dst_fold():
    start = datetime.fromisoformat("2026-11-01T01:30:00-04:00").astimezone(ZoneInfo("America/New_York"))

    end = _add_elapsed_minutes(start, 60)

    assert end.isoformat() == "2026-11-01T01:30:00-05:00"


def test_route_aware_production_accepts_visit_inside_next_day_closing_interval():
    intent = parse_trip_request("2026/11/01到2026/11/02 倉敷兩天一夜，2大，自駕")
    provenance = {"source_type": "provider", "provider": "Recorded Places", "source_url": "https://example.test/places", "retrieved_at": "2026-10-01T00:00:00+09:00", "status": "confirmed"}
    regular_hours = {"status": "fresh", "timezone": "Asia/Tokyo", "intervals": [{"weekday": day, "opens_at": "08:00", "closes_at": "20:00"} for day in range(7)], "provenance": provenance}
    overnight_hours = {"status": "fresh", "timezone": "Asia/Tokyo", "intervals": [{"weekday": day, "opens_at": "18:00", "closes_at": "01:00", "closes_day_offset": 1} for day in range(7)], "provenance": provenance}
    places = [
        {"id": "overnight-first", "name": "First POI", "kind": "poi", "coordinates": {"latitude": 34.6, "longitude": 133.77}, "opening_hours": regular_hours,
         "schedule": {"duration_minutes": 75, "duration_basis": "provider", "day": 1, "selected": True, "required": True, "fixed_start_at": "2026-11-01T09:30:00+09:00", "fixed_end_at": "2026-11-01T10:45:00+09:00"}, "provenance": provenance},
        {"id": "overnight-second", "name": "Night Museum", "kind": "poi", "coordinates": {"latitude": 34.6001, "longitude": 133.77}, "opening_hours": overnight_hours,
         "schedule": {"duration_minutes": 75, "duration_basis": "provider", "day": 1, "selected": True, "required": True, "fixed_start_at": "2026-11-01T18:00:00+09:00", "fixed_end_at": "2026-11-01T19:15:00+09:00"}, "provenance": provenance},
        *[{"id": f"overnight-extra-{index}", "name": f"Extra {index}", "kind": "poi", "coordinates": {"latitude": 34.61 + index / 10000, "longitude": 133.77}, "opening_hours": regular_hours, "provenance": provenance} for index in range(2)],
    ]
    hotel = {"place": {"id": "overnight-hotel", "name": "Recorded hotel", "kind": "hotel", "coordinates": {"latitude": 34.6, "longitude": 133.77}, "provenance": provenance}, "total_cost": {"amount": 10000, "currency": "JPY"}, "check_in": "2026-11-01", "check_out": "2026-11-02", "occupancy": {"adults": 2, "child_ages": [], "rooms": 1}, "price_status": "unverified", "provenance": provenance}
    refs = [PlaceRef(item["id"], item["coordinates"]["latitude"], item["coordinates"]["longitude"]) for item in places]
    refs.append(PlaceRef("overnight-hotel", 34.6, 133.77))
    routes = {(origin.place_id, destination.place_id): 10 for origin in refs for destination in refs if origin != destination}
    opening = {item["id"]: tuple(OpeningInterval(entry["weekday"], time.fromisoformat(entry["opens_at"]), time.fromisoformat(entry["closes_at"]), entry.get("closes_day_offset", 0)) for entry in item["opening_hours"]["intervals"]) for item in places}
    records = [*(SimpleNamespace(collection="places", candidate=item) for item in places), SimpleNamespace(collection="hotels", candidate=hotel)]

    trip, = _candidate_trips("overnight-visit", intent, records, ValidationContext(routes, opening))

    scheduled = next(item for day in trip["days"] for item in day["items"] if item["place_id"] == "overnight-second")
    assert scheduled["start_at"] == "2026-11-01T18:00:00+09:00"
    assert scheduled["end_at"] == "2026-11-01T19:15:00+09:00"



def test_route_aware_production_fails_closed_when_poi_hours_are_missing():
    intent = parse_trip_request("2026/11/01到2026/11/05，倉敷五天四夜，2大，自駕")
    provenance = {"source_type": "provider", "provider": "Recorded Places", "source_url": "https://example.test/places", "retrieved_at": "2026-10-01T00:00:00+09:00", "status": "confirmed"}
    poi_records = [("places", {"id": f"poi-{number}", "name": f"倉敷景點 {number}", "kind": "poi", "coordinates": {"latitude": 34.6, "longitude": 133.77}, "provenance": provenance}) for number in range(12)]
    hotel = {"place": {"id": "hotel", "name": "倉敷旅館", "kind": "hotel", "coordinates": {"latitude": 34.6, "longitude": 133.77}, "provenance": provenance}, "total_cost": {"amount": 1000, "currency": "JPY"}, "check_in": "2026-11-01", "check_out": "2026-11-05", "occupancy": {"adults": 2, "child_ages": [], "rooms": 1}, "provenance": provenance}
    records = [SimpleNamespace(collection=collection, candidate=candidate) for collection, candidate in poi_records]
    records.append(SimpleNamespace(collection="hotels", candidate=hotel))

    for context, expected in (
        (ValidationContext(), "verified opening hours"),
        (ValidationContext({}, {f"poi-{number}": tuple(OpeningInterval(day, time(8), time(22)) for day in range(7)) for number in range(12)}), "no feasible assignment"),
    ):
        try:
            _candidate_trips("kurashiki-missing-facts", intent, records, context)
        except ProductionIncompleteError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"expected incomplete schedule for missing {expected}")



def test_taiwan_domestic_trip_uses_taiwan_context_without_flight_search(tmp_path):
    google = RecordedTaiwanGoogle()
    intent = parse_trip_request("2026/10/20到2026/10/22，台北出發，台灣萬華西門三天兩夜，2大，大眾運輸")
    result = _runner(tmp_path, google=google).run(intent)

    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert google.queries[0].destination == "萬華、西門町"
    assert "flights" not in google.queries[0].categories
    assert trip["local_timezone"] == "Asia/Taipei"
    assert trip["budget"]["currency"] == "TWD"
    assert trip["selected"]["flight_ids"] == []
    assert trip["candidate_sets"]["flights"] == []
    assert trip["candidate_sets"]["hotels"] == []
    assert "hotel" not in trip["budget"]["categories"]
    assert not any("river" in str(constraint).lower() for constraint in trip["preferences"]["hard_constraints"])
    assert "no booking is created" in trip["provenance"]["note"].lower()


def test_production_does_not_query_lodging_even_with_legacy_amadeus_credentials(tmp_path):
    intent = parse_trip_request("2026/10/20到2026/10/22，台灣萬華西門三天兩夜，2大，2間房，雙床房，預算8千元")
    environment = {**ENVIRONMENT, "AMADEUS_CLIENT_ID": "obsolete-id", "AMADEUS_CLIENT_SECRET": "obsolete-secret"}
    result = _runner(tmp_path, google=RecordedTaiwanGoogle(), environment=environment).run(intent)
    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert trip["selected"]["hotel_place_ids"] == []
    assert trip["candidate_sets"]["hotels"] == []


def test_hotel_over_budget_or_unverified_preference_remains_unselected(tmp_path):
    intent = parse_trip_request("2026/10/20到2026/10/22，台灣萬華三天兩夜，2大，預算8千元")
    result = _runner(tmp_path, google=RecordedTaiwanGoogle()).run(intent)
    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert trip["selected"]["hotel_place_ids"] == []
    assert trip["budget"]["total_status"] == "incomplete"

    room_intent = parse_trip_request("2026/10/20到2026/10/22，台灣萬華三天兩夜，2大，雙床房，預算8千元")
    room_result = _runner(tmp_path / "room-type", google=RecordedTaiwanGoogle()).run(room_intent)
    assert room_result.succeeded
    room_trip = json.loads(room_result.trip_path.read_text(encoding="utf-8"))
    assert room_trip["selected"]["hotel_place_ids"] == []


def test_hotel_selection_compares_distance_to_requested_destination_places():
    intent = parse_trip_request("2026/10/20到2026/10/22，台灣萬華西門三天兩夜，2大")
    candidate = lambda hotel_id, latitude, price: {
        "place": {"id": hotel_id, "name": hotel_id, "kind": "hotel", "coordinates": {"latitude": latitude, "longitude": 121.51}},
        "check_in": "2026-10-20", "check_out": "2026-10-22",
        "occupancy": {"adults": 2, "child_ages": [], "rooms": 1},
        "total_cost": {"amount": price, "currency": "TWD"},
    }
    hotels = [candidate("far-cheap", 25.20, 1000), candidate("near-expensive", 25.05, 5000)]
    selected = _select_hotel_candidate(hotels, intent, date(2026, 10, 20), date(2026, 10, 22), [], [
        {"coordinates": {"latitude": 25.04, "longitude": 121.51}},
    ])
    assert selected is hotels[1]
    assert _select_hotel_candidate([hotels[0]], intent, date(2026, 10, 20), date(2026, 10, 22), [], [
        {"coordinates": {"latitude": 25.04, "longitude": 121.51}},
    ]) is None


def test_night_river_view_without_confirmed_viewpoint_evidence_stays_incomplete(tmp_path):
    intent = parse_trip_request("2026/10/20到2026/10/22，台北出發，台灣萬華西門三天兩夜，2大，大眾運輸，晚上看得到河流與夜景")
    result = _runner(tmp_path, google=RecordedTaiwanGoogle()).run(intent)
    assert not result.succeeded
    assert result.trip is None
    validation = result.stage(StageName.VALIDATOR_REPAIR)
    assert validation.status is StageStatus.FAILED
    assert any("no scheduled evening viewpoint has sourced evidence" in warning.message for warning in validation.warnings)


def test_cross_border_trip_links_to_google_flights_without_provider_search(tmp_path):
    intent = parse_trip_request("2026/10/20到2026/10/22，香港出發台灣萬華三天兩夜，2大")
    result = _runner(tmp_path, google=RecordedTaiwanGoogle()).run(intent)

    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert trip["selected"]["flight_ids"] == []
    assert trip["flight_search_url"] == "https://www.google.com/travel/flights?hl=zh-TW"
    assert "香港 → 台灣、萬華" in trip["flight_search_summary"]


def test_unmapped_origin_falls_back_to_google_flights_search_page(tmp_path):
    intent = parse_trip_request("2026/10/20到2026/10/22，台灣萬華三天兩夜，2大")
    intent = replace(intent, origin="未知出發地")
    start, end = date.fromisoformat(intent.start_date), date.fromisoformat(intent.end_date)
    assert _google_flights_search_url(intent, start, end) == "https://www.google.com/travel/flights?hl=zh-TW"
    assert "未知出發地" in _google_flights_search_summary(intent, start, end)
    result = _runner(tmp_path, google=RecordedTaiwanGoogle()).run(intent)
    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert trip["flight_search_url"] == "https://www.google.com/travel/flights?hl=zh-TW"


def test_unsupported_hotel_destination_reports_provider_capability_limit(tmp_path):
    intent = parse_trip_request("2026/10/20到2026/10/22，北海道三天兩夜，2大")
    result = _runner(tmp_path).run(intent)

    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert trip["selected"]["hotel_place_ids"] == []
    research = result.stage(StageName.RESEARCH)
    assert research.status is StageStatus.SUCCEEDED


def test_international_japan_trip_completes_without_live_flight_provider(tmp_path):
    intent = parse_trip_request("2026/4/10到2026/4/14 台北出發德島五天四夜，2大，預算8萬日圓，自駕")
    result = _runner(tmp_path).run(intent)

    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert trip["candidate_sets"]["flights"] == []
    assert "google.com/travel/flights?" in trip["flight_search_url"]



def test_cli_non_demo_invokes_shared_production_composition_not_configuration_ready(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("src.cli.missing_required_configuration", list)
    called = {}
    fake_result = SimpleNamespace(succeeded=True, trip_path=tmp_path / "trips/x/trip.json", render_path=tmp_path / "site/x/index.html", stages=(), warnings=(), trip={"budget": {"currency": "JPY", "categories": {}, "total": {"amount": 0, "currency": "JPY"}, "total_status": "incomplete", "limit_status": "unlimited"}})

    class Runner:
        def run(self, intent):
            called["intent"] = intent
            return fake_result

    with patch("src.cli.create_production_orchestrator", return_value=Runner()) as factory:
        exit_code = plan_command(argparse.Namespace(request="德島五天四夜，2大，預算8萬日圓", trip_id="x", demo=False, trips_directory="trips", site_directory="site"))

    assert exit_code == 0
    assert "intent" in called
    factory.assert_called_once()
    output = capsys.readouterr().out
    assert '"status": "complete"' in output
    assert '"budget_summary": "未設定預算上限；已知費用小計 JPY 0（部分費用尚未取得）"' in output
    assert "configuration_ready" not in output


def test_restaurant_selection_keeps_open_route_verified_candidate_when_first_is_closed():
    from src.application.production import _restaurant_candidates
    from src.validator import ValidationContext

    intent = parse_trip_request("2026/4/10到2026/4/10 台北出發德島一日，1大，自駕")
    candidates = []
    for index in range(7):
        place_id = f"restaurant-{index}"
        provenance = {"source_type": "provider", "provider": "recorded feed", "source_url": f"https://example.test/{index}", "retrieved_at": "2026-04-01T00:00:00+09:00", "status": "confirmed"}
        closed_days = [4] if index == 0 else []
        candidates.append({"place": {"id": place_id, "name": place_id, "kind": "restaurant", "provenance": provenance}, "provenance": provenance,
                           "opening_hours": {"status": "fresh", "timezone": "Asia/Tokyo", "closed_weekdays": closed_days,
                                             "intervals": [{"weekday": day, "opens_at": "07:00", "closes_at": "22:00"} for day in range(7)]}})
    routes = {}
    for candidate in candidates:
        place_id = candidate["place"]["id"]
        routes[("hotel", place_id)] = routes[(place_id, "poi")] = routes[("poi", place_id)] = routes[(place_id, "hotel")] = 5
    selected = _restaurant_candidates(candidates, intent, date(2026, 4, 10), date(2026, 4, 10), ValidationContext(routes), [{"id": "poi"}], "hotel")
    lunch = next(candidate for candidate in selected if candidate.get("schedule", {}).get("meal_period") == "lunch")
    assert lunch["place"]["id"] != "restaurant-0"
    assert lunch["schedule"]["alternatives"]
    assert all(item["hours_verified"] and item["route_verified"] for item in lunch["schedule"]["alternatives"])
    planned = [candidate for candidate in selected if candidate.get("schedule", {}).get("selected") is True]
    assert all(candidate["schedule"].get("day") == 1 for candidate in planned)
    assert len({candidate["schedule"].get("meal_period") for candidate in planned}) == len(planned)
    backup_ids = [item["place_id"] for candidate in planned for item in candidate["schedule"]["alternatives"]]
    assert len(backup_ids) == len(set(backup_ids))
    assert not set(backup_ids).intersection(candidate["place"]["id"] for candidate in planned)
