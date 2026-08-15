import json
from pathlib import Path

from src.golden_trip_renderer.build_site import build_site


FIXTURE = Path("fixtures/trips/japan-5-day-trip-v1.json")


def test_golden_trip_renderer_includes_required_views_without_repairing_itinerary_facts():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    html = build_site(trip)
    required_ids = [
        'id="critical"',
        'id="itinerary"',
        'id="routing"',
        'id="reservations"',
        'id="restaurants"',
        'id="flights-hotels"',
        'id="budget"',
        'id="weather"',
        'id="alternatives"',
        'id="sources"',
        'id="sources-list"',
        'id="operations"',
        'id="share"',
    ]
    for marker in required_ids:
        assert marker in html
    assert "trip status" in html.lower()
    assert "reported" in html and "estimated" in html
    assert "window.print()" in html


def test_golden_trip_renderer_highlights_critical_alerts_and_navigation_links():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    trip["validation"] = [{"code": "safety.warning", "message": "山區夜間建議避免開車", "severity": "warning", "status": "unverified"}]
    html = build_site(trip)
    assert "safety.warning" in html
    assert "待確認" in html
    assert "Google Maps 導航" in html
    assert "每日快速導覽" in html
