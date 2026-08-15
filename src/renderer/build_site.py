"""Dependency-free static renderer for Canonical Trip V1 documents.

It only formats canonical fields and optional upstream read models. It never
validates, routes, optimises, or decides whether an itinerary is correct.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
from typing import Any


def build_site(trip: dict[str, Any], derived: dict[str, Any] | None = None) -> str:
    """Render a self-contained mobile-first HTML document."""
    derived = derived or {}
    places = {p["id"]: p for p in trip["candidate_sets"].get("places", [])}
    title = escape(trip.get("title", "Trip"))
    dates = trip.get("date_range", {})
    overview = derived.get("overview", {})
    stats = "".join(f'<div class="stat"><span>{escape(str(k))}</span><strong>{escape(str(v))}</strong></div>' for k, v in overview.items())
    if not stats:
        stats = f'<div class="stat"><span>旅遊日期</span><strong>{escape(dates.get("start_date", "—"))} ～ {escape(dates.get("end_date", "—"))}</strong></div>'
    warnings = "".join(f"<li>{escape(_warning_text(x))}</li>" for x in trip.get("validation", [])) or '<li class="quiet">目前沒有上游 validation warning。</li>'
    days = "".join(_render_day(day, places) for day in trip.get("days", []))
    budget = "".join(f"<tr><th>{escape(str(k))}</th><td>{escape(_money(v))}</td></tr>" for k, v in trip.get("budget", {}).get("categories", {}).items())
    total = derived.get("budget", {}).get("total_label") or _money(trip.get("budget", {}).get("total", {}))
    sources = "".join(_render_source(x) for x in _sources(trip)) or '<p class="quiet">沒有未確認來源資料。</p>'
    attributions = "".join(_render_attribution(value) for value in _attributions(trip))
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title><style>{_CSS}</style></head><body><main>
<header><p class="eyebrow">TRIP · {escape(trip.get("local_timezone", ""))}</p><h1>{title}</h1><div class="stats">{stats}</div></header>
<nav aria-label="行程區段"><a href="#overview">總覽</a><a href="#itinerary">行程</a><a href="#budget">預算</a></nav>
<section id="overview"><h2>總覽</h2><h3>Validation warnings</h3><ul class="warnings">{warnings}</ul><h3>未確認與估算資訊</h3><p class="hint">以下狀態由資料來源提供；此頁不判定行程是否可行。</p><div class="sources">{sources}</div><div class="attributions">{attributions}</div></section>
<section id="itinerary"><h2>行程</h2>{days}</section><section id="budget"><h2>預算</h2><table><tbody>{budget}</tbody><tfoot><tr><th>總計</th><td>{escape(str(total))}</td></tr></tfoot></table></section>
</main></body></html>'''


def _render_day(day: dict[str, Any], places: dict[str, dict[str, Any]]) -> str:
    items = []
    for item in day.get("items", []):
        place = places.get(item.get("place_id"), {})
        items.append(f'<li><time>{escape(_time(item.get("start_at", "")))}</time><strong>{escape(place.get("name", item.get("place_id", "—")))}</strong><span>{escape(item.get("kind", ""))}</span></li>')
    return f'<article><p class="eyebrow">{escape(day.get("date", ""))}</p><h3>{escape(day.get("summary", ""))}</h3><ol>{"".join(items)}</ol></article>'


def _sources(trip: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"name": p.get("name", p.get("id", "—")), "provenance": p["provenance"]} for p in trip.get("candidate_sets", {}).get("places", []) if p.get("provenance", {}).get("status") in {"reported", "estimated", "unverified"}]


def _attributions(trip: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for candidate in trip.get("candidate_sets", {}).get("restaurants", []):
        candidate_values = candidate.get("attributions")
        if isinstance(candidate_values, list):
            values.extend(value for value in candidate_values if isinstance(value, str) and value)
    return list(dict.fromkeys(values))


def _render_attribution(value: str) -> str:
    if value == _HOTPEPPER_ATTRIBUTION:
        return (
            '<p class="attribution">Powered by '
            '<a href="http://webservice.recruit.co.jp/">'
            'ホットペッパーグルメ Webサービス</a></p>'
        )
    return f'<p class="attribution">{escape(value)}</p>'


def _render_source(item: dict[str, Any]) -> str:
    p = item["provenance"]
    provider = escape(str(p.get("provider", "未知來源")))
    provider = f'<a href="{escape(str(p["source_url"]), quote=True)}">{provider}</a>' if p.get("source_url") else provider
    return f'<article class="source"><strong>{escape(str(item["name"]))}</strong><span class="badge">{escape(str(p.get("status", "unknown")))}</span><p>{provider} · source freshness: {escape(str(p.get("retrieved_at", "unknown")))}</p></article>'


def _warning_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _time(value: str) -> str:
    try: return datetime.fromisoformat(value).strftime("%H:%M")
    except ValueError: return value


def _money(value: Any) -> str:
    if not isinstance(value, dict): return "—"
    amount, currency = value.get("amount", "—"), value.get("currency", "")
    return f"{currency} {amount:,}" if isinstance(amount, (int, float)) else f"{currency} {amount}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a static Trip V1 site")
    parser.add_argument("trip", type=Path); parser.add_argument("--derived", type=Path); parser.add_argument("--output", type=Path, default=Path("site"))
    args = parser.parse_args(); trip = json.loads(args.trip.read_text(encoding="utf-8"))
    derived = json.loads(args.derived.read_text(encoding="utf-8")) if args.derived else None
    args.output.mkdir(parents=True, exist_ok=True); (args.output / "index.html").write_text(build_site(trip, derived), encoding="utf-8")


_CSS = '''
:root{--ink:#172033;--muted:#5d6779;--line:#dce1e9;--accent:#0b6e69}*{box-sizing:border-box}body{margin:0;background:#f3f6f8;color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Noto Sans TC",sans-serif}main{max-width:680px;margin:auto;padding:20px 16px 48px}header,section,article{background:#fff;border:1px solid var(--line);border-radius:16px}header,section{padding:20px;margin-bottom:14px}h1{font-size:28px;line-height:1.2;margin:4px 0 18px}h2{font-size:21px;margin:0 0 16px}h3{font-size:17px;margin:12px 0 8px}.eyebrow{color:var(--muted);font-size:12px;font-weight:700;letter-spacing:.06em;margin:0}.stats{display:grid;gap:8px}.stat{background:#eaf5f3;border-radius:10px;padding:10px 12px}.stat span,.stat strong{display:block}.stat span,.hint,.quiet,.source p,.attribution{color:var(--muted);font-size:14px}nav{display:flex;gap:8px;overflow:auto;position:sticky;top:0;padding:8px 0;background:#f3f6f8;z-index:1}nav a{background:#fff;border:1px solid var(--line);border-radius:999px;color:var(--ink);padding:7px 13px;text-decoration:none;white-space:nowrap}ul,ol{padding-left:20px}.warnings li{color:#9a5200;margin:6px 0}.warnings .quiet{color:var(--muted)}article{padding:14px;margin:10px 0}article h3{margin-top:3px}ol{list-style:none;padding:0;margin:10px 0 0}ol li{display:grid;grid-template-columns:56px 1fr;gap:3px 10px;border-top:1px solid var(--line);padding:10px 0}ol li:first-child{border-top:0}time,ol span{color:var(--muted);font-size:14px}ol span{grid-column:2}.source{display:grid;grid-template-columns:1fr auto;gap:2px 8px}.source p{grid-column:1/-1;margin:2px 0 0}.attribution{margin:12px 0 0}.badge{color:#704400;background:#fff1d6;border-radius:999px;font-size:12px;font-weight:700;padding:2px 8px}table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid var(--line);padding:10px 0;text-align:left}td{text-align:right}tfoot{font-weight:800}@media(max-width:390px){main{padding:12px 10px 32px}header,section{padding:16px}h1{font-size:25px}}
'''

_HOTPEPPER_ATTRIBUTION = "Powered by ホットペッパーグルメ Webサービス"


if __name__ == "__main__": main()
