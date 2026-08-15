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
    assert 'Powered by <a href="http://webservice.recruit.co.jp/">ホットペッパーグルメ Webサービス</a>' in html
    assert html.count("ホットペッパーグルメ Webサービス") == 1


def test_renderer_escapes_unrecognized_restaurant_attribution():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    trip["candidate_sets"]["restaurants"][0]["attributions"] = ["<script>alert(1)</script>"]
    html = build_site(trip)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_renderer_shows_contact_navigation_and_clarification():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    place = next(item for item in trip["candidate_sets"]["places"] if item["id"] == "dazaifu")
    place["resolution"] = {"state": "clarification_required", "confidence": 0.4, "clarification": "請確認預約分店"}
    html = build_site(trip)
    assert "tel:+81-92-922-8225" in html
    assert "導航點：" in html and "太宰府駐車中心" in html
    assert "Mapcode 55 333 807*70" in html
    assert "需要確認：請確認預約分店" in html


def test_renderer_does_not_create_links_for_unsafe_urls_or_phone_values():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    place = next(item for item in trip["candidate_sets"]["places"] if item["id"] == "dazaifu")
    place["google_maps_url"] = "javascript:alert(1)"
    place["phone"] = '123\" onclick=\"alert(1)'
    place["navigation_points"] = [{
        "id": "unsafe-point",
        "kind": "entrance",
        "name": "<img src=x onerror=alert(1)>",
        "google_maps_url": "data:text/html,bad",
    }]
    html = build_site(trip)
    assert 'href="javascript:' not in html
    assert 'href="data:' not in html
    assert 'href="tel:123' not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<img src=x onerror=alert(1)>" not in html


def test_renderer_allows_https_google_maps_and_safe_phone_links():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    place = next(item for item in trip["candidate_sets"]["places"] if item["id"] == "dazaifu")
    place["google_maps_url"] = "https://maps.google.com/?q=dazaifu&mode=walk"
    html = build_site(trip)
    assert 'href="https://maps.google.com/?q=dazaifu&amp;mode=walk"' in html
    assert 'href="tel:+81-92-922-8225"' in html
