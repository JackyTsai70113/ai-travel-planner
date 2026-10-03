from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.application.production import ProductionDependencies, create_production_orchestrator
from src.cli import plan_command
from src.intent import parse_trip_request
from src.orchestrator import StageName, StageStatus
from src.sources import AmadeusClient, SourceAdapter
from src.sources.routing import FixtureRoutingProvider


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
        amadeus_client=AmadeusClient(transport, ENVIRONMENT), routing_provider=FixtureRoutingProvider(()),
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
    assert all(
        item["start_at"].endswith("+08:00") and item["end_at"].endswith("+08:00")
        for day in trip["days"] for item in day["items"]
    )


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
