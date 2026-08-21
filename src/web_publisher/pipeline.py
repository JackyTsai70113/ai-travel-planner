from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.schemas.validate_trip import validate_trip

CONFIG_SCHEMA = "trip-site-v1"
MEDIA_SCHEMA = "trip-media-v1"
REGISTRY_SCHEMA = "trip-registry-v1"
PUBLISHER_VERSION = "trip-site-publisher-v1"
SENSITIVE_KEYS = {"api_key", "apikey", "authorization", "password", "secret", "token", "booking_reference", "private_notes"}


@dataclass(frozen=True)
class BuildResult:
    trip_id: str
    slug: str
    output_dir: Path
    bundle_sha256: str
    report_path: Path
    readiness: str


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha(path: Path) -> str:
    return _sha(path.read_bytes())


def _strip_private(value: Any, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in SENSITIVE_KEYS or any(part in normalized for part in ("api_key", "password", "access_token")):
                continue
            if key in {"source_path", "absolute_path"}:
                continue
            result[key] = _strip_private(child, normalized)
        return result
    if isinstance(value, list):
        return [_strip_private(child, parent_key) for child in value]
    return value


def load_config(config_path: Path) -> dict[str, Any]:
    config = _read(config_path)
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise ValueError(f"{config_path}: schema_version must be {CONFIG_SCHEMA}")
    required = ("trip_id", "slug", "publication_status", "theme_id", "media_manifest", "features", "output_path")
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"{config_path}: missing required fields: {', '.join(missing)}")
    if config["publication_status"] not in {"preview", "published", "archived"}:
        raise ValueError(f"{config_path}: invalid publication_status")
    if not isinstance(config["features"], dict):
        raise ValueError(f"{config_path}: features must be an object")
    if not isinstance(config["slug"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", config["slug"]):
        raise ValueError(f"{config_path}: slug must contain only lowercase letters, digits, and hyphens")
    if Path(config["media_manifest"]).is_absolute() or ".." in Path(config["media_manifest"]).parts:
        raise ValueError(f"{config_path}: media_manifest must stay inside its config directory")
    return config


def load_media(path: Path) -> dict[str, Any]:
    media = _read(path)
    if media.get("schema_version") != MEDIA_SCHEMA:
        raise ValueError(f"{path}: schema_version must be {MEDIA_SCHEMA}")
    if not isinstance(media.get("assets"), list):
        raise ValueError(f"{path}: assets must be an array")
    for asset in media["assets"]:
        if not isinstance(asset, dict) or not asset.get("id") or not asset.get("status"):
            raise ValueError(f"{path}: every asset requires id and status")
        if asset["status"] not in {"approved", "pending", "rejected"}:
            raise ValueError(f"{path}: invalid media status")
        if asset["status"] == "approved" and not asset.get("source_url"):
            raise ValueError(f"{path}: approved media requires source_url")
    return media


def _readiness(trip: dict[str, Any], config: dict[str, Any]) -> tuple[str, list[str]]:
    issues = []
    uncertainty = []
    for item in trip.get("validation", []):
        if isinstance(item, dict):
            severity = item.get("severity")
            message = str(item.get("message") or item.get("code") or "validation issue")
            if severity in {"error", "critical"}:
                issues.append(message)
            elif severity in {"warning", "unknown", "unverified", "conflict", "stale"}:
                uncertainty.append(message)
    if not trip.get("validation"):
        uncertainty.append("no recorded validation result")
    if config["publication_status"] == "published" and (issues or uncertainty):
        return "blocked", issues + uncertainty
    return ("ready" if not issues and not uncertainty else "incomplete"), issues + uncertainty


def _registry_entry(bundle: dict[str, Any], config: dict[str, Any], readiness: str, generated_at: str, bundle_hash: str) -> dict[str, Any]:
    date_range = bundle.get("date_range") or {}
    days = bundle.get("days") or []
    return {
        "schema_version": REGISTRY_SCHEMA,
        "slug": config["slug"],
        "canonical_url": f"trips/{config['slug']}/",
        "trip_id": config["trip_id"],
        "title": config.get("title_override") or bundle.get("title") or config["trip_id"],
        "date_range": {"start_date": date_range.get("start_date"), "end_date": date_range.get("end_date")},
        "duration_days": len(days),
        "theme_id": config["theme_id"],
        "publication_status": config["publication_status"],
        "readiness": readiness,
        "features": config["features"],
        "media_manifest": config["media_manifest"],
        "bundle_sha256": bundle_hash,
        "last_build": generated_at,
    }


def _safe_provenance(raw: Any, supports: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    result = {"supports": supports, "status": raw.get("status", "unknown"), "authority": raw.get("provider") or raw.get("source_type"), "last_checked": raw.get("retrieved_at") or raw.get("checked_at"), "confidence": raw.get("confidence"), "source_url": raw.get("source_url")}
    return {key: value for key, value in result.items() if value is not None}


def _generic_bundle(trip: dict[str, Any], config: dict[str, Any], trip_path: Path, readiness: str, generated_at: str) -> dict[str, Any]:
    candidate = trip.get("candidate_sets") if isinstance(trip.get("candidate_sets"), dict) else {}
    places = [place for place in candidate.get("places", []) if isinstance(place, dict) and place.get("id")]
    place_index = {place["id"]: place for place in places}
    days = []
    for day in trip.get("days", []):
        if not isinstance(day, dict):
            continue
        days.append({"date": day.get("date"), "summary": day.get("summary"), "items": [{key: item.get(key) for key in ("id", "kind", "place_id", "start_at", "end_at") if item.get(key) is not None} for item in day.get("items", []) if isinstance(item, dict)]})
    safe_places = [{key: place.get(key) for key in ("id", "name", "address", "kind", "maps_query") if place.get(key) is not None} for place in places]
    legs = [{key: leg.get(key) for key in ("id", "mode", "from_place_id", "to_place_id", "departure_at", "arrival_at", "estimated_duration", "distance_km") if leg.get(key) is not None} for leg in candidate.get("transport_legs", []) if isinstance(leg, dict)]
    validation = [{key: item.get(key) for key in ("code", "message", "severity", "path", "reference") if item.get(key) is not None} for item in trip.get("validation", []) if isinstance(item, dict)]
    ledger = []
    if _safe_provenance(trip.get("provenance"), "trip"):
        ledger.append(_safe_provenance(trip.get("provenance"), "trip"))
    for place in places:
        entry = _safe_provenance(place.get("provenance"), f"place:{place['id']}")
        if entry:
            ledger.append(entry)
    budget = trip.get("budget") if isinstance(trip.get("budget"), dict) else {}
    total = budget.get("total") if isinstance(budget.get("total"), dict) else {}
    return {
        "schema_version": "trip-public-bundle-v1", "trip_id": config["trip_id"], "title": config.get("title_override") or trip.get("title"), "local_timezone": trip.get("local_timezone"), "date_range": trip.get("date_range", {}),
        "overview": {"trip_scope": [config["trip_id"]], "day_count": len(days)}, "traveler_profile": {"adults": (trip.get("traveler_profile") or {}).get("adults", 0), "children_count": len((trip.get("traveler_profile") or {}).get("children", []))},
        "places": safe_places, "days": days, "transport_legs": legs, "selected": {"hotel_place_ids": (trip.get("selected") or {}).get("hotel_place_ids", []), "flight_ids": (trip.get("selected") or {}).get("flight_ids", [])},
        "reservations": [], "flights": [{"id": item.get("id"), "carrier": item.get("carrier"), "flight_number": item.get("flight_number")} for item in candidate.get("flights", []) if isinstance(item, dict)],
        "hotels": [{"place_id": (item.get("place") or {}).get("id"), "check_in": item.get("check_in"), "check_out": item.get("check_out")} for item in candidate.get("hotels", []) if isinstance(item, dict)],
        "conditions": {"status": "unknown"}, "alternatives": [], "meals": [], "budget": {"currency": budget.get("currency"), "total": {"amount": total.get("amount"), "currency": total.get("currency") or budget.get("currency")}},
        "validation": validation, "source_ledger": ledger, "site": {"slug": config["slug"], "theme_id": config["theme_id"], "features": config["features"], "media_manifest": config["media_manifest"]}, "build": {"publisher": PUBLISHER_VERSION, "generated_at": generated_at, "validation_status": readiness}
    }


def _write_shell(path: Path, config: dict[str, Any]) -> None:
    title = config.get("title_override") or config["trip_id"]
    path.write_text(
        "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>"
        + title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        + "</title></head><body><div id=\"root\"></div><script type=\"application/json\" data-trip-site-config>"
        + json.dumps({"slug": config["slug"], "trip_id": config["trip_id"], "theme_id": config["theme_id"]}, ensure_ascii=False)
        + "</script></body></html>\n",
        encoding="utf-8",
    )


def build_trip(trip_path: Path, config_path: Path, output_root: Path) -> BuildResult:
    config = load_config(config_path)
    if config["trip_id"] != _read(trip_path).get("id"):
        raise ValueError(f"{config_path}: trip_id does not match canonical trip")
    media_path = config_path.parent / config["media_manifest"]
    media = load_media(media_path)
    trip = _read(trip_path)
    validate_trip(trip)
    readiness, issues = _readiness(trip, config)
    if config["publication_status"] == "published" and readiness == "blocked":
        raise ValueError("critical validation failure blocks published build: " + "; ".join(issues))

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    bundle = _generic_bundle(trip, config, trip_path, readiness, generated_at)
    out = output_root / "trips" / config["slug"]
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "public-bundle.json", bundle)
    bundle_hash = _file_sha(out / "public-bundle.json")
    _write(out / "site.json", {key: config[key] for key in ("schema_version", "trip_id", "slug", "publication_status", "theme_id", "media_manifest", "features", "pwa", "seo", "output_path") if key in config})
    _write(out / "site-media.json", {"schema_version": media["schema_version"], "trip_id": media.get("trip_id"), "assets": [{key: asset.get(key) for key in ("id", "kind", "status", "source_url", "alt", "license") if asset.get(key) is not None} for asset in media["assets"]]})
    _write_shell(out / "index.html", config)
    report = {
        "schema_version": "trip-site-build-report-v1",
        "publisher": PUBLISHER_VERSION,
        "trip_id": config["trip_id"],
        "slug": config["slug"],
        "readiness": readiness,
        "input_hashes": {"trip": _file_sha(trip_path), "site_config": _file_sha(config_path), "media_manifest": _file_sha(media_path)},
        "outputs": {"bundle_sha256": bundle_hash, "output_path": str(out)},
        "versions": {"bundle": "trip-public-bundle-v1", "theme": config["theme_id"], "media": media["schema_version"]},
        "generated_at": generated_at,
    }
    report_path = out / "build-report.json"
    report["outputs"]["web_asset_sha256"] = _file_sha(out / "index.html")
    _write(report_path, report)
    return BuildResult(config["trip_id"], config["slug"], out, bundle_hash, report_path, readiness)


def build_all(config_root: Path, output_root: Path) -> list[BuildResult]:
    configs = sorted(config_root.glob("**/site.json"))
    if not configs:
        raise ValueError(f"no site.json found under {config_root}")
    results = []
    output_root.mkdir(parents=True, exist_ok=True)
    trips_output = output_root / "trips"
    if trips_output.exists():
        shutil.rmtree(trips_output)
    configs_by_trip_id: dict[str, dict[str, Any]] = {}
    for config_path in configs:
        config = load_config(config_path)
        trip_path = config_path.parent / config.get("trip_file", "trip.json")
        configs_by_trip_id[config["trip_id"]] = config
        results.append(build_trip(trip_path, config_path, output_root))
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    registry = [_registry_entry(_read(result.output_dir / "public-bundle.json"), configs_by_trip_id[result.trip_id], result.readiness, generated_at, result.bundle_sha256) for result in results]
    _write(output_root / "registry.json", {"schema_version": REGISTRY_SCHEMA, "generated_at": generated_at, "trips": registry})
    root_index = output_root / "index.html"
    root_index.write_text("<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Japan Trip Sites</title></head><body><main><h1>Japan Trip Sites</h1><p>See registry.json for the generated trip catalog.</p></main></body></html>\n", encoding="utf-8")
    return results


def init_site(trip_id: str, slug: str, theme_id: str, target: Path) -> tuple[Path, Path]:
    target.mkdir(parents=True, exist_ok=True)
    config = {"schema_version": CONFIG_SCHEMA, "trip_id": trip_id, "slug": slug, "publication_status": "preview", "theme_id": theme_id, "media_manifest": "site-media.json", "features": {"itinerary": True, "driving": False, "conditions": False, "local_planner": False}, "pwa": {"name": trip_id, "scope": f"/trips/{slug}/"}, "seo": {"title": trip_id, "description": "待填寫；不可放入虛構行程資料。"}, "output_path": f"site/trips/{slug}/", "trip_file": "trip.json"}
    media = {"schema_version": MEDIA_SCHEMA, "trip_id": trip_id, "assets": []}
    config_path, media_path = target / "site.json", target / "site-media.json"
    _write(config_path, config)
    _write(media_path, media)
    return config_path, media_path
