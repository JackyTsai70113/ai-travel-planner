import json
from datetime import time
from pathlib import Path

from src.intent import parse_trip_request
from src.orchestrator import StageName, StageStatus, TravelOrchestrator, TravelOrchestratorConfig
from src.sources import FixtureCommunityRestaurantAdapter, FixtureOfficialPoiAdapter, SourceAdapter
from src.validator import OpeningInterval, ValidationContext


ROOT = Path(__file__).parents[1]


class FailingAdapter(SourceAdapter):
    name = "fixture-failure"

    def fetch(self, query):
        raise RuntimeError("fixture provider is unavailable")


def _trip():
    return json.loads((ROOT / "fixtures/trips/japan-5-day-trip-v1.json").read_text(encoding="utf-8"))


def _context(intent, store):
    assert tuple(store.records()), "candidate factory must receive researched candidates"
    hours = {place: [OpeningInterval(day, time(8), time(22)) for day in range(7)] for place in ("ohori-park", "dazaifu", "yufuin", "beppu", "canal-city")}
    return ValidationContext({("fuk", "hakata-hotel"): 180, ("yufuin", "beppu"): 60}, hours)


def _factory(intent, store):
    assert tuple(store.records())
    return [_trip()]


def _orchestrator(tmp_path, **overrides):
    values = {
        "adapters": (FixtureOfficialPoiAdapter(), FixtureCommunityRestaurantAdapter()),
        "candidate_trip_factory": _factory,
        "routing_context_factory": _context,
        "output_directory": tmp_path,
    }
    values.update(overrides)
    config = TravelOrchestratorConfig(**values)
    return TravelOrchestrator(config)


def test_fixture_pipeline_emits_canonical_trip_and_rendered_site(tmp_path):
    result = _orchestrator(tmp_path).run(parse_trip_request("2026/4/10到2026/4/14 福岡五天四夜，2大1小，預算20萬日圓"))

    assert result.succeeded
    assert result.trip["schema_version"] == "trip-v1"
    assert result.render_path == tmp_path / "kyushu-family-2026" / "index.html"
    assert result.render_path.exists()
    assert "九州五天四夜親子自駕" in result.render_path.read_text(encoding="utf-8")
    assert all(result.stage(name).status is not StageStatus.PENDING for name in StageName)
    assert result.stage(StageName.CANONICAL_TRIP).status is StageStatus.INCOMPLETE
    assert any(warning.code == "source.unverified" for warning in result.warnings)


def test_partial_research_provider_failure_is_incomplete_but_can_render(tmp_path):
    result = _orchestrator(tmp_path, adapters=(FixtureOfficialPoiAdapter(), FailingAdapter())).run(
        parse_trip_request("福岡五天四夜，2大，預算20萬日圓")
    )

    assert result.succeeded
    assert result.stage(StageName.RESEARCH).status is StageStatus.INCOMPLETE
    assert any(warning.code == "research.provider_failed" for warning in result.warnings)


def test_critical_research_failure_blocks_misleading_final_trip(tmp_path):
    result = _orchestrator(tmp_path, adapters=(FailingAdapter(),)).run(
        parse_trip_request("福岡五天四夜，2大，預算20萬日圓")
    )

    assert not result.succeeded
    assert result.trip is None
    assert result.render_path is None
    assert result.stage(StageName.RESEARCH).status is StageStatus.FAILED
    assert result.stage(StageName.CANDIDATE_STORE).status is StageStatus.PENDING


def test_invalid_validator_result_blocks_canonical_trip_and_renderer(tmp_path):
    result = _orchestrator(tmp_path).run(parse_trip_request("福岡五天四夜，2大，預算1萬日圓"))

    assert not result.succeeded
    assert result.trip is None
    assert result.render_path is None
    assert result.stage(StageName.VALIDATOR_REPAIR).status is StageStatus.FAILED
    assert any(warning.code == "validator.invalid" for warning in result.stage(StageName.VALIDATOR_REPAIR).errors)
    assert result.stage(StageName.CANONICAL_TRIP).status is StageStatus.PENDING
    assert result.stage(StageName.RENDERER).status is StageStatus.PENDING


def test_repair_exhaustion_is_machine_readable_and_blocks_final_trip(tmp_path):
    def invalid_factory(intent, store):
        trip = _trip()
        trip["days"][3]["items"][1]["start_at"] = "2026-04-13T11:00:00+09:00"
        return [trip]

    result = TravelOrchestrator(TravelOrchestratorConfig(
        adapters=(FixtureOfficialPoiAdapter(),),
        candidate_trip_factory=invalid_factory,
        routing_context_factory=_context,
        output_directory=tmp_path,
        max_repair_iterations=0,
    )).run(parse_trip_request("福岡五天四夜，2大，預算20萬日圓"))

    assert not result.succeeded
    report = result.stage(StageName.VALIDATOR_REPAIR)
    assert report.status is StageStatus.FAILED
    assert any(warning.code == "repair.exhausted" for warning in report.errors)
    assert any(warning.code == "time.overlap" for warning in report.warnings)


def test_retry_is_bounded_and_records_actual_attempts(tmp_path):
    attempts = {"routing": 0}

    def flaky_routing(intent, store):
        attempts["routing"] += 1
        if attempts["routing"] == 1:
            raise RuntimeError("temporary fixture routing failure")
        return _context(intent, store)

    result = _orchestrator(tmp_path, routing_context_factory=flaky_routing, max_stage_attempts=2).run(
        parse_trip_request("福岡五天四夜，2大，預算20萬日圓")
    )

    assert result.succeeded
    assert attempts["routing"] == 2
    assert result.stage(StageName.ROUTING).attempts == 2
