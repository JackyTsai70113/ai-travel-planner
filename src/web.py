"""Private, filesystem-backed dashboard for the production planning pipeline.

The HTTP layer intentionally has no provider or planner knowledge.  A request is
parsed once and handed to ``src.application.production``; the canonical trip it
persists remains the only data used to build the read models below.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, quote, unquote, urlparse

from src.intent import parse_trip_request


STAGES = ("parsing", "research", "candidate store", "routing", "planning", "optimizing", "validation / repair", "rendering")
TAB_NAMES = ("Overview", "Itinerary", "Map / Routing", "Restaurants", "Flights", "Hotels", "Budget", "Research / Sources", "Validation", "Final Website")


class PlanningService(Protocol):
    def plan(self, request: str, trip_id: str, progress: Callable[[str], None]) -> Any: ...


class ProductionPlanningService:
    """Small lazy bridge that keeps the web process independent of providers."""

    def __init__(self, trips_directory: Path, site_directory: Path) -> None:
        self.trips_directory = trips_directory
        self.site_directory = site_directory

    def plan(self, request: str, trip_id: str, progress: Callable[[str], None]) -> Any:
        progress("parsing")
        intent = parse_trip_request(request)
        # Importing here lets the dashboard return a configuration error instead
        # of failing to start when optional production integrations are absent.
        from src.application.production import create_production_orchestrator

        for stage in STAGES[1:]:
            progress(stage)
        orchestrator = create_production_orchestrator(
            trip_id=trip_id,
            trips_directory=self.trips_directory,
            site_directory=self.site_directory,
            progress_callback=progress,
        )
        return orchestrator.run(intent)


@dataclass
class Job:
    id: str
    request: str
    stage: str = "queued"
    state: str = "running"
    error: dict[str, Any] | None = None
    trip_id: str | None = None
    stages: list[str] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "state": self.state, "stage": self.stage, "stages": self.stages, "error": self.error, "trip_id": self.trip_id}


class DashboardApp:
    def __init__(self, *, trips_directory: Path = Path("trips"), site_directory: Path = Path("site"), service: PlanningService | None = None) -> None:
        self.trips_directory, self.site_directory = trips_directory, site_directory
        self.service = service or ProductionPlanningService(trips_directory, site_directory)
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, request: str) -> Job:
        if not request.strip():
            raise ValueError("請輸入自然語言旅遊需求。")
        job = Job(uuid.uuid4().hex, request)
        with self._lock:
            self.jobs[job.id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def job(self, job_id: str) -> Job | None:
        with self._lock:
            return self.jobs.get(job_id)

    def _run(self, job: Job) -> None:
        trip_id = _trip_id(job.request)
        def progress(stage: str) -> None:
            with self._lock:
                job.stage = stage
                if stage not in job.stages:
                    job.stages.append(stage)
        try:
            result = self.service.plan(job.request, trip_id, progress)
            trip = _result_trip(result)
            # Successful production composition must have persisted the canonical
            # document.  Do not render a "success" from an in-memory invalid trip.
            trip_path = self.trips_directory / trip_id / "trip.json"
            if trip is None and trip_path.exists():
                trip = _read_json(trip_path)
            if trip is None:
                raise RuntimeError("production composition completed without a persisted canonical Trip")
            if not trip_path.exists():
                raise RuntimeError("production composition did not persist trips/<trip-id>/trip.json")
            if not (self.site_directory / trip_id / "index.html").exists():
                raise RuntimeError("production composition did not render site/<trip-id>/index.html")
            with self._lock:
                job.state, job.stage, job.trip_id = "complete", "complete", trip_id
        except Exception as exc:  # External failures are deliberately surfaced.
            with self._lock:
                job.state, job.stage = "failed", "failed"
                job.error = _safe_error(exc)

    def recent_trips(self) -> list[dict[str, str]]:
        if not self.trips_directory.exists():
            return []
        result = []
        for path in self.trips_directory.glob("*/trip.json"):
            try:
                trip = _read_json(path)
                result.append({"id": str(trip.get("id", path.parent.name)), "title": str(trip.get("title", path.parent.name)), "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
            except (OSError, ValueError, TypeError):
                continue
        return sorted(result, key=lambda item: item["updated_at"], reverse=True)

    def trip_view(self, trip_id: str) -> dict[str, Any] | None:
        if not _safe_id(trip_id):
            return None
        path = self.trips_directory / trip_id / "trip.json"
        if not path.is_file():
            return None
        return _trip_read_model(_read_json(path), trip_id)


def _result_trip(result: Any) -> dict[str, Any] | None:
    if isinstance(result, dict):
        return result.get("trip") if isinstance(result.get("trip"), dict) else result
    value = getattr(result, "trip", None)
    return value if isinstance(value, dict) else None


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Trip JSON must be an object")
    return value


def _trip_id(request: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", request.lower()).strip("-")
    words = words[:36].strip("-") or "request"
    # Canonical Trip IDs must start with a letter, including requests which
    # begin with a duration such as "5 天 4 夜".
    if not words[0].isalpha(): words = "trip-" + words
    return words + "-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _safe_id(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_-]*", value))


def _safe_error(exc: Exception) -> dict[str, Any]:
    name = exc.__class__.__name__
    missing = getattr(exc, "missing", None)
    if missing:
        return {"code": "configuration_missing", "message": "Production provider configuration is missing or unverified.", "missing": [str(item) for item in missing]}
    text = _redact(str(exc))
    if "configuration_missing" in text or "credential" in text.lower() or "api key" in text.lower():
        return {"code": "configuration_missing", "message": text}
    return {"code": "planning_failed", "message": text or name}


def _redact(value: str) -> str:
    for secret in os.environ.values():
        if len(secret) >= 6 and secret in value:
            value = value.replace(secret, "[redacted]")
    return value[:1000]


def _trip_read_model(trip: dict[str, Any], trip_id: str) -> dict[str, Any]:
    sets = trip.get("candidate_sets", {})
    places = {item.get("id"): item for item in sets.get("places", []) if isinstance(item, dict)}
    days = []
    for day in trip.get("days", []):
        items = []
        for item in day.get("items", []):
            place = places.get(item.get("place_id"), {})
            items.append({"time": item.get("start_at"), "end": item.get("end_at"), "kind": item.get("kind"), "name": place.get("name", item.get("place_id")), "duration": _duration(item.get("start_at"), item.get("end_at")), "alternatives": item.get("alternative_place_ids", []), "fixed": item.get("kind") == "transport"})
        days.append({"date": day.get("date"), "summary": day.get("summary", ""), "items": items})
    routes = []
    for leg in sets.get("transport_legs", []):
        provenance = leg.get("provenance", {})
        routes.append({"from": places.get(leg.get("from_place_id"), {}).get("name", leg.get("from_place_id")), "to": places.get(leg.get("to_place_id"), {}).get("name", leg.get("to_place_id")), "mode": leg.get("mode"), "departure": leg.get("departure_at"), "arrival": leg.get("arrival_at"), "status": provenance.get("status", "unverified"), "maps": _maps_link(places.get(leg.get("from_place_id")), places.get(leg.get("to_place_id")))})
    sources = []
    for group, candidates in sets.items():
        for candidate in candidates if isinstance(candidates, list) else []:
            provenance = candidate.get("provenance") or candidate.get("place", {}).get("provenance", {})
            if provenance:
                sources.append({"group": group, "name": candidate.get("name") or candidate.get("place", {}).get("name") or candidate.get("id"), **_public_provenance(provenance)})
    overview = {"title": trip.get("title"), "dates": trip.get("date_range", {}), "travelers": trip.get("traveler_profile", {}), "cities": trip.get("preferences", {}).get("hard_constraints", []), "budget": trip.get("budget", {}).get("total"), "validation_status": "invalid" if any(x.get("severity") == "error" for x in trip.get("validation", [])) else "valid", "warnings": trip.get("validation", [])}
    return _public({"trip": trip, "overview": overview, "days": days, "routes": routes, "restaurants": sets.get("restaurants", []), "flights": sets.get("flights", []), "hotels": sets.get("hotels", []), "budget": trip.get("budget", {}), "sources": sources, "validation": trip.get("validation", []), "website_url": f"/site/{quote(trip_id)}/index.html", "trip_json_url": f"/trips/{quote(trip_id)}/trip.json"})


def _duration(start: Any, end: Any) -> str:
    try:
        minutes = int((datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))).total_seconds() / 60)
        return f"{minutes} min"
    except (TypeError, ValueError):
        return "unknown / unverified"


def _maps_link(origin: Any, destination: Any) -> str | None:
    if not isinstance(origin, dict) or not isinstance(destination, dict): return None
    a, b = origin.get("coordinates"), destination.get("coordinates")
    if not isinstance(a, dict) or not isinstance(b, dict): return None
    return "https://www.google.com/maps/dir/?api=1&origin={0},{1}&destination={2},{3}".format(a.get("latitude"), a.get("longitude"), b.get("latitude"), b.get("longitude"))


def _public_provenance(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value.get(key) for key in ("provider", "source_url", "retrieved_at", "status", "source_type")}


def _public(value: Any) -> Any:
    """Remove accidental credential-shaped keys from a browser read model."""
    if isinstance(value, list): return [_public(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _public(v) for k, v in value.items() if not re.search(r"(api.?key|secret|token|password|authorization)", str(k), re.I)}
    return _redact(value) if isinstance(value, str) else value


class DashboardHandler(BaseHTTPRequestHandler):
    app: DashboardApp

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/": return self._html(_home_html(self.app.recent_trips()))
        if parsed.path.startswith("/api/jobs/"):
            job = self.app.job(parsed.path.rsplit("/", 1)[-1]); return self._json(job.public() if job else {"error": "not_found"}, 200 if job else 404)
        if parsed.path.startswith("/api/trips/"):
            view = self.app.trip_view(unquote(parsed.path.rsplit("/", 1)[-1])); return self._json(view or {"error": "not_found"}, 200 if view else 404)
        if parsed.path.startswith("/trips/") or parsed.path.startswith("/site/"):
            return self._artifact(parsed.path)
        self._json({"error": "not_found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/plans": return self._json({"error": "not_found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", "0")); body = json.loads(self.rfile.read(length))
            job = self.app.submit(str(body.get("request", "")))
            self._json(job.public(), 202)
        except (ValueError, json.JSONDecodeError) as exc: self._json({"error": str(exc)}, 400)

    def _artifact(self, url_path: str) -> None:
        parts = [unquote(x) for x in url_path.split("/") if x]
        if len(parts) != 3 or parts[0] not in {"trips", "site"} or not _safe_id(parts[1]) or parts[2] not in {"trip.json", "index.html"}:
            return self._json({"error": "not_found"}, 404)
        root = self.app.trips_directory if parts[0] == "trips" else self.app.site_directory
        path = root / parts[1] / parts[2]
        if not path.is_file(): return self._json({"error": "not_found"}, 404)
        content_type = "application/json; charset=utf-8" if path.suffix == ".json" else "text/html; charset=utf-8"
        data = path.read_bytes(); self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def _json(self, body: Any, status: int = 200) -> None:
        data = json.dumps(_public(body), ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def _html(self, body: str) -> None:
        data = body.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None: pass


def create_server(app: DashboardApp | None = None, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    handler = type("ConfiguredDashboardHandler", (DashboardHandler,), {"app": app or DashboardApp()})
    return ThreadingHTTPServer((host, port), handler)


def _home_html(recent: list[dict[str, str]]) -> str:
    recent_html = "".join(f'<li><a href="#" onclick="openTrip(\'{escape(x["id"], quote=True)}\')">{escape(x["title"])}</a><small>{escape(x["updated_at"])}</small></li>' for x in recent) or "<li>尚無已完成行程。</li>"
    tabs = "".join(f'<button role="tab" data-tab="{escape(name)}">{escape(name)}</button>' for name in TAB_NAMES)
    return f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Travel Planner</title><style>{_CSS}</style><main><h1>AI Travel Planner</h1><form id="plan"><textarea id="request" required placeholder="幫我規劃 5 天 4 夜德島＋神戶，2 大 1 個 2 歲小孩，台北出發，自駕，不要太累，預算 8 萬。"></textarea><button>開始規劃</button></form><p id="progress" aria-live="polite"></p><p id="error" role="alert"></p><section><h2>最近行程</h2><ul>{recent_html}</ul></section><section id="workspace" hidden><div class="tabs" role="tablist">{tabs}</div><pre id="result"></pre></section></main><script>{_JS}</script></html>'''


_JS = '''const p=document.querySelector('#progress'),e=document.querySelector('#error'),w=document.querySelector('#workspace'),r=document.querySelector('#result');
document.querySelector('#plan').onsubmit=async x=>{x.preventDefault();e.textContent='';p.textContent='準備執行…';let q=await fetch('/api/plans',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request:document.querySelector('#request').value})});let j=await q.json();if(!q.ok){e.textContent=j.error;return} watch(j.id)};
async function watch(id){let q=await fetch('/api/jobs/'+id),j=await q.json();p.textContent='目前階段：'+j.stage+(j.stages.length?' · '+j.stages.join(' → '):'');if(j.state==='running')return setTimeout(()=>watch(id),500);if(j.state==='failed'){e.textContent=(j.error&&j.error.message)||'規劃失敗';return}openTrip(j.trip_id)}
async function openTrip(id){let q=await fetch('/api/trips/'+id),j=await q.json();if(!q.ok){e.textContent='無法載入行程';return}window.trip=j;w.hidden=false;show('Overview')};
document.querySelectorAll('[data-tab]').forEach(x=>x.onclick=()=>show(x.dataset.tab));function show(tab){let t=window.trip;if(!t)return;let maps={'Overview':t.overview,'Itinerary':t.days,'Map / Routing':t.routes,'Restaurants':t.restaurants,'Flights':t.flights,'Hotels':t.hotels,'Budget':t.budget,'Research / Sources':t.sources,'Validation':t.validation,'Final Website':{website:t.website_url,trip_json:t.trip_json_url}};r.textContent=JSON.stringify(maps[tab],null,2)}'''
_CSS = 'body{font:16px system-ui;max-width:980px;margin:2rem auto;padding:0 1rem;background:#f5f7fa;color:#172033}textarea{width:100%;min-height:7rem;padding:1rem}button{padding:.7rem 1rem;margin:.5rem .3rem .5rem 0}section,form{background:white;padding:1rem;border-radius:.75rem;margin:1rem 0}.tabs{overflow:auto;white-space:nowrap}pre{white-space:pre-wrap;overflow:auto;background:#101828;color:#eaf2ff;padding:1rem;border-radius:.5rem}#error{color:#b42318}small{display:block;color:#667085}'


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the private AI Travel Planner dashboard")
    parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args(); server = create_server(host=args.host, port=args.port)
    print(f"AI Travel Planner dashboard: http://{args.host}:{args.port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == "__main__": main()
