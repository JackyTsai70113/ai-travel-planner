from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.application.production import ProductionDependencies, create_production_orchestrator
from src.cli import plan_command
from src.intent import parse_trip_request
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

    def fetch(self, query):
        now = "2026-01-01T00:00:00+09:00"
        provenance = {"source_type": "provider", "provider": "Recorded Google Places", "source_url": "https://example.test/places", "retrieved_at": now, "status": "confirmed"}
        places = [("places", {"id": f"poi-{number}", "name": f"POI {number}", "kind": "poi", "coordinates": {"latitude": 34.0 + number / 100, "longitude": 134.0}, "provenance": provenance}) for number in range(5)]
        restaurant = {"place": {"id": "restaurant-1", "name": "Open restaurant", "kind": "restaurant", "coordinates": {"latitude": 34.1, "longitude": 134.1}, "provenance": provenance}, "rating": 4.5, "review_count": 100, "opening_hours": {"status": "fresh", "timezone": "Asia/Tokyo", "intervals": [{"weekday": day, "opens_at": "09:00", "closes_at": "21:00"} for day in range(7)]}, "provenance": provenance}
        return [*places, ("restaurants", restaurant)]


class RecordedYouTube:
    def fetch_evidence(self, query):
        return []


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


def _runner(tmp_path):
    dependencies = ProductionDependencies(
        google=RecordedGoogle(), youtube=RecordedYouTube(),
        amadeus_client=AmadeusClient(_transport, ENVIRONMENT), routing_provider=FixtureRoutingProvider(()),
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
    assert "google-secret" not in persisted
    assert "amadeus-secret" not in persisted
    assert result.render_path.exists()


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
