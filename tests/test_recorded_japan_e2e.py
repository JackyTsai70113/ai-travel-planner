"""Offline five-day Japan pipeline scenario using recorded provider-shaped data."""

from __future__ import annotations

import copy
import json
from datetime import datetime, time, timezone
from pathlib import Path

from src.intent import parse_trip_request
from src.orchestrator import StageName, StageStatus, TravelOrchestrator, TravelOrchestratorConfig
from src.restaurant_intelligence import validation_opening_hours
from src.sources import GooglePlacesAdapter
from src.validator import BudgetLimit, OpeningInterval, ValidationContext


ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 10, 8, tzinfo=timezone.utc)


class RecordedGoogleClient:
    """Recorded Google Places API (New) payloads; no test makes a network call."""

    def __init__(self):
        self.responses = [
            {"places": [{
                "id": "tokushima-park", "displayName": {"text": "德島中央公園"},
                "formattedAddress": "Tokushima", "googleMapsUri": "https://maps.example.test/tokushima-park",
                "location": {"latitude": 34.07, "longitude": 134.55},
            }]},
            {"places": [{
                "id": "tokushima-family-dining", "displayName": {"text": "親子食堂"},
                "rating": 4.4, "userRatingCount": 218, "primaryType": "japanese_restaurant",
                "googleMapsUri": "https://maps.example.test/tokushima-family-dining",
                "timeZone": {"id": "Asia/Tokyo"},
                "regularOpeningHours": {"periods": [
                    # Monday lunch/dinner split; no Wednesday interval.
                    {"open": {"day": 1, "hour": 11}, "close": {"day": 1, "hour": 14}},
                    {"open": {"day": 1, "hour": 17}, "close": {"day": 1, "hour": 21}},
                ]},
            }]},
        ]

    def request_json(self, method, url, *, headers, body=None):
        assert method == "POST"
        assert headers["X-Goog-Api-Key"] == "recorded-google-key"
        return self.responses.pop(0)


def _fixture_trip() -> dict:
    return json.loads((ROOT / "fixtures/trips/japan-5-day-trip-v1.json").read_text(encoding="utf-8"))


def _context(_: object, store: object) -> ValidationContext:
    restaurants = [record.candidate for record in store.records() if record.collection == "restaurants"]
    regular_hours = {
        place_id: [OpeningInterval(day, time(8), time(22)) for day in range(7)]
        for place_id in ("ohori-park", "dazaifu", "yufuin", "beppu", "canal-city")
    }
    return ValidationContext(
        travel_minutes={
            ("fuk", "hakata-hotel"): 180,
            ("yufuin", "beppu"): 60,
            ("beppu", "google-tokushima-family-dining"): 60,
        },
        opening_hours={**regular_hours, **validation_opening_hours(restaurants)},
        budget_limit=BudgetLimit(200000, "JPY"),
    )


def _recorded_candidate_factory(_: object, store: object) -> list[dict]:
    trip = copy.deepcopy(_fixture_trip())
    restaurant = next(record.candidate for record in store.records() if record.collection == "restaurants")
    trip["candidate_sets"]["restaurants"] = [restaurant]
    trip["candidate_sets"]["places"].append(restaurant["place"])
    trip["days"][3]["items"].append({
        "id": "monday-family-dinner", "kind": "meal", "place_id": restaurant["place"]["id"],
        "start_at": "2026-04-13T17:30:00+09:00", "end_at": "2026-04-13T18:30:00+09:00",
        "selection_status": "selected",
    })
    return [trip]


def test_recorded_five_day_japan_pipeline_runs_candidates_routing_budget_validation_and_renderer(tmp_path):
    adapter = GooglePlacesAdapter("recorded-google-key", http_client=RecordedGoogleClient(), now=NOW)
    result = TravelOrchestrator(TravelOrchestratorConfig(
        adapters=(adapter,), candidate_trip_factory=_recorded_candidate_factory,
        routing_context_factory=_context, output_directory=tmp_path,
    )).run(parse_trip_request("幫我規劃 5 天 4 夜德島＋神戶，2 大 1 個 2 歲小孩，台北出發，自駕，不要太累，預算 20 萬日圓。"))

    assert result.succeeded
    assert result.trip is not None
    assert result.trip["schema_version"] == "trip-v1"
    assert result.trip["candidate_sets"]["restaurants"][0]["rating"] == 4.4
    assert result.trip["budget"]["total"]["amount"] == 169000
    assert result.render_path == tmp_path / "kyushu-family-2026" / "index.html"
    assert result.render_path.exists()
    assert result.stage(StageName.ROUTING).status is StageStatus.SUCCEEDED
    assert result.stage(StageName.VALIDATOR_REPAIR).status is StageStatus.SUCCEEDED
    assert "recorded-google-key" not in result.render_path.read_text(encoding="utf-8")


def test_insufficient_recorded_route_blocks_final_renderer(tmp_path):
    def insufficient_context(intent, store):
        context = _context(intent, store)
        return ValidationContext(
            travel_minutes={**context.travel_minutes, ("yufuin", "beppu"): 180},
            opening_hours=context.opening_hours,
            budget_limit=context.budget_limit,
        )

    result = TravelOrchestrator(TravelOrchestratorConfig(
        adapters=(GooglePlacesAdapter("recorded-google-key", http_client=RecordedGoogleClient(), now=NOW),),
        candidate_trip_factory=_recorded_candidate_factory, routing_context_factory=insufficient_context,
        output_directory=tmp_path, max_repair_iterations=0,
    )).run(parse_trip_request("德島＋神戶五天四夜，2大1小，預算20萬日圓"))

    assert not result.succeeded
    assert result.render_path is None
    assert result.stage(StageName.VALIDATOR_REPAIR).status is StageStatus.FAILED
    assert any(warning.code == "travel_time.insufficient" for warning in result.stage(StageName.VALIDATOR_REPAIR).warnings)
