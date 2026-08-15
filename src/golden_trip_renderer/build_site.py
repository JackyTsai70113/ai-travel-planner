"""Golden Trip Website static renderer for Canonical Trip V1 documents."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote
from typing import Any


def build_site(trip: dict[str, Any], derived: dict[str, Any] | None = None) -> str:
    """Render a mobile-first, offline-friendly Trip V1 website."""
    del derived  # compatibility placeholder for callers that pass a derived model.
    places = {place.get("id"): place for place in trip.get("candidate_sets", {}).get("places", []) if isinstance(place, dict)}
    days = trip.get("days", [])
    validation = _as_list(trip.get("validation"))
    weather = _as_list(trip.get("weather"))
    candidate_sets = trip.get("candidate_sets", {})
    selected = trip.get("selected", {})
    title = escape(str(trip.get("title", "Trip")))

    day_sections = "".join(_render_day(day, idx + 1, places) for idx, day in enumerate(days))
    quick_nav = "".join(
        f'<a href="#day-{idx + 1}">{escape(_day_label(day, idx + 1))}</a>'
        for idx, day in enumerate(days)
    ) or "<span>尚未產生行程</span>"
    validation_rows = "".join(_render_validation_row(item) for item in validation)
    validation_summary = validation_rows or '<li class="quiet">目前沒有上游 validation warning。</li>'
    budget_rows = "".join(_render_budget_row(key, value) for key, value in trip.get("budget", {}).get("categories", {}).items())
    total_budget = _money(trip.get("budget", {}).get("total"))
    flight_rows = "".join(_render_flight(flight, selected.get("flight_ids", []), places) for flight in candidate_sets.get("flights", []))
    hotel_rows = "".join(_render_hotel(hotel, selected.get("hotel_place_ids", []), places) for hotel in candidate_sets.get("hotels", []))
    transport_rows = "".join(_render_leg(leg, places) for leg in candidate_sets.get("transport_legs", []))
    meal_sections = "".join(_render_meal(day, places, candidate_sets) for day in days)
    source_rows = "".join(_render_provenance(item, key) for key, item in _all_candidates_with_group(candidate_sets))
    reservations = _render_reservations(trip, candidate_sets)
    restaurant_rows = _render_restaurants(candidate_sets.get("restaurants", []), places)
    weather_rows = "".join(_render_weather_entry(entry) for entry in weather) or "<p class='quiet'>未提供氣象動態。</p>"
    route_links = "".join(_render_route_link(leg, places) for leg in candidate_sets.get("transport_legs", []))
    critical_alerts = "".join(
        f'<li class="critical">{_field_text(item.get("message", item))}</li>'
        for item in validation
        if str(item.get("severity", "")).lower() in {"error", "critical"}
    ) or '<li class="quiet">目前無 critical alerts。</li>'
    status_badge = _trip_status_chip(validation)
    trip_start = escape(str(trip.get("date_range", {}).get("start_date", "—")))
    trip_end = escape(str(trip.get("date_range", {}).get("end_date", "—")))
    trip_dates = f"{trip_start} ～ {trip_end}"
    local_currency = escape(str(trip.get("budget", {}).get("currency", "JPY")))
    operations = _normalize_block(trip.get("operations", {}))
    handbook = _normalize_block(trip.get("handbook", {}))
    emergency = _normalize_block(trip.get("emergency", {}))
    alternatives = _normalize_block(trip.get("alternatives", {}))
    return f"""<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <style>{_CSS}</style>
  </head>
  <body>
    <main class="frame">
      <header>
        <p class="eyebrow">Golden Trip Website</p>
        <h1>{title}</h1>
        <p>Trip status: {status_badge}</p>
        <div class="trip-meta">旅遊日期：{trip_dates}</div>
        <div class="trip-meta">預設幣別：{local_currency}</div>
      </header>

      <section id="critical">
        <h2>Overview / Critical alerts / Trip status</h2>
        <ul class="alerts">{critical_alerts}</ul>
        <p>行程狀態：{status_badge}</p>
      </section>

      <nav aria-label="daily quick navigation">
        <p>每日快速導覽</p>
        <div class="day-nav">{quick_nav}</div>
      </nav>

      <section id="itinerary">
        <h2>Detailed day itinerary</h2>
        {day_sections or '<p class="quiet">尚未產生每日行程。</p>'}
      </section>

      <section id="routing">
        <h2>Map / Daily route / Navigation links</h2>
        <div class="route-grid">{route_links}</div>
        <table>
          <thead>
            <tr><th>起點</th><th>終點</th><th>交通</th><th>出發</th><th>抵達</th><th>來源狀態</th><th>地圖</th></tr>
          </thead>
          <tbody>{transport_rows}</tbody>
        </table>
      </section>

      <section id="reservations">
        <h2>Reservations</h2>
        {reservations}
      </section>

      <section id="restaurants">
        <h2>Restaurants / Meals / Opening hours / Alternatives</h2>
        {restaurant_rows}
        {meal_sections}
      </section>

      <section id="flights-hotels">
        <h2>Flights / Hotels / Transportation</h2>
        <h3>Flights</h3>
        <table>
          <thead><tr><th>航班</th><th>起點</th><th>目的地</th><th>起飛</th><th>降落</th><th>票價</th></tr></thead>
          <tbody>{flight_rows}</tbody>
        </table>
        <h3>Hotels</h3>
        <table>
          <thead><tr><th>飯店</th><th>入住</th><th>退房</th><th>每晚</th><th>泊車</th></tr></thead>
          <tbody>{hotel_rows}</tbody>
        </table>
      </section>

      <section id="budget">
        <h2>Budget</h2>
        <table><tbody>{budget_rows}</tbody></table>
        <p class="subtotal">Total: {total_budget}</p>
      </section>

      <section id="weather">
        <h2>Weather / Dynamic conditions</h2>
        {weather_rows}
      </section>

      <section id="alternatives">
        <h2>Alternatives / Rain plan</h2>
        {_render_block_with_fallback(alternatives, "未提供備案與替代路線。")}
      </section>

      <section id="sources">
        <h2>Research / Provenance / Freshness</h2>
        <div class="source-grid">{source_rows}</div>
      </section>

      <section id="sources-list">
        <h2>Validation / Unverified facts</h2>
        <ul>{validation_summary}</ul>
      </section>

      <section id="operations">
        <h2>Operations / Handbook / Emergency / Japanese</h2>
        <div class="two-col">
          <article>{_render_block_with_fallback(operations, "未提供 Operations 資訊。")}</article>
          <article>{_render_block_with_fallback(handbook, "未提供行前手冊。")}</article>
          <article>{_render_block_with_fallback(emergency, "未提供緊急聯絡。")}</article>
        </div>
      </section>

      <section id="share">
        <h2>Printable / Shareable summary</h2>
        <p>可離線瀏覽本頁，必要時使用列印共用。</p>
        <button onclick="window.print()">列印行程摘要</button>
      </section>
    </main>
    <footer>Generated from Canonical Trip only · all dynamic facts keep provenance and status</footer>
  </body>
</html>
"""


def _as_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _trip_status_chip(validation: list[dict[str, Any]]) -> str:
    if any(item.get("severity") in {"error", "critical"} for item in validation):
        return '<span class=\"chip critical\">需人工確認</span>'
    if any(_is_unverified(item) for item in validation):
        return '<span class=\"chip warning\">待確認</span>'
    if validation:
        return '<span class=\"chip\">已完成</span>'
    return '<span class=\"chip success\">可執行（含風險告知）</span>'


def _is_unverified(item: dict[str, Any]) -> bool:
    status = str(item.get("status", "")).lower()
    severity = str(item.get("severity", "")).lower()
    return status == "unverified" or severity in {"warning", "info"} or "unverified" in str(item.get("code", "")).lower()


def _field_text(value: Any) -> str:
    if isinstance(value, dict):
        return escape(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return escape(str(value))


def _day_label(day: dict[str, Any], index: int) -> str:
    return day.get("summary") or day.get("date") or f"Day {index}"


def _render_day(day: dict[str, Any], day_index: int, places: dict[str, dict[str, Any]]) -> str:
    date = escape(str(day.get("date", "")))
    title = escape(str(day.get("summary", "")))
    if not isinstance(day.get("items"), list):
        return f'<article id="day-{day_index}" class="day-card"><h3>{title}</h3><p class="date">{date}</p><p class="quiet">該日沒有行程</p></article>'
    items = []
    for item in day.get("items", []):
        if not isinstance(item, dict):
            continue
        place = places.get(item.get("place_id", ""), {})
        place_name = escape(str(place.get("name", item.get("place_id", "—"))))
        start = _time(item.get("start_at"))
        end = _time(item.get("end_at"))
        kind = escape(str(item.get("kind", "活動")))
        status = escape(str(item.get("selection_status", "selected")))
        duration = ""
        if start or end:
            duration = f"<span>{start} ~ {end}</span>"
        items.append(
            f"<li><strong>{place_name}</strong><span>{kind}</span>"
            f"{duration}<small>{status}</small></li>"
        )
    body = "".join(items) or "<li class=\"quiet\">該日目前為空</li>"
    return f'<article id="day-{day_index}" class="day-card"><p class="date">{date}</p><h3>{title}</h3><ol>{body}</ol></article>'


def _render_route_link(leg: dict[str, Any], places: dict[str, dict[str, Any]]) -> str:
    from_name = _place_name(places, leg.get("from_place_id"))
    to_name = _place_name(places, leg.get("to_place_id"))
    url = _maps_url(leg.get("from_place_id"), leg.get("to_place_id"), places)
    status = _status_badge(leg.get("provenance", {}).get("status", "estimated"))
    return f"<p>{from_name} → {to_name}：{status} <a href=\"{url}\" target=\"_blank\" rel=\"noopener\">Google Maps 導航</a></p>"


def _render_leg(leg: dict[str, Any], places: dict[str, dict[str, Any]]) -> str:
    if not isinstance(leg, dict):
        return ""
    from_place = _place_name(places, leg.get("from_place_id"))
    to_place = _place_name(places, leg.get("to_place_id"))
    return f"""<tr><td>{from_place}</td><td>{to_place}</td><td>{escape(str(leg.get('mode', '—')))}</td><td>{_time(leg.get('departure_at'))}</td><td>{_time(leg.get('arrival_at'))}</td><td>{_status_badge(leg.get('provenance', {}).get('status', 'estimated'))}</td><td><a href=\"{_maps_url(leg.get('from_place_id'), leg.get('to_place_id'), places)}\" target=\"_blank\" rel=\"noopener\">路線</a></td></tr>"""


def _render_reservations(trip: dict[str, Any], candidate_sets: dict[str, Any]) -> str:
    selected_flights = set(trip.get("selected", {}).get("flight_ids", []))
    selected_hotels = set(trip.get("selected", {}).get("hotel_place_ids", []))
    rows = []
    for flight in candidate_sets.get("flights", []):
        if not isinstance(flight, dict):
            continue
        if str(flight.get("id")) not in {str(item) for item in selected_flights}:
            continue
        rows.append(f"<p>{escape(flight.get('carrier', '未提供航司'))} {escape(str(flight.get('flight_number', '未提供航班號')))}（訂位：{_flight_reservation(flight)}）</p>")
    for hotel in candidate_sets.get("hotels", []):
        if not isinstance(hotel, dict):
            continue
        place = hotel.get("place", {})
        if str(place.get("id")) not in {str(item) for item in selected_hotels}:
            continue
        rows.append(f"<p>{escape(place.get('name', '未提供酒店'))}（保留狀態：{_reservation_label(place.get('reservation_required'))}）</p>")
    return "".join(rows) or "<p class='quiet'>目前未看到已選保留資訊。</p>"


def _flight_reservation(flight: dict[str, Any]) -> str:
    if flight.get("cancellation_policy"):
        return "需確認退改"
    return "待確認"


def _reservation_label(value: Any) -> str:
    if value is True:
        return "需預約"
    if value is False:
        return "可即時入住"
    return "待確認"


def _render_meal(day: dict[str, Any], places: dict[str, dict[str, Any]], candidate_sets: dict[str, Any]) -> str:
    restaurant_index = {
        candidate.get("place", {}).get("id"): candidate
        for candidate in candidate_sets.get("restaurants", [])
        if isinstance(candidate, dict)
    }
    meals = []
    for item in day.get("items", []):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", ""))
        if "meal" not in kind and kind not in {"lunch", "breakfast", "dinner"}:
            continue
        place = places.get(item.get("place_id", ""), {})
        candidate = restaurant_index.get(place.get("id"), {})
        opening = _format_interval(candidate.get("opening_hours", {}))
        meals.append(
            f'<div class="meal"><h4>{escape(place.get("name", item.get("place_id", "未指定餐廳")))}</h4>'
            f'<p>時間 {_time(item.get("start_at"))} - {_time(item.get("end_at"))}</p>'
            f'<p>價位：{escape(str(candidate.get("price_range", "未提供")))}</p>'
            f'<p>營業：{opening}</p></div>'
        )
    return "".join(meals)


def _render_restaurants(restaurants: list[dict[str, Any]], places: dict[str, dict[str, Any]]) -> str:
    if not restaurants:
        return "<p class='quiet'>目前無餐廳候選。</p>"
    cards = []
    for restaurant in restaurants:
        if not isinstance(restaurant, dict):
            continue
        place = restaurant.get("place", {})
        name = escape(str(place.get("name", "未提供")))
        wait = restaurant.get("wait_risk", "unknown")
        child = "是" if restaurant.get("child_friendly") else "否"
        cards.append(f"<article><h4>{name}</h4><p>候補狀態：{_status_badge(place.get('provenance', {}).get('status', 'reported'))}</p><p>是否需預約：{_reservation_label(restaurant.get('reservation_required'))}</p><p>輪候風險：{escape(str(wait))}</p><p>親子友善：{child}</p></article>")
    return "".join(cards)


def _render_flight(flight: dict[str, Any], selected_ids: list[str], places: dict[str, dict[str, Any]]) -> str:
    if not isinstance(flight, dict):
        return ""
    dep = flight.get("departure", {})
    arr = flight.get("arrival", {})
    selected = ' class="selected"' if flight.get("id") in selected_ids else ""
    return (
        f"<tr><td>{escape(str(flight.get('carrier', '')))} {escape(str(flight.get('flight_number', '')))}{selected}</td>"
        f"<td>{_place_name(places, dep.get('place_id'))}</td><td>{_place_name(places, arr.get('place_id'))}</td>"
        f"<td>{_time(dep.get('at'))}</td><td>{_time(arr.get('at'))}</td>"
        f"<td>{_money(flight.get('cost'))}</td></tr>"
    )


def _render_hotel(hotel: dict[str, Any], selected_ids: list[str], places: dict[str, dict[str, Any]]) -> str:
    if not isinstance(hotel, dict):
        return ""
    place = hotel.get("place", {})
    selected = " (selected)" if place.get("id") in selected_ids else ""
    parking = "有" if hotel.get("parking_available") else "否"
    return (
        f"<tr><td>{escape(str(place.get('name', '未提供')))}{escape(selected)}</td>"
        f"<td>{escape(str(hotel.get('check_in', '未提供')))}</td><td>{escape(str(hotel.get('check_out', '未提供')))}</td>"
        f"<td>{_money(hotel.get('nightly_cost'))}</td><td>{parking}</td></tr>"
    )


def _render_budget_row(label: str, value: dict[str, Any]) -> str:
    if not isinstance(value, dict):
        return ""
    return f"<tr><th>{escape(label)}</th><td>{_money(value)}</td></tr>"


def _render_validation_row(item: dict[str, Any]) -> str:
    code = escape(str(item.get("code", "warning")))
    message = escape(str(item.get("message", "")))
    severity = _status_badge(item.get("severity", "warning"))
    return f"<li>{severity} {code}：{message}</li>"


def _render_provenance(item: dict[str, Any], group: str) -> str:
    provenance = item.get("provenance") or item.get("place", {}).get("provenance", {})
    if not isinstance(provenance, dict):
        return ""
    place_name = item.get("place", {}).get("name")
    fallback_name = place_name if place_name else item.get("id", "—")
    name = escape(str(item.get("name", fallback_name)))
    provider = escape(str(provenance.get("provider", "未提供")))
    status = _status_badge(provenance.get("status", "unverified"))
    retrieved = escape(str(provenance.get("retrieved_at", "unknown")))
    source_url = str(provenance.get("source_url", ""))
    source = f'<a href="{escape(source_url, quote=True)}">source</a>' if source_url else "source unknown"
    return f"<article><p><strong>{name}</strong></p><p>Group: {escape(group)} {status}</p><p>{provider} · {source} · retrieved: {retrieved}</p></article>"


def _render_weather_entry(entry: dict[str, Any]) -> str:
    if not isinstance(entry, dict):
        return ""
    return f"<p>{escape(str(entry.get('date', '—')))}：{escape(str(entry.get('description', '未提供')))} / {escape(str(entry.get('risk', 'unknown')))}</p>"


def _normalize_block(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _render_block_with_fallback(value: dict[str, Any], fallback: str) -> str:
    if not value:
        return f"<p class='quiet'>{fallback}</p>"
    lines = [f"<li>{escape(str(v))}</li>" for v in value.values() if isinstance(v, str)]
    if not lines:
        return "<p class='quiet'>" + escape(fallback) + "</p>"
    return "<ul>" + "".join(lines) + "</ul>"


def _all_candidates_with_group(candidate_sets: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    result = []
    for group, candidates in candidate_sets.items():
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if isinstance(candidate, dict):
                result.append((group, candidate))
    return result


def _maps_url(from_place_id: Any, to_place_id: Any, places: dict[str, dict[str, Any]]) -> str:
    from_id = str(from_place_id) if from_place_id is not None else ""
    to_id = str(to_place_id) if to_place_id is not None else ""
    from_coords = places.get(from_id, {})
    to_coords = places.get(to_id, {})
    if (
        isinstance(from_coords, dict)
        and isinstance(from_coords.get("coordinates"), dict)
        and isinstance(to_coords, dict)
        and isinstance(to_coords.get("coordinates"), dict)
    ):
        origin = "{},{}".format(
            from_coords["coordinates"].get("latitude", ""),
            from_coords["coordinates"].get("longitude", ""),
        )
        destination = "{},{}".format(
            to_coords["coordinates"].get("latitude", ""),
            to_coords["coordinates"].get("longitude", ""),
        )
        return f"https://www.google.com/maps/dir/?api=1&origin={quote(str(origin))}&destination={quote(str(destination))}"
    origin = quote(_place_plain_name(places, from_id))
    destination = quote(_place_plain_name(places, to_id))
    return f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}"


def _place_name(places: dict[str, dict[str, Any]], place_id: Any) -> str:
    return escape(_place_plain_name(places, place_id))


def _place_plain_name(places: dict[str, dict[str, Any]], place_id: Any) -> str:
    if not isinstance(place_id, str):
        place_id = str(place_id) if place_id is not None else ""
    return str(places.get(place_id, {}).get("name", place_id or "—"))


def _status_badge(value: Any) -> str:
    status = str(value or "unknown")
    token = status.lower()
    if token == "confirmed":
        return '<span class="badge ok">confirmed</span>'
    if token == "reported":
        return '<span class="badge neutral">reported</span>'
    if token == "estimated":
        return '<span class="badge warning">estimated</span>'
    if token == "unverified":
        return '<span class="badge danger">unverified</span>'
    return f'<span class="badge">{escape(status)}</span>'


def _money(value: Any) -> str:
    if not isinstance(value, dict):
        return "—"
    amount = value.get("amount")
    currency = str(value.get("currency", "JPY"))
    if amount is None:
        return "—"
    if isinstance(amount, (int, float)):
        return f"{currency} {amount:,.0f}".replace(",", ",")
    return f"{currency} {escape(str(amount))}"


def _time(value: Any) -> str:
    if not isinstance(value, str):
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%m/%d %H:%M")
    except ValueError:
        return value


def _format_interval(value: Any) -> str:
    if not isinstance(value, dict):
        return "未提供"
    entries = value.get("intervals", [])
    if not isinstance(entries, list):
        return "未提供"
    rows = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        day = item.get("day")
        start = item.get("start")
        end = item.get("end")
        if start and end:
            rows.append(f"{day}:{start}-{end}")
    return ", ".join(rows) or "未提供"


_CSS = """
:root{--ink:#172033;--muted:#657085;--line:#d9dff0;--ok:#0f8a5f;--warn:#d46b08;--danger:#c42b1c;--bg:#eef2f8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,BlinkMacSystemFont,"Noto Sans TC",sans-serif}
.frame{width:min(100%,390px);margin:auto;padding:16px 12px 44px}
header,section,article,footer{background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px}
section,article,footer{margin-top:12px}
h1{font-size:27px;line-height:1.3;margin:.15rem 0 1rem}
h2{font-size:20px;margin:.1rem 0 .7rem}
h3{font-size:18px;margin:.2rem 0 .5rem}
.eyebrow{margin:0;color:var(--muted);font-size:13px;letter-spacing:.06em}
.trip-meta{font-size:14px;color:var(--muted)}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;background:#edf5f2;color:#184d3f;font-weight:700}
.chip.warning{background:#fff4e6;color:#9a5f03}
.chip.critical{background:#fff1f0;color:#9f1b1b}
.chip.success{background:#ebf8f2}
.alerts{padding-left:1.2rem}
.alerts .critical{color:var(--danger);font-weight:700}
.day-nav{display:flex;gap:8px;overflow:auto;padding-bottom:4px}
.day-nav a{display:inline-block;background:#f4f7fb;border:1px solid var(--line);padding:6px 10px;border-radius:999px;text-decoration:none;color:inherit;white-space:nowrap}
.day-card{margin-top:10px}
.day-card ol{margin:0;padding-left:20px}
.day-card li,.route-grid p{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.day-card li{border-top:1px solid var(--line);padding:8px 0;list-style:none}
.day-card li:first-child,.route-grid p:first-child{border-top:none}
.day-card li span{color:var(--muted);font-size:14px}
.day-card .date{color:var(--muted);margin:0 0 .4rem}
table{width:100%;border-collapse:collapse}
th,td{padding:8px 0;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--muted);font-size:13px}
.quota article,.source-grid article{border-top:1px solid var(--line);padding-top:10px}
.meal{padding:8px 0;border-top:1px dashed var(--line)}
.meal:first-child{border-top:0}
.source-grid{display:grid;gap:8px}
.quiet{color:var(--muted)}
.two-col{display:grid;gap:10px}
.chip.ok{background:#ecfdf3;color:#065f46}
.badge{font-size:12px;padding:2px 7px;border-radius:10px;margin-left:6px}
.badge.ok{background:#ecfdf3;color:#065f46}
.badge.neutral{background:#f2f4f7;color:#344054}
.badge.warning{background:#fffaeb;color:#b54708}
.badge.danger{background:#fef3f2;color:#b42318}
.subtotal{margin:.7rem 0 0}
button{margin-top:8px;background:#172033;color:#fff;border:0;padding:9px 12px;border-radius:9px}
@media print{button, .day-nav{display:none}.frame{width:100%}}
"""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Golden Trip website")
    parser.add_argument("trip", type=Path)
    parser.add_argument("--output", type=Path, default=Path("site"))
    args = parser.parse_args()
    trip = _read_json(args.trip)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "index.html").write_text(build_site(trip), encoding="utf-8")


if __name__ == "__main__":
    main()
