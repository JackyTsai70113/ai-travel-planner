from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime, time, timezone
import json
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.application.production import ProductionDependencies, ProductionIncompleteError, _candidate_trips, _google_flights_search_summary, _google_flights_search_url, _select_hotel_candidate, create_production_orchestrator
from src.cli import plan_command
from src.intent import parse_trip_request
from src.orchestrator import StageName, StageStatus
from src.planner import schedule as route_aware_schedule
from src.schemas import validate_trip
from src.sources import AmadeusClient, SourceAdapter
from src.sources.routing import PlaceRef, Route, RouteMode, RouteProvenance, RouteStatus
from src.validator import OpeningInterval, ValidationContext


ENVIRONMENT = {
    "GOOGLE_MAPS_API_KEY": "google-secret",
    "YOUTUBE_API_KEY": "youtube-secret",
    "AMADEUS_CLIENT_ID": "amadeus-id",
    "AMADEUS_CLIENT_SECRET": "amadeus-secret",
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


def _transport(method, url, headers, body):
    if url.endswith("/v1/security/oauth2/token"):
        return 200, {"access_token": "recorded-token"}
    if "flight-offers" in url:
        return 200, {"data": [{"id": "offer-1", "itineraries": [{"segments": [{"carrierCode": "CI", "number": "1", "departure": {"iataCode": "TPE", "at": "2026-04-10T08:00:00"}, "arrival": {"iataCode": "TKS", "at": "2026-04-10T12:00:00"}}]}], "price": {"grandTotal": "1000", "currency": "JPY"}}]}
    if "locations/hotels/by-city" in url:
        return 200, {"data": [{"hotelId": "H1"}]}
    if "hotel-offers" in url:
        return 200, {"data": [{"hotel": {"hotelId": "H1", "name": "Recorded hotel", "latitude": 34.1, "longitude": 134.2}, "offers": [{"id": "hotel-offer", "price": {"total": "2000", "currency": "JPY"}}]}]}
    raise AssertionError(url)


def _runner(tmp_path, *, youtube=None, google=None, transport=_transport):
    dependencies = ProductionDependencies(
        google=google or RecordedGoogle(), youtube=youtube or RecordedYouTube(),
        amadeus_client=AmadeusClient(transport, ENVIRONMENT), routing_provider=RecordedCompleteRouting(),
    )
    return create_production_orchestrator(
        trip_id="recorded-trip", trips_directory=tmp_path / "trips", site_directory=tmp_path / "site",
        environment=ENVIRONMENT, dependencies=dependencies,
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
    assert "amadeus-secret" not in persisted
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
            amadeus_client=AmadeusClient(_transport, ENVIRONMENT),
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

    assert not result.succeeded
    assert intent.budget_status == "unlimited"
    assert any("hotel search is not available for this destination" in warning.message for warning in result.stage(StageName.RESEARCH).warnings)


def test_kurashiki_five_day_fixture_schedules_multiple_pois_per_day_without_provider_durations():
    request = "日本岡山縣倉敷五天四夜。日期：2026/11/01～2026/11/05。出發地：桃園國際機場。旅客：6位成人、1位2歲幼兒。預算：暫不設限制。交通方式：自駕。"
    intent = parse_trip_request(request)
    provenance = {"source_type": "provider", "provider": "Recorded Places", "source_url": "https://example.test/places", "retrieved_at": "2026-10-01T00:00:00+09:00", "status": "confirmed"}
    hours = {"status": "fresh", "timezone": "Asia/Tokyo", "intervals": [{"weekday": day, "opens_at": "08:00", "closes_at": "22:00"} for day in range(7)], "provenance": provenance}
    anchors = {
        0: {"duration_minutes": 75, "duration_basis": "provider", "day": 1, "selected": True, "required": True, "fixed_start_at": "2026-11-01T09:30:00+09:00", "fixed_end_at": "2026-11-01T10:45:00+09:00"},
        1: {"duration_minutes": 75, "duration_basis": "provider", "day": 1, "selected": True, "required": True, "fixed_start_at": "2026-11-01T14:00:00+09:00", "fixed_end_at": "2026-11-01T15:15:00+09:00"},
    }
    poi_records = [("places", {"id": f"kurashiki-poi-{number}", "name": f"倉敷景點 {number}", "kind": "poi", "primary_type": "museum", "coordinates": {"latitude": 34.6 + number / 10000, "longitude": 133.77}, "opening_hours": hours, **({"schedule": anchors[number]} if number in anchors else {}), "provenance": provenance}) for number in range(12)]
    hotel = {"place": {"id": "kurashiki-hotel", "name": "Recorded Kurashiki hotel", "kind": "hotel", "coordinates": {"latitude": 34.6, "longitude": 133.77}, "provenance": provenance}, "total_cost": {"amount": 1000, "currency": "JPY"}, "check_in": "2026-11-01", "check_out": "2026-11-05", "occupancy": {"adults": 6, "child_ages": [2], "rooms": 1}, "price_status": "unverified", "provenance": provenance}
    refs = [PlaceRef(candidate["id"], candidate["coordinates"]["latitude"], candidate["coordinates"]["longitude"]) for _, candidate in poi_records]
    refs.append(PlaceRef("kurashiki-hotel", 34.6, 133.77))
    routes = {(origin.place_id, destination.place_id): 10 for origin in refs for destination in refs if origin != destination}
    opening = {ref.place_id: tuple(OpeningInterval(day, time(8), time(22)) for day in range(7)) for ref in refs if ref.place_id != "kurashiki-hotel"}

    with patch("src.application.production.schedule", wraps=route_aware_schedule) as scheduler:
        trip, = _candidate_trips("kurashiki-recorded", intent, [*map(lambda pair: SimpleNamespace(collection=pair[0], candidate=pair[1]), poi_records), SimpleNamespace(collection="hotels", candidate=hotel)], ValidationContext(routes, opening))
    scheduler.assert_called_once()
    validate_trip(trip)

    visits_by_day = [[item for item in day["items"] if item["kind"] == "visit"] for day in trip["days"]]
    assert len(poi_records) >= 10
    assert all(len(visits) >= 2 for visits in visits_by_day)
    assert trip["candidate_sets"]["places"][0]["schedule"]["duration_basis"] == "provider"
    assert trip["candidate_sets"]["places"][0]["schedule"]["fixed_start_at"] == "2026-11-01T09:30:00+09:00"
    assert trip["candidate_sets"]["places"][1]["schedule"]["fixed_start_at"] == "2026-11-01T14:00:00+09:00"
    assert all(trip["candidate_sets"]["places"][number]["schedule"]["duration_basis"] == "planning_estimate" for number in range(2, 12))
    assert all(item["end_at"] > item["start_at"] for day in visits_by_day for item in day)
    assert trip["budget"]["limit_status"] == "unlimited"
    assert "limit" not in trip["budget"]
    assert trip["budget"]["total_status"] == "incomplete"



def test_route_aware_production_fails_closed_when_poi_hours_are_missing():
    intent = parse_trip_request("2026/11/01到2026/11/05，倉敷五天四夜，2大，自駕")
    provenance = {"source_type": "provider", "provider": "Recorded Places", "source_url": "https://example.test/places", "retrieved_at": "2026-10-01T00:00:00+09:00", "status": "confirmed"}
    poi_records = [("places", {"id": f"poi-{number}", "name": f"倉敷景點 {number}", "kind": "poi", "coordinates": {"latitude": 34.6, "longitude": 133.77}, "provenance": provenance}) for number in range(12)]
    hotel = {"place": {"id": "hotel", "name": "倉敷旅館", "kind": "hotel", "coordinates": {"latitude": 34.6, "longitude": 133.77}, "provenance": provenance}, "total_cost": {"amount": 1000, "currency": "JPY"}, "check_in": "2026-11-01", "check_out": "2026-11-05", "occupancy": {"adults": 2, "child_ages": [], "rooms": 1}, "provenance": provenance}
    records = [SimpleNamespace(collection=collection, candidate=candidate) for collection, candidate in poi_records]
    records.append(SimpleNamespace(collection="hotels", candidate=hotel))

    with pytest.raises(ProductionIncompleteError, match="verified opening hours"):
        _candidate_trips("kurashiki-missing-hours", intent, records, ValidationContext())

    opening = {f"poi-{number}": tuple(OpeningInterval(day, time(8), time(22)) for day in range(7)) for number in range(12)}
    with pytest.raises(ProductionIncompleteError, match="no feasible pair"):
        _candidate_trips("kurashiki-missing-routes", intent, records, ValidationContext({}, opening))



def test_taiwan_domestic_trip_uses_taiwan_context_without_flight_search(tmp_path):
    calls = []

    def taiwan_transport(method, url, headers, body):
        calls.append(url)
        if url.endswith("/v1/security/oauth2/token"):
            return 200, {"access_token": "recorded-token"}
        if "flight-offers" in url:
            raise AssertionError("Taiwan domestic trips must not search international flights")
        if "locations/hotels/by-city" in url:
            assert "cityCode=TPE" in url
            return 200, {"data": [{"hotelId": "H1"}]}
        if "hotel-offers" in url:
            return 200, {"data": [{"hotel": {"hotelId": "H1", "name": "Recorded Taipei hotel", "latitude": 25.04, "longitude": 121.51}, "offers": [{"id": "hotel-offer", "price": {"total": "2000", "currency": "TWD"}}]}]}
        raise AssertionError(url)

    google = RecordedTaiwanGoogle()
    intent = parse_trip_request("2026/10/20到2026/10/22，台北出發，台灣萬華西門三天兩夜，2大，大眾運輸")
    result = _runner(tmp_path, google=google, transport=taiwan_transport).run(intent)

    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert "flight-offers" not in " ".join(calls)
    assert google.queries[0].destination == "萬華、西門町"
    assert "flights" not in google.queries[0].categories
    assert trip["local_timezone"] == "Asia/Taipei"
    assert trip["budget"]["currency"] == "TWD"
    assert trip["selected"]["flight_ids"] == []
    assert trip["candidate_sets"]["flights"] == []
    assert set(trip["budget"]["categories"]) == {"hotel"}
    hotel_query = next(url for url in calls if "hotel-offers" in url)
    assert "checkInDate=2026-10-20" in hotel_query
    assert "checkOutDate=2026-10-22" in hotel_query
    assert trip["candidate_sets"]["hotels"][0]["check_in"] == "2026-10-20"
    assert trip["candidate_sets"]["hotels"][0]["check_out"] == "2026-10-22"
    assert trip["candidate_sets"]["hotels"][0]["occupancy"] == {"adults": 2, "child_ages": [], "rooms": 1}
    assert "taxes_fees" not in trip["candidate_sets"]["hotels"][0]
    assert "tax inclusion" in trip["candidate_sets"]["hotels"][0]["provenance"]["note"]
    assert "one-room search is preliminary" in trip["candidate_sets"]["hotels"][0]["provenance"]["note"]
    assert trip["candidate_sets"]["hotels"][0]["price_status"] == "unverified"
    assert "cancellation_policy" not in trip["candidate_sets"]["hotels"][0]
    assert not any("river" in str(constraint).lower() for constraint in trip["preferences"]["hard_constraints"])
    assert "no booking is created" in trip["provenance"]["note"].lower()


def test_hotel_selection_is_price_ranked_and_unqualified_stays_pending(tmp_path):
    calls = []

    def hotels_transport(method, url, headers, body):
        calls.append(url)
        if url.endswith("/v1/security/oauth2/token"):
            return 200, {"access_token": "recorded-token"}
        if "locations/hotels/by-city" in url:
            return 200, {"data": [{"hotelId": "H-expensive"}, {"hotelId": "H-cheap"}]}
        if "hotel-offers" in url:
            return 200, {"data": [
                {"hotel": {"hotelId": "H-expensive", "name": "Expensive Taipei", "latitude": 25.04, "longitude": 121.51}, "offers": [{"id": "expensive", "price": {"total": "7000", "currency": "TWD"}, "room": {"typeEstimated": {"category": "STANDARD_ROOM"}}}]},
                {"hotel": {"hotelId": "H-cheap", "name": "Affordable Taipei", "latitude": 25.05, "longitude": 121.52}, "offers": [{"id": "cheap", "price": {"total": "4000", "currency": "TWD"}, "room": {"typeEstimated": {"category": "TWIN_BED"}}}]},
            ]}
        raise AssertionError(url)

    intent = parse_trip_request("2026/10/20到2026/10/22，台灣萬華西門三天兩夜，2大，2間房，雙床房，預算8千元")
    result = _runner(tmp_path, google=RecordedTaiwanGoogle(), transport=hotels_transport).run(intent)
    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert trip["selected"]["hotel_place_ids"] == ["amadeus-hotel-h-cheap"]
    assert trip["budget"]["categories"]["hotel"]["amount"] == 4000
    selected_candidate = next(item for item in trip["candidate_sets"]["hotels"] if item["place"]["id"] == trip["selected"]["hotel_place_ids"][0])
    assert selected_candidate["room_type"] == "TWIN_BED"
    assert selected_candidate["occupancy"]["rooms"] == 2
    assert "roomQuantity=2" in next(url for url in calls if "hotel-offers" in url)


def test_hotel_over_budget_or_unverified_preference_remains_unselected(tmp_path):
    def hotels_transport(method, url, headers, body):
        if url.endswith("/v1/security/oauth2/token"):
            return 200, {"access_token": "recorded-token"}
        if "locations/hotels/by-city" in url:
            return 200, {"data": [{"hotelId": "H1"}]}
        if "hotel-offers" in url:
            return 200, {"data": [{"hotel": {"hotelId": "H1", "name": "Generic Taipei hotel", "latitude": 25.04, "longitude": 121.51}, "offers": [{"id": "hotel-offer", "price": {"total": "9000", "currency": "TWD"}}]}]}
        raise AssertionError(url)

    intent = parse_trip_request("2026/10/20到2026/10/22，台灣萬華三天兩夜，2大，預算8千元")
    result = _runner(tmp_path, google=RecordedTaiwanGoogle(), transport=hotels_transport).run(intent)
    assert not result.succeeded
    assert any("selected lodging candidate" in error.message for error in result.stage(StageName.PLANNER).errors)

    def untyped_room_transport(method, url, headers, body):
        if url.endswith("/v1/security/oauth2/token"):
            return 200, {"access_token": "recorded-token"}
        if "locations/hotels/by-city" in url:
            return 200, {"data": [{"hotelId": "H1"}]}
        if "hotel-offers" in url:
            return 200, {"data": [{"hotel": {"hotelId": "H1", "name": "Generic Taipei hotel", "latitude": 25.04, "longitude": 121.51}, "offers": [{"id": "hotel-offer", "price": {"total": "4000", "currency": "TWD"}}]}]}
        raise AssertionError(url)

    room_intent = parse_trip_request("2026/10/20到2026/10/22，台灣萬華三天兩夜，2大，雙床房，預算8千元")
    room_result = _runner(tmp_path / "room-type", google=RecordedTaiwanGoogle(), transport=untyped_room_transport).run(room_intent)
    assert not room_result.succeeded
    assert any("selected lodging candidate" in error.message for error in room_result.stage(StageName.PLANNER).errors)


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

    def taiwan_transport(method, url, headers, body):
        if url.endswith("/v1/security/oauth2/token"):
            return 200, {"access_token": "recorded-token"}
        if "locations/hotels/by-city" in url:
            return 200, {"data": [{"hotelId": "H1"}]}
        if "hotel-offers" in url:
            return 200, {"data": [{"hotel": {"hotelId": "H1", "name": "Recorded Taipei hotel", "latitude": 25.04, "longitude": 121.51}, "offers": [{"id": "hotel-offer", "price": {"total": "2000", "currency": "TWD"}}]}]}
        raise AssertionError(url)

    result = _runner(tmp_path, google=RecordedTaiwanGoogle(), transport=taiwan_transport).run(intent)
    assert not result.succeeded
    assert result.trip is None
    validation = result.stage(StageName.VALIDATOR_REPAIR)
    assert validation.status is StageStatus.FAILED
    assert any("no scheduled evening viewpoint has sourced evidence" in warning.message for warning in validation.warnings)


def test_cross_border_trip_links_to_google_flights_without_provider_search(tmp_path):
    calls = []

    def cross_border_transport(method, url, headers, body):
        calls.append(url)
        if url.endswith("/v1/security/oauth2/token"):
            return 200, {"access_token": "recorded-token"}
        if "flight-offers" in url:
            return 200, {"data": [{"id": "hk-tpe", "itineraries": [{"segments": [{"carrierCode": "CX", "number": "400", "departure": {"iataCode": "HKG", "at": "2026-10-20T08:00:00"}, "arrival": {"iataCode": "TPE", "at": "2026-10-20T10:00:00"}}]}], "price": {"grandTotal": "3000", "currency": "TWD"}}]}
        if "locations/hotels/by-city" in url:
            return 200, {"data": [{"hotelId": "H1"}]}
        if "hotel-offers" in url:
            return 200, {"data": [{"hotel": {"hotelId": "H1", "name": "Recorded Taipei hotel", "latitude": 25.04, "longitude": 121.51}, "offers": [{"id": "hotel-offer", "price": {"total": "2000", "currency": "TWD"}}]}]}
        raise AssertionError(url)

    intent = parse_trip_request("2026/10/20到2026/10/22，香港出發台灣萬華三天兩夜，2大")
    result = _runner(tmp_path, google=RecordedTaiwanGoogle(), transport=cross_border_transport).run(intent)

    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert "flight-offers" not in " ".join(calls)
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
    assert not result.succeeded
    assert any("selected lodging candidate" in error.message for error in result.stage(StageName.PLANNER).errors)


def test_unsupported_hotel_destination_reports_provider_capability_limit(tmp_path):
    intent = parse_trip_request("2026/10/20到2026/10/22，北海道三天兩夜，2大")
    result = _runner(tmp_path).run(intent)

    assert not result.succeeded
    research = result.stage(StageName.RESEARCH)
    assert research.status is StageStatus.INCOMPLETE
    assert any("hotel search is not available for this destination" in warning.message for warning in research.warnings)


def test_international_japan_trip_completes_without_live_flight_provider(tmp_path):
    calls = []

    def no_flight_offers(method, url, headers, body):
        calls.append(url)
        if "flight-offers" in url:
            return 200, {"data": []}
        return _transport(method, url, headers, body)

    intent = parse_trip_request("2026/4/10到2026/4/14 台北出發德島五天四夜，2大，預算8萬日圓，自駕")
    result = _runner(tmp_path, transport=no_flight_offers).run(intent)

    assert "flight-offers" not in " ".join(calls)
    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert trip["candidate_sets"]["flights"] == []
    assert "google.com/travel/flights?" in trip["flight_search_url"]



def test_cli_non_demo_invokes_shared_production_composition_not_configuration_ready(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("src.cli.missing_required_configuration", lambda: [])
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


def test_legacy_breakfast_is_omitted_when_route_would_overlap_first_poi():
    from src.application.production import _schedule_legacy_meals
    from src.validator import ValidationContext

    restaurant = {"place": {"id": "breakfast-shop", "name": "早餐店"}, "opening_hours": {"status": "fresh", "timezone": "Asia/Taipei", "intervals": [{"weekday": day, "opens_at": "06:00", "closes_at": "20:00"} for day in range(7)]}, "provenance": {"source_type": "provider", "provider": "recorded", "retrieved_at": "2026-01-01T00:00:00+08:00"}}
    trip = {"local_timezone": "Asia/Taipei", "selected": {"hotel_place_ids": ["hotel"]}, "candidate_sets": {"restaurants": [restaurant]}, "days": [{"date": "2026-04-10", "items": [{"id": "poi", "kind": "visit", "place_id": "poi", "start_at": "2026-04-10T10:00:00+08:00", "end_at": "2026-04-10T12:00:00+08:00"}]}]}
    routes = {("hotel", "breakfast-shop"): 45, ("breakfast-shop", "poi"): 45}
    _schedule_legacy_meals(trip, [restaurant], ValidationContext(travel_minutes=routes))
    assert all(item["kind"] != "meal" for item in trip["days"][0]["items"])


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
