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


def test_renderer_does_not_show_false_zero_when_trip_budget_is_incomplete():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    trip["budget"]["total"] = {"amount": 0, "currency": trip["budget"]["currency"]}
    trip["budget"]["categories"] = {}
    trip["budget"]["total_status"] = "incomplete"
    html = build_site(trip)
    assert "總額待確認（僅列已知費用小計）" in html
    assert f'{trip["budget"]["currency"]} 0' not in html


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


def test_renderer_projects_restaurant_facts_from_canonical_candidate_for_scheduled_meal():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    restaurant = trip["candidate_sets"]["restaurants"][0]
    restaurant["place"]["id"] = "hakata-food"
    restaurant["place"]["name"] = "博多食堂"
    restaurant["cuisine"] = "博多料理"
    restaurant["price_range"] = "¥1,000–2,000"
    restaurant["provenance"] = {"source_type": "official", "provider": "店家官方網站", "source_url": "https://restaurant.example/menu", "retrieved_at": "2026-10-03T09:00:00+09:00", "status": "reported"}
    trip["days"][0]["items"].append({"id": "lunch", "kind": "meal", "place_id": "hakata-food", "start_at": "2026-04-10T12:00:00+09:00", "end_at": "2026-04-10T13:00:00+09:00"})
    html = build_site(trip)
    assert "博多料理" in html and "¥1,000–2,000" in html
    assert "店家官方網站" in html and "2026-10-03T09:00:00+09:00" in html


def test_renderer_attributes_each_restaurant_field_and_shows_last_order_and_selection_reason():
    trip = json.loads(FIXTURE.read_text(encoding="utf-8"))
    restaurant = trip["candidate_sets"]["restaurants"][0]
    restaurant["place"]["id"] = "hakata-food"
    restaurant["place"]["name"] = "博多食堂"
    restaurant["cuisine"] = "博多料理"
    restaurant["price_range"] = "¥1,000–2,000"
    restaurant["opening_hours"] = {"status": "fresh", "intervals": [{"weekday": 4, "opens_at": "11:00", "closes_at": "20:00", "last_order_at": "19:30"}]}
    restaurant["field_provenance"] = {
        "cuisine": [{"provider": "料理來源", "source_url": "https://example.test/cuisine", "retrieved_at": "2026-10-03T09:00:00+09:00"}],
        "price_range": [{"provider": "價格來源", "source_url": "https://example.test/price", "retrieved_at": "2026-10-03T10:00:00+09:00"}],
        "opening_hours": [{"provider": "營業來源", "source_url": "https://example.test/hours", "retrieved_at": "2026-10-03T11:00:00+09:00"}],
    }
    restaurant["schedule"] = {"duration_minutes": 60, "day": 1, "meal_period": "dinner", "selection_reason": "符合當日晚餐時段且營業與路線已查核。"}
    trip["days"][0]["items"].append({"id": "lunch", "kind": "meal", "place_id": "hakata-food", "start_at": "2026-04-10T18:30:00+09:00", "end_at": "2026-04-10T19:30:00+09:00"})
    html = build_site(trip)
    assert "料理來源" in html and "價格來源" in html and "營業來源" in html
    assert "最後點餐 19:30" in html
    assert "選擇原因：符合當日晚餐時段且營業與路線已查核。" in html
    assert 'href="https://example.test/price"' in html


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
