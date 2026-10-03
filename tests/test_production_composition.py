from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.application.production import ProductionDependencies, ProductionIncompleteError, _attach_timed_transport_legs, _routing_context, _select_hotel_candidate, create_production_orchestrator
from src.cli import plan_command
from src.intent import parse_trip_request
from src.orchestrator import StageName, StageStatus
from src.sources import AmadeusClient, SourceAdapter
from src.sources.routing import FixtureRoutingProvider, Route, RouteMode, RouteProvenance, RouteStatus, RouteStep
from src.schemas import validate_trip
from src.planner import SchedulingInput, ScheduleState, schedule
from src.planner.scheduler import _route_time_description
from src.validator import OpeningInterval, RouteConstraint, ValidationContext


ENVIRONMENT = {
    "GOOGLE_MAPS_API_KEY": "google-secret",
    "YOUTUBE_API_KEY": "youtube-secret",
    "AMADEUS_CLIENT_ID": "amadeus-id",
    "AMADEUS_CLIENT_SECRET": "amadeus-secret",
    "OPENROUTESERVICE_API_KEY": "ors-secret",
}


def test_transit_route_time_language_distinguishes_source_verification_status():
    assert _route_time_description("confirmed") == "已確認"
    assert _route_time_description("estimated") == "估計"
    assert _route_time_description("unverified") == "未驗證"


class RecordedGoogle(SourceAdapter):
    name = "recorded-google"

    def __init__(self):
        self.queries = []

    def fetch(self, query):
        self.queries.append(query)
        now = "2026-01-01T00:00:00+09:00"
        provenance = {"source_type": "provider", "provider": "Recorded Google Places", "source_url": "https://example.test/places", "retrieved_at": now, "status": "confirmed"}
        places = [("places", {"id": f"poi-{number}", "name": f"POI {number}", "kind": "poi", "coordinates": {"latitude": 34.0 + number / 100, "longitude": 134.0}, "provenance": provenance}) for number in range(5)]
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


class BrokenYouTube(RecordedYouTube):
    def fetch_evidence(self, query):
        raise RuntimeError("recorded YouTube timeout")


class RecordedTransitRoutingProvider(FixtureRoutingProvider):
    def __init__(self):
        super().__init__(())
        self.modes = []

    def fetch(self, origin, destination, mode):
        self.modes.append(mode)
        assert mode is RouteMode.TRANSIT
        return Route(origin, destination, mode, RouteStatus.AVAILABLE,
                     RouteProvenance("recorded transit", datetime(2026, 1, 1, tzinfo=timezone.utc)), 300, 1000)

    def fetch_at(self, origin, destination, mode, departure_at):
        self.modes.append(mode)
        assert mode is RouteMode.TRANSIT
        arrival_at = departure_at + timedelta(minutes=5)
        return Route(origin, destination, mode, RouteStatus.AVAILABLE,
                     RouteProvenance("recorded transit", datetime(2026, 1, 1, tzinfo=timezone.utc)),
                     300, 1000, departure_at, arrival_at, (RouteStep("bus", departure_at, arrival_at, "A", "B", "R1"),))


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


def _runner(tmp_path, *, youtube=None, google=None, transport=_transport, routing_provider=None):
    dependencies = ProductionDependencies(
        google=google or RecordedGoogle(), youtube=youtube or RecordedYouTube(),
        amadeus_client=AmadeusClient(transport, ENVIRONMENT), routing_provider=routing_provider or FixtureRoutingProvider(()),
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
    assert trip["selected"]["flight_ids"] == ["amadeus-flight-offer-1"]
    assert trip["local_timezone"] == "Asia/Tokyo"
    assert trip["budget"]["currency"] == "JPY"
    assert "google-secret" not in persisted
    assert "amadeus-secret" not in persisted
    assert result.render_path.exists()


def test_transit_request_keeps_transit_mode_and_preserves_unsupported_status():
    class RecordingRoutingProvider(FixtureRoutingProvider):
        def __init__(self):
            super().__init__(())
            self.modes = []

        def fetch(self, origin, destination, mode):
            self.modes.append(mode)
            return super().fetch(origin, destination, mode)

        def fetch_at(self, origin, destination, mode, departure_at):
            self.modes.append(mode)
            return super().fetch_at(origin, destination, mode, departure_at)

    provider = RecordingRoutingProvider()
    records = [
        SimpleNamespace(collection="places", candidate={"id": place_id, "coordinates": {"latitude": 25.0, "longitude": 121.0 + index / 100}})
        for index, place_id in enumerate(("origin", "destination"))
    ]
    intent = parse_trip_request("2026/4/10到2026/4/10 台北一日，大眾運輸")

    context = _routing_context(records, provider, intent)
    travel = context.travel_minutes_for("origin", "destination", datetime(2026, 4, 10, 7, tzinfo=timezone.utc))

    assert provider.modes
    assert set(provider.modes) == {RouteMode.TRANSIT}
    assert travel is None
    assert context.travel_minutes == {}
    assert context.timed_route_facts[("origin", "destination", "2026-04-10T07:00:00+00:00")].status == "unsupported"


def test_transit_request_with_unsupported_provider_does_not_emit_complete_trip(tmp_path):
    intent = parse_trip_request("2026/10/20到2026/10/20，台北出發，台灣萬華一日，2大，大眾運輸")
    result = _runner(tmp_path, google=RecordedTaiwanGoogle()).run(intent)

    assert not result.succeeded
    planner = result.stage(StageName.PLANNER)
    assert planner.status is StageStatus.FAILED
    assert any("unsupported" in error.message and "no walking fallback" in error.message for error in planner.errors)


def test_mixed_transport_uses_explicit_transit_steps_instead_of_walking_fallback():
    class RecordingRoutingProvider(FixtureRoutingProvider):
        def __init__(self):
            super().__init__(())
            self.modes = []

        def fetch_at(self, origin, destination, mode, departure_at):
            self.modes.append(mode)
            return super().fetch_at(origin, destination, mode, departure_at)

    provider = RecordingRoutingProvider()
    records = [SimpleNamespace(collection="places", candidate={"id": place_id, "coordinates": {"latitude": 25.0, "longitude": 121.0 + index / 100}})
               for index, place_id in enumerate(("origin", "destination"))]
    intent = parse_trip_request("2026/4/10到2026/4/10 台北一日，混合交通")

    context = _routing_context(records, provider, intent)
    assert context.route_lookup is not None
    assert context.travel_minutes_for("origin", "destination", datetime(2026, 4, 10, 7, tzinfo=timezone.utc)) is None
    assert provider.modes == [RouteMode.TRANSIT]


def test_transit_scheduler_adjusts_day_start_after_last_service_and_verifies_return():
    class LastServiceRoutingProvider(RecordedTransitRoutingProvider):
        def __init__(self):
            super().__init__()
            self.departures = []

        def fetch_at(self, origin, destination, mode, departure_at):
            self.departures.append((origin.place_id, destination.place_id, departure_at))
            if origin.place_id != "hakata-hotel" and departure_at.hour >= 20:
                return Route(origin, destination, mode, RouteStatus.NO_ROUTE,
                             RouteProvenance("recorded transit", datetime(2026, 4, 10, 20, tzinfo=timezone.utc)))
            return super().fetch_at(origin, destination, mode, departure_at)

    trip = json.loads((Path(__file__).parents[1] / "fixtures/trips/japan-5-day-trip-v1.json").read_text())
    poi = next(place for place in trip["candidate_sets"]["places"] if place["id"] == "ohori-park")
    trip["candidate_sets"]["places"] = [poi]
    trip["days"] = []
    poi["coordinates"] = {"latitude": 33.5932, "longitude": 130.3769}
    poi["schedule"] = {"duration_minutes": 475, "day": 1, "required": True}
    trip["candidate_sets"]["restaurants"] = []
    trip["date_range"] = {"start_date": "2026-04-10", "end_date": "2026-04-10"}
    hotel_id = trip["selected"]["hotel_place_ids"][0]
    hotel = next(candidate["place"] for candidate in trip["candidate_sets"]["hotels"] if candidate["place"]["id"] == hotel_id)
    hotel["coordinates"] = {"latitude": 33.5902, "longitude": 130.4207}
    records = [SimpleNamespace(collection="places", candidate=poi),
               SimpleNamespace(collection="hotels", candidate={"place": hotel})]
    provider = LastServiceRoutingProvider()
    intent = parse_trip_request("2026/4/10到2026/4/10 福岡一日，大眾運輸")
    context = _routing_context(records, provider, intent)
    context = replace(context, opening_hours={poi["id"]: tuple(OpeningInterval(day, datetime.min.time(), datetime.max.time()) for day in range(7))})

    result = schedule(SchedulingInput(trip, context, daily_start="12:00", daily_end="22:00"))

    assert result.best_trip is not None
    assert result.best_trip.state is ScheduleState.READY
    assert result.candidates[1].state is ScheduleState.FAILED
    assert any(violation.code == "schedule.hotel_return_unverified" for violation in result.candidates[1].violations)
    adjustment = next(violation for violation in result.best_trip.violations
                      if violation.code == "schedule.daily_start_adjustment")
    assert adjustment.context["requested_daily_start"] == "12:00"
    assert adjustment.context["adjusted_daily_start"] == "11:45"
    assert adjustment.context["return_departure_at"] == "2026-04-10T19:45:00+09:00"
    assert adjustment.context["return_arrival_at"] == "2026-04-10T19:50:00+09:00"
    assert adjustment.context["mode"] == "transit"
    assert adjustment.context["verification_status"] == "estimated"
    assert "路線為估計時刻" in adjustment.message
    assert any(item["code"] == "schedule.daily_start_adjustment"
               for item in result.best_trip.trip["validation"])
    validate_trip(result.best_trip.trip)
    assert any(origin == poi["id"] and destination == hotel_id and departure.hour == 20
               for origin, destination, departure in provider.departures)
    projected = json.loads(json.dumps(result.best_trip.trip))
    _attach_timed_transport_legs(projected, context, intent,
                                 daily_start=adjustment.context["adjusted_daily_start"])
    projected_legs = [leg for leg in projected["candidate_sets"]["transport_legs"]
                      if leg["id"].startswith("transit-day1-")]
    assert len(projected_legs) == 2
    assert projected_legs[0]["departure_at"] == "2026-04-10T11:45:00+09:00"
    assert projected_legs[-1]["arrival_at"] == adjustment.context["return_arrival_at"]


def test_transit_scheduler_rejects_later_actual_service_arriving_after_daily_end():
    class DelayedServiceProvider(RecordedTransitRoutingProvider):
        def fetch_at(self, origin, destination, mode, departure_at):
            if origin.place_id == "hakata-hotel":
                return super().fetch_at(origin, destination, mode, departure_at)
            if departure_at.hour >= 20:
                return Route(origin, destination, mode, RouteStatus.NO_ROUTE,
                             RouteProvenance("recorded transit", datetime(2026, 4, 10, 20, tzinfo=timezone.utc)))
            actual_departure = datetime(2026, 4, 10, 20, 15, tzinfo=departure_at.tzinfo)
            actual_arrival = datetime(2026, 4, 10, 21, 5, tzinfo=departure_at.tzinfo)
            return Route(origin, destination, mode, RouteStatus.AVAILABLE,
                         RouteProvenance("recorded transit", datetime(2026, 4, 10, 20, tzinfo=timezone.utc)),
                         3000, 1000, actual_departure, actual_arrival,
                         (RouteStep("bus", actual_departure, actual_arrival, "A", "B", "R1"),))

    trip = json.loads((Path(__file__).parents[1] / "fixtures/trips/japan-5-day-trip-v1.json").read_text())
    poi = next(place for place in trip["candidate_sets"]["places"] if place["id"] == "ohori-park")
    trip["candidate_sets"]["places"] = [poi]
    trip["days"] = []
    poi["coordinates"] = {"latitude": 33.5932, "longitude": 130.3769}
    poi["schedule"] = {"duration_minutes": 475, "day": 1, "required": True}
    trip["candidate_sets"]["restaurants"] = []
    trip["date_range"] = {"start_date": "2026-04-10", "end_date": "2026-04-10"}
    hotel_id = trip["selected"]["hotel_place_ids"][0]
    hotel = next(candidate["place"] for candidate in trip["candidate_sets"]["hotels"] if candidate["place"]["id"] == hotel_id)
    hotel["coordinates"] = {"latitude": 33.5902, "longitude": 130.4207}
    records = [SimpleNamespace(collection="places", candidate=poi),
               SimpleNamespace(collection="hotels", candidate={"place": hotel})]
    context = _routing_context(records, DelayedServiceProvider(),
                               parse_trip_request("2026/4/10到2026/4/10 福岡一日，大眾運輸"))
    context = replace(context, opening_hours={poi["id"]: tuple(OpeningInterval(day, datetime.min.time(), datetime.max.time()) for day in range(7))})

    result = schedule(SchedulingInput(trip, context, daily_start="12:00", daily_end="21:00"))

    assert result.best_trip is None
    assert all(item.code != "schedule.daily_start_adjustment"
               for candidate in result.candidates for item in candidate.violations)


def test_transit_schedule_exports_same_timed_routes_into_canonical_trip_and_public_leg_contract():
    trip = json.loads((Path(__file__).parents[1] / "fixtures/trips/japan-5-day-trip-v1.json").read_text())
    poi_id = next(place["id"] for place in trip["candidate_sets"]["places"] if place.get("kind") == "poi")
    trip["days"] = [{"date": "2026-04-10", "items": [{
        "id": "d1-visit", "kind": "visit", "place_id": poi_id,
        "start_at": "2026-04-10T10:00:00+09:00", "end_at": "2026-04-10T12:00:00+09:00",
        "selection_status": "selected",
    }]}]
    hotel_id = trip["selected"]["hotel_place_ids"][0]
    start = datetime.fromisoformat("2026-04-10T07:00:00+09:00")
    visit_end = datetime.fromisoformat("2026-04-10T12:00:00+09:00")
    retrieved = datetime.fromisoformat("2026-04-10T06:00:00+09:00")

    def fact(departure):
        arrival = departure + timedelta(minutes=5)
        return RouteConstraint(status="verified", minutes=5, source_status="confirmed", mode="mixed",
                               departure_at=departure, arrival_at=arrival, wait_seconds=120, transfer_count=1,
                               steps=({"mode": "walk", "departure_at": departure.isoformat(), "arrival_at": (departure + timedelta(minutes=1)).isoformat()},
                                      {"mode": "train", "departure_at": (departure + timedelta(minutes=2)).isoformat(), "arrival_at": arrival.isoformat(), "departure_stop": "A", "arrival_stop": "B", "line_name": "R1"}),
                               provider="recorded Google Routes", source_url="https://routes.googleapis.com/directions/v2:computeRoutes", retrieved_at=retrieved)

    context = ValidationContext(route_lookup=lambda *_: None, timed_route_facts={
        (hotel_id, poi_id, start.isoformat()): fact(start),
        (poi_id, hotel_id, visit_end.isoformat()): fact(visit_end),
    })
    intent = parse_trip_request("2026/4/10到2026/4/14，德島五天四夜，混合交通")

    _attach_timed_transport_legs(trip, context, intent)
    validate_trip(trip)

    legs = trip["candidate_sets"]["transport_legs"][-2:]
    assert [leg["mode"] for leg in legs] == ["mixed", "mixed"]
    assert [leg["transfer_count"] for leg in legs] == [1, 1]
    assert all(leg["verification_status"] == "confirmed" for leg in legs)
    assert all(leg["provenance"]["provider"] == "recorded Google Routes" for leg in legs)
    transport_items = [item for day in trip["days"] for item in day["items"] if item["kind"] == "transport"]
    assert len(transport_items) == 2
    assert [item["transport_leg_id"] for item in transport_items] == [leg["id"] for leg in legs]


def test_nested_provider_failure_is_visible_to_orchestrator_without_losing_trip(tmp_path):
    intent = parse_trip_request("2026/4/10到2026/4/14 台北出發德島五天四夜，2大，預算8萬日圓，自駕")
    result = _runner(tmp_path, youtube=BrokenYouTube()).run(intent)

    assert result.succeeded
    research = result.stage(StageName.RESEARCH)
    assert research.status is StageStatus.INCOMPLETE
    assert any(
        warning.code == "research.provider_failed"
        and "recorded-youtube" in warning.message
        and "recorded YouTube timeout" in warning.message
        for warning in research.warnings
    )


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
    intent = parse_trip_request("2026/10/20到2026/10/22，台北出發，台灣萬華西門三天兩夜，2大，自駕")
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
    assert result.succeeded
    trip = json.loads(result.trip_path.read_text(encoding="utf-8"))
    assert trip["selected"]["hotel_place_ids"] == []
    assert trip["candidate_sets"]["hotels"]
    assert "hotel" not in trip["budget"]["categories"]
    assert trip["budget"]["total_status"] == "incomplete"
    assert "remains unselected" in trip["provenance"]["note"]
    assert "總額待確認" in result.render_path.read_text(encoding="utf-8")

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
    assert room_result.succeeded
    room_trip = json.loads(room_result.trip_path.read_text(encoding="utf-8"))
    assert room_trip["selected"]["hotel_place_ids"] == []
    assert room_trip["candidate_sets"]["hotels"]


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
    intent = parse_trip_request("2026/10/20到2026/10/22，台北出發，台灣萬華西門三天兩夜，2大，自駕，晚上看得到河流與夜景")

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


def test_cross_border_hong_kong_to_taiwan_still_searches_flight(tmp_path):
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
    assert "flight-offers" in " ".join(calls)
    assert trip["selected"]["flight_ids"] == ["amadeus-flight-hk-tpe"]


def test_unsupported_explicit_origin_fails_before_provider_calls(tmp_path):
    google = RecordedTaiwanGoogle()
    intent = parse_trip_request("2026/10/20到2026/10/22，台灣萬華三天兩夜，2大")
    intent = replace(intent, origin="新加坡")

    try:
        _runner(tmp_path, google=google).run(intent)
    except Exception as exc:
        assert "flight search is not available for origin '新加坡'" in str(exc)
    else:
        raise AssertionError("unsupported explicit origin must fail clearly")
    assert google.queries == []


def test_unsupported_hotel_destination_reports_provider_capability_limit(tmp_path):
    intent = parse_trip_request("2026/10/20到2026/10/22，北海道三天兩夜，2大")
    result = _runner(tmp_path).run(intent)

    assert not result.succeeded
    research = result.stage(StageName.RESEARCH)
    assert research.status is StageStatus.INCOMPLETE
    assert any("hotel search is not available for this destination" in warning.message for warning in research.warnings)


def test_international_japan_trip_stays_incomplete_without_flight_candidates(tmp_path):
    calls = []

    def no_flight_offers(method, url, headers, body):
        calls.append(url)
        if "flight-offers" in url:
            return 200, {"data": []}
        return _transport(method, url, headers, body)

    intent = parse_trip_request("2026/4/10到2026/4/14 台北出發德島五天四夜，2大，預算8萬日圓，自駕")
    result = _runner(tmp_path, transport=no_flight_offers).run(intent)

    assert "flight-offers" in " ".join(calls)
    assert not result.succeeded
    assert result.trip is None


def test_unknown_provider_airport_code_does_not_assume_japan_timezone():
    from src.application.production import ProductionIncompleteError, _airport_timezone

    try:
        _airport_timezone("SIN")
    except ProductionIncompleteError as exc:
        assert "without a timezone mapping: SIN" in str(exc)
    else:
        raise AssertionError("unknown airports must not receive a guessed timezone")


def test_cli_non_demo_invokes_shared_production_composition_not_configuration_ready(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("src.cli.missing_required_configuration", lambda: [])
    called = {}
    fake_result = SimpleNamespace(succeeded=True, trip_path=tmp_path / "trips/x/trip.json", render_path=tmp_path / "site/x/index.html", stages=(), warnings=())

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
