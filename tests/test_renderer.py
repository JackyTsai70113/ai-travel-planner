import json
from pathlib import Path

from src.renderer.build_site import build_site


FIXTURE = Path("fixtures/trips/japan-5-day-trip-v1.json")


def test_renderer_shows_core_views_and_provenance_state():
    html = build_site(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert "總覽" in html and "行程" in html and "預算" in html
    assert "博多家庭飯店" in html
    assert "JPY 169,000" in html
    assert "reported" in html
    assert "source freshness:" in html
    assert "目前沒有上游 validation warning" in html


def test_renderer_displays_upstream_validation_without_evaluating_it():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    trip["validation"] = [{"code": "schedule_conflict", "message": "由 validator 提供"}]
    assert "schedule_conflict" in build_site(trip)


def test_renderer_displays_required_restaurant_attribution():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    trip["candidate_sets"]["restaurants"][0]["attributions"] = [
        "Powered by ホットペッパーグルメ Webサービス",
    ]
    html = build_site(trip)
    assert "Powered by ホットペッパーグルメ Webサービス" in html
    assert html.count("Powered by ホットペッパーグルメ Webサービス") == 1
