"""Build a deterministic public-safe bundle for the Awaji 2026 trip."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

TRIP_PATH_DEFAULT = Path("trips/awaji-naruto-tokushima-kobe-2026/trip.json")
OUTPUT_DEFAULT = Path("trips/awaji-naruto-tokushima-kobe-2026/public-bundle.json")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def _format_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _today_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _build_profile(trip: dict) -> dict:
    profile = trip.get("traveler_profile", {})
    children = profile.get("children", [])
    return {
        "adults": profile.get("adults", 0),
        "children_count": len(children),
        "children_ages": [entry.get("age") for entry in children],
    }


def _safe_time(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value[:16]
    if parsed.tzinfo is None:
        return parsed.replace(microsecond=0, second=0).isoformat()
    return parsed.replace(microsecond=0, second=0).isoformat()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def _safe_str(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_status(value: object) -> str:
    normalized = _safe_str(value) or "unknown"
    known = {
        "confirmed",
        "estimated",
        "reported",
        "user-confirmed",
        "warning",
        "error",
        "critical",
        "info",
        "unverified",
        "stale",
        "conflict",
        "unknown",
    }
    return normalized if normalized in known else "unknown"


def _provenance_entry(raw: dict[str, Any], *, default_supports: str = "trip-record") -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    status = _as_status(raw.get("status"))
    authority = _safe_str(raw.get("provider")) or _safe_str(raw.get("source_type")) or _safe_str(raw.get("supports"))
    checked = _safe_str(raw.get("retrieved_at")) or _safe_str(raw.get("checked_at"))
    confidence = raw.get("confidence")
    if isinstance(confidence, bool):
        confidence = float(confidence)
    if isinstance(confidence, (int, float)):
        confidence = float(confidence)
    else:
        confidence = None
    return {
        "supports": default_supports,
        "authority": authority,
        "last_checked": checked,
        "status": status,
        "confidence": confidence,
        "freshness": raw.get("freshness", "unknown"),
        "conflicts": bool(raw.get("conflict")) if raw.get("conflict") is not None else False,
        "source_url": _safe_str(raw.get("source_url")),
    }


def _to_ledger_entry(payload: dict[str, Any], *, supports: str) -> dict[str, Any] | None:
    entry = _provenance_entry(payload, default_supports=supports)
    if entry is None:
        return None
    if entry["authority"] is None:
        entry["authority"] = "未指定"
    return entry


def _money_entry(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    amount = _safe_int(value.get("amount"))
    currency = _safe_str(value.get("currency"))
    if amount is None or currency is None:
        return None
    return {"amount": amount, "currency": currency}


def _normalize_item(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "start_at": _safe_time(item.get("start_at")),
        "end_at": _safe_time(item.get("end_at")),
        "place_id": item.get("place_id"),
        "transport_leg_id": item.get("transport_leg_id"),
        "alternative_place_ids": _as_list(item.get("alternative_place_ids")),
        "notes": item.get("notes"),
    }


def _bundle_days(trip: dict) -> list[dict]:
    days: list[dict] = []
    for day in trip.get("days", []):
        day_items = [
            _normalize_item(item)
            for item in day.get("items", [])
            if isinstance(item, dict)
        ]
        days.append({
            "date": day.get("date"),
            "summary": day.get("summary"),
            "items": day_items,
        })
    return days


def _official_url(place: dict[str, object]) -> str | None:
    for identifier in _as_list(place.get("identifiers")):
        if not isinstance(identifier, dict):
            continue
        if identifier.get("type") == "official_url":
            return _safe_str(identifier.get("value"))
    return None


def _google_maps_url(place: dict[str, object]) -> str | None:
    explicit = _safe_str(place.get("google_maps_url"))
    if explicit:
        return explicit
    query = _safe_str(place.get("address")) or _safe_str(place.get("name"))
    if not query:
        return None
    return "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": query})


def _bundle_places(places: dict[str, dict[str, object]]) -> list[dict]:
    return sorted(
        [
            {
                "id": place_id,
                "name": place.get("name"),
                "address": place.get("address"),
                "kind": place.get("kind"),
                "maps_query": place.get("address") or place.get("name"),
                "google_maps_url": _google_maps_url(place),
                "opening_hours_note": place.get("opening_hours_note"),
                "accessibility_notes": place.get("accessibility_notes"),
                "official_url": _official_url(place),
            }
            for place_id, place in places.items()
            if isinstance(place, dict)
        ],
        key=lambda item: item["id"],
    )


def _bundle_place_index(places: dict[str, dict[str, object]]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for place_id, place in places.items():
        if not isinstance(place, dict):
            continue
        provenance = _as_dict(place.get("provenance"))
        indexed[place_id] = {
            "id": place_id,
            "name": _safe_str(place.get("name")) or place_id,
            "address": _safe_str(place.get("address")),
            "kind": _safe_str(place.get("kind")),
            "phone": _safe_str(place.get("phone")),
            "mapcode": _safe_str(place.get("mapcode")),
            "maps_query": _safe_str(place.get("maps_query")),
            "google_maps_url": _google_maps_url(place),
            "opening_hours_note": _safe_str(place.get("opening_hours_note")),
            "accessibility_notes": _safe_str(place.get("accessibility_notes")),
            "official_url": _official_url(place),
            "provenance": {
                "status": _as_status(provenance.get("status")),
                "authority": _safe_str(provenance.get("provider"))
                or _safe_str(provenance.get("source_type"))
                or "未指定",
                "last_checked": _safe_str(provenance.get("retrieved_at")),
                "confidence": provenance.get("confidence"),
                "source_url": _safe_str(provenance.get("source_url")),
            },
            "parking": _safe_str(place.get("parking")),
            "entrance_fee": _safe_str(place.get("entrance_fee")),
            "japanese_phrase": _safe_str(place.get("japanese_phrase")),
        }
    return indexed


def _bundle_validation(validation: list[dict]) -> list[dict]:
    output: list[dict] = []
    for item in validation:
        if not isinstance(item, dict):
            continue
        entry = {
            "code": _safe_str(item.get("code")),
            "message": _safe_str(item.get("message")) or "",
            "severity": _as_status(item.get("severity")),
            "path": _safe_str(item.get("path")),
            "reference": _safe_str(item.get("reference")),
        }
        if entry["code"]:
            output.append(entry)
    return output


def _bundle_critical_alerts(validation: list[dict]) -> list[dict]:
    alerts: list[dict] = []
    for item in validation:
        if not isinstance(item, dict):
            continue
        severity = _as_status(item.get("severity"))
        if severity not in {"error", "warning"}:
            continue
        alerts.append(
            {
                "id": _safe_str(item.get("code")) or "generic",
                "level": severity,
                "message": _safe_str(item.get("message")) or "需要補充",
                "path": _safe_str(item.get("path")),
            }
        )
    return alerts


def _bundle_transport_legs(trip: dict, places: dict[str, dict[str, object]]) -> list[dict]:
    candidate_legs = _as_list(_as_dict(trip.get("candidate_sets")).get("transport_legs"))
    output = []
    for leg in candidate_legs:
        if not isinstance(leg, dict):
            continue
        from_id = _safe_str(leg.get("from_place_id"))
        to_id = _safe_str(leg.get("to_place_id"))
        if not from_id or not to_id:
            continue
        departure_at = _safe_str(leg.get("departure_at"))
        arrival_at = _safe_str(leg.get("arrival_at"))
        provenance = _as_dict(leg.get("provenance"))
        duration_minutes = None
        if departure_at and arrival_at:
            try:
                duration = datetime.fromisoformat(arrival_at) - datetime.fromisoformat(departure_at)
                if duration.total_seconds() >= 0:
                    duration_minutes = int(duration.total_seconds() // 60)
            except ValueError:
                duration_minutes = None
        from_place = _as_dict(places.get(from_id))
        to_place = _as_dict(places.get(to_id))
        origin = _safe_str(from_place.get("address")) or _safe_str(from_place.get("name")) or from_id
        destination = _safe_str(to_place.get("address")) or _safe_str(to_place.get("name")) or to_id
        leg_mode = _safe_str(leg.get("mode")) or "car"
        maps_mode = "transit" if leg_mode in {"bus", "train"} else "walking" if leg_mode == "walk" else "driving"
        directions_url = "https://www.google.com/maps/dir/?" + urlencode(
            {"api": "1", "origin": origin, "destination": destination, "travelmode": maps_mode}
        )
        output.append(
            {
                "id": _safe_str(leg.get("id")) or f"{from_id}-{to_id}",
                "mode": leg_mode,
                "status": _as_status(provenance.get("status")),
                "from_place": _safe_str(from_id),
                "to_place": _safe_str(to_id),
                "from_label": _safe_str(places.get(from_id, {}).get("name")) or from_id,
                "to_label": _safe_str(places.get(to_id, {}).get("name")) or to_id,
                "departure_at": _safe_time(departure_at),
                "arrival_at": _safe_time(arrival_at),
                "estimated_duration_minutes": duration_minutes,
                "note": _safe_str(provenance.get("note")),
                "source_url": _safe_str(provenance.get("source_url")),
                "google_maps_directions_url": directions_url,
                "source_refs": [],
            }
        )
    if output:
        return output

    # Fallback route when no explicit leg model exists: infer from day transport items.
    for day in trip.get("days", []):
        for item in _as_list(day.get("items")):
            if not isinstance(item, dict):
                continue
            if _safe_str(item.get("kind")) != "transport":
                continue
            from_label = _safe_str(item.get("place_id")) or "from"
            to_label = _safe_str(item.get("route_to_place_id"))
            if not to_label:
                continue
            output.append(
                {
                    "id": _safe_str(item.get("id")) or f"{from_label}-{to_label}",
                    "mode": "car",
                    "status": "estimated",
                    "from_place": from_label,
                    "to_place": to_label,
                    "from_label": _safe_str(places.get(from_label, {}).get("name")) or from_label,
                    "to_label": _safe_str(places.get(to_label, {}).get("name")) or to_label,
                    "departure_at": _safe_time(_safe_str(item.get("start_at"))),
                    "arrival_at": _safe_time(_safe_str(item.get("end_at"))),
                    "note": _safe_str(item.get("notes")),
                    "source_refs": [],
                }
            )
    return output


def _bundle_conditions(trip: dict) -> dict[str, Any]:
    raw = _as_dict(trip.get("conditions"))
    if not raw:
        raw = _as_dict(trip.get("condition_snapshots"))
    if not raw:
        return {
            "weather": {"status": "unknown", "status_label": "官方未確認"},
            "tide": {"status": "unknown", "status_label": "官方未確認"},
            "closures": [],
            "freshness": "unknown",
        }
    weather = raw.get("weather") if isinstance(raw.get("weather"), dict) else {}
    tide = raw.get("tide") if isinstance(raw.get("tide"), dict) else {}
    return {
        "weather": {
            "status": _as_status(weather.get("status")),
            "status_label": _safe_str(weather.get("status_label")) or _safe_str(weather.get("state")),
            "summary": _safe_str(weather.get("summary")),
            "last_checked": _safe_str(weather.get("last_checked")),
            "recheck_at": _safe_str(weather.get("recheck_at")),
        },
        "tide": {
            "status": _as_status(tide.get("status")),
            "status_label": _safe_str(tide.get("status_label")) or _safe_str(tide.get("state")),
            "summary": _safe_str(tide.get("summary")),
            "last_checked": _safe_str(tide.get("last_checked")),
            "recheck_at": _safe_str(tide.get("recheck_at")),
        },
        "closures": [
            {
                "place_id": _safe_str(item.get("place_id")),
                "name": _safe_str(item.get("name")),
                "status": _as_status(item.get("status")),
                "summary": _safe_str(item.get("summary")),
            }
            for item in _as_list(raw.get("closures"))
            if isinstance(item, dict)
        ],
        "freshness": _safe_str(raw.get("freshness")) or "unknown",
    }


def _bundle_alternatives(trip: dict) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in _as_list(trip.get("plan_alternatives", [])) + _as_list(
        trip.get("alternatives", [])
    ):
        if not isinstance(item, dict):
            continue
        output.append(
            {
                "id": _safe_str(item.get("id")) or "alternative",
                "title": _safe_str(item.get("title")) or "Plan B/C",
                "status": _as_status(item.get("status")),
                "summary": _safe_str(item.get("summary")) or _safe_str(item.get("notes")) or "待補",
                "reasons": _as_list(item.get("reasons")),
                "decision_gate": _safe_str(item.get("decision_gate")),
                "conditions": _as_list(item.get("conditions")),
            }
        )
    return output


def _override_value(trip: dict, path: str) -> object:
    for override in _as_list(trip.get("overrides")):
        if not isinstance(override, dict):
            continue
        if override.get("path") == path and override.get("preserve_on_replan") is True:
            return override.get("value")
    return None


def _bundle_pretrip_checklist(trip: dict) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for entry in _as_list(_override_value(trip, "/operations/pretrip_checklist")):
        if not isinstance(entry, dict):
            continue
        item_id = _safe_str(entry.get("id"))
        item = _safe_str(entry.get("item"))
        if not item_id or not item:
            continue
        output.append(
            {
                "id": item_id,
                "completed": entry.get("completed") is True,
                "timing": _safe_str(entry.get("timing")),
                "item": item,
                "action": _safe_str(entry.get("action")),
                "fallback": _safe_str(entry.get("fallback")),
                "contact": _safe_str(entry.get("contact")),
            }
        )
    return output


def _bundle_operations(trip: dict) -> dict[str, Any]:
    raw = _as_dict(trip.get("operations"))
    return {
        "fuel": raw.get("fuel") or {},
        "supplies": raw.get("supplies") or [],
        "emergency": raw.get("emergency") or [],
        "handbook": raw.get("handbook") or [],
        "returns": raw.get("returns") or [],
        "pretrip_checklist": _bundle_pretrip_checklist(trip),
    }


def _bundle_source_ledger(places: dict[str, dict[str, object]], trip: dict) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def collect(supports: str, payload: object) -> None:
        entry = _to_ledger_entry(_as_dict(payload), supports=supports)
        if entry is None:
            return
        key = f"{entry['supports']}|{entry['authority']}|{entry['last_checked']}|{entry['status']}"
        if key in seen:
            return
        seen.add(key)
        collected.append(entry)

    collect("trip.meta", trip.get("provenance"))
    for place_id, place in places.items():
        collect(f"place:{place_id}", place.get("provenance"))
    for section in ("flights", "restaurants", "hotels"):
        for item in _as_list(_as_dict(trip.get("candidate_sets")).get(section)):
            if isinstance(item, dict):
                collect(section[:-1] if section.endswith("s") else section, _as_dict(item.get("provenance")))
    for item in _as_list(trip.get("validation")):
        if isinstance(item, dict):
            collect("validation", _as_dict(item.get("provenance")))
    return collected


def _bundle_reservations(days: list[dict], places: dict[str, dict[str, object]]) -> list[dict]:
    reservations: list[dict] = []
    for day in days:
        for item in day.get("items", []):
            if item.get("id", "").startswith("fixed-"):
                place = places.get(item.get("place_id"), {})
                place_name = place.get("name") if isinstance(place, dict) else None
                fallback_name = "8/28 17:45 固定預約（名稱待補）"
                resolution = place.get("resolution") if isinstance(place, dict) else {}
                is_resolved = bool(
                    resolution
                    and isinstance(resolution, dict)
                    and resolution.get("state") == "resolved"
                )
                has_known_name = isinstance(place_name, str) and place_name.strip()
                display_name = place_name if has_known_name else fallback_name
                reservations.append(
                    {
                        "id": item.get("id"),
                        "day": day.get("date"),
                        "time": item.get("start_at"),
                        "name": display_name,
                        "place_id": item.get("place_id"),
                        "unresolved": not is_resolved,
                        "kind": "fixed-reservation" if is_resolved else "placeholder-anchored-reservation",
                    }
                )
    return reservations


def _public_preferences(preferences: dict) -> dict:
    return {
        "hard_constraints": [
            {
                "id": entry.get("id"),
                "description": entry.get("description"),
            }
            for entry in preferences.get("hard_constraints", [])
            if isinstance(entry, dict)
        ],
        "soft_preferences": [
            {
                "id": entry.get("id"),
                "description": entry.get("description"),
            }
            for entry in preferences.get("soft_preferences", [])
            if isinstance(entry, dict)
        ],
    }


def build_public_bundle(trip: dict, trip_path: Path) -> dict:
    places = {
        _safe_str(place.get("id")): place
        for place in _as_dict(trip.get("candidate_sets")).get("places", [])
        if isinstance(place, dict) and _safe_str(place.get("id"))
    }
    days = _bundle_days(trip)
    reservations = _bundle_reservations(days, places)
    validation = _as_list(trip.get("validation", []))
    validation_payload = _bundle_validation(validation)
    conditions = _bundle_conditions(trip)
    alternatives = _bundle_alternatives(trip)
    operations = _bundle_operations(trip)
    transport_legs = _bundle_transport_legs(trip, places)
    place_index = _bundle_place_index(places)
    source_ledger = _bundle_source_ledger(places, trip)
    budget = trip.get("budget", {})
    critical_issues = [
        item.get("message")
        for item in validation_payload
        if item.get("severity") == "error" and item.get("message")
    ]

    severities = {item.get("severity") for item in validation_payload}
    trip_status = "ok"
    if "error" in severities:
        trip_status = "error"
    elif "warning" in severities:
        trip_status = "warning"

    selected_hotel_ids = _as_list(_as_dict(trip.get("selected")).get("hotel_place_ids"))
    selected_flight_ids = _as_list(_as_dict(trip.get("selected")).get("flight_ids"))
    return {
        "trip_id": trip.get("id"),
        "title": trip.get("title"),
        "schema": "awaji-public-bundle-v1",
        "overview": {
            "trip_scope": ["awaji", "naruto", "tokushima", "kobe"],
            "critical_unknown_count": len(_bundle_critical_alerts(validation_payload)),
            "next_recheck_at": _safe_str(
                _as_dict(trip.get("operations")).get("next_recheck_at")
            ),
        },
        "local_timezone": trip.get("local_timezone"),
        "places": _bundle_places(places),
        "status": trip_status,
        "date_range": trip.get("date_range", {}),
        "traveler_profile": _build_profile(trip),
        "selected": {
            "hotel_place_ids": selected_hotel_ids,
            "flight_ids": selected_flight_ids,
        },
        "days": days,
        "reservations": reservations,
        "preferences": _public_preferences(trip.get("preferences", {})),
        "transport_legs": transport_legs,
        "conditions": conditions,
        "alternatives": alternatives,
        "operations": operations,
        "budget": {
            "currency": budget.get("currency"),
            "total": _money_entry(budget.get("total")) or {"amount": 0, "currency": budget.get("currency") or "JPY"},
            "categories": budget.get("categories", {}),
        },
        "critical_alerts": _bundle_critical_alerts(validation_payload),
        "validation": validation_payload,
        "source_ledger": source_ledger,
        "evidence_gate": {
            "status": "error" if critical_issues else "ok",
            "critical_issues": critical_issues,
            "source_hygiene_failures": [],
        },
        "meta": {
            "generated_at": _today_iso(),
            "source_path": str(trip_path),
            "source_sha256": _sha256(trip_path),
            "trip_schema": trip.get("schema_version"),
            "source_coverage": {
                "places": len(place_index),
                "days": len(days),
                "selected_hotels": len(selected_hotel_ids),
                "selected_flights": len(selected_flight_ids),
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the public bundle for the Awaji 2026 handbook")
    parser.add_argument("--trip-path", type=Path, default=TRIP_PATH_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--web-output", type=Path, default=None)
    args = parser.parse_args()

    trip = _read_json(args.trip_path)
    bundle = build_public_bundle(trip, args.trip_path)
    bundle_payload = _format_json(bundle)
    bundle["meta"]["bundle_sha256"] = _sha256_bytes(bundle_payload.encode("utf-8"))
    bundle_payload = _format_json(bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(bundle_payload, encoding="utf-8")
    if args.web_output is not None:
        args.web_output.parent.mkdir(parents=True, exist_ok=True)
        args.web_output.write_text(bundle_payload, encoding="utf-8")


if __name__ == "__main__":
    main()
