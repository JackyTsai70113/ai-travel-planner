"""Build a deterministic public-safe bundle for the Awaji 2026 trip."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

TRIP_PATH_DEFAULT = Path("trips/awaji-naruto-tokushima-kobe-2026/trip.json")
OUTPUT_DEFAULT = Path("trips/awaji-naruto-tokushima-kobe-2026/public-bundle.json")
INVALID_SOURCE_MARKERS = ("example.invalid", "airline.example.invalid", "your-org/ai-travel-planner")
REFRESH_WINDOWS = [
    {"label": "T-7", "days_before": 7, "status": "required"},
    {"label": "T-3", "days_before": 3, "status": "required"},
    {"label": "T-1", "days_before": 1, "status": "required"},
    {"label": "day-of", "days_before": 0, "status": "required"},
]


def _normalize_evidence_reference_id(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    if raw.startswith("selected-") and "/" in raw:
        return raw.split("/", 1)[1]
    return raw


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _today_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _now_local(local_timezone: str) -> datetime:
    return datetime.now(ZoneInfo(local_timezone))


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


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt
    return dt


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


def _has_invalid_source_url(node: object) -> bool:
    if not isinstance(node, dict):
        return False
    source_url = node.get("source_url")
    if isinstance(source_url, str):
        return any(marker in source_url for marker in INVALID_SOURCE_MARKERS)
    return False


def _source_issues(value: object, path: str = "", accumulator: list[str] | None = None) -> list[str]:
    if accumulator is None:
        accumulator = []
    if isinstance(value, dict):
        if _has_invalid_source_url(value):
            accumulator.append(f"{path or '/'}")
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            _source_issues(child, child_path, accumulator)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _source_issues(child, f"{path}[{index}]", accumulator)
    return accumulator


def _find_place(trip: dict, place_id: str) -> dict:
    for place in trip.get("candidate_sets", {}).get("places", []):
        if isinstance(place, dict) and place.get("id") == place_id:
            return place
    return {}


def _find_flight(trip: dict, flight_id: str) -> dict:
    for flight in trip.get("candidate_sets", {}).get("flights", []):
        if isinstance(flight, dict) and flight.get("id") == flight_id:
            return flight
    return {}


def _is_evidence_weak(item: object) -> bool:
    if not isinstance(item, dict):
        return True
    provenance = item.get("provenance")
    if not isinstance(provenance, dict):
        return True
    if _has_invalid_source_url(provenance):
        return True
    if provenance.get("status") in {"unverified", "estimated"}:
        return True
    return False


def _collect_critical_issues(trip: dict, trip_path: Path, evidence_ids: set[str]) -> list[str]:
    selected = trip.get("selected", {})
    issues: list[str] = []

    for fact_id in _collect_selected_fact_ids(selected):
        if fact_id not in evidence_ids:
            issues.append(f"selected:{fact_id}: missing evidence")

    for hotel_id in selected.get("hotel_place_ids", []):
        place = _find_place(trip, hotel_id)
        if _is_evidence_weak(place):
            issues.append(f"selected-hotel/{hotel_id}: no strong evidence")

    for flight_id in selected.get("flight_ids", []):
        flight = _find_flight(trip, flight_id)
        if _is_evidence_weak(flight):
            issues.append(f"selected-flight/{flight_id}: no strong evidence")
        else:
            departure = flight.get("departure", {})
            arrival = flight.get("arrival", {})
            if (
                isinstance(departure, dict)
                and isinstance(arrival, dict)
                and departure.get("at") is None
                and arrival.get("at") is None
            ):
                issues.append(f"selected-flight/{flight_id}: both endpoints unknown")

    return issues


def _load_evidence_payload(trip_path: Path) -> dict:
    evidence_path = trip_path.with_name("evidence.json")
    if not evidence_path.exists():
        return {}
    try:
        return json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _collect_stale_selected_evidence_issues(trip: dict, trip_path: Path, now: datetime) -> list[str]:
    now_local = now.astimezone(ZoneInfo(trip.get("local_timezone", "Asia/Tokyo")))
    payload = _load_evidence_payload(trip_path)
    raw_entries = payload.get("entries", []) if isinstance(payload, dict) else []
    evidence_by_id: dict[str, dict] = {}
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        normalized = _normalize_evidence_reference_id(entry.get("reference_id"))
        if normalized:
            evidence_by_id[normalized] = entry

    issues: list[str] = []
    for fact_id in _collect_selected_fact_ids(trip.get("selected", {})):
        entry = evidence_by_id.get(fact_id)
        if not isinstance(entry, dict):
            continue
        validity = entry.get("validity")
        if not isinstance(validity, dict):
            issues.append(f"selected:{fact_id}: evidence missing validity interval")
            continue
        valid_until = _parse_iso_datetime(validity.get("valid_until"))
        if valid_until is None:
            continue
        if valid_until.astimezone(now_local.tzinfo) < now_local:
            issues.append(f"selected:{fact_id}: evidence stale (valid_until={valid_until.isoformat()})")
    return issues


def _collect_evidence_ids(trip: dict, trip_path: Path) -> set[str]:
    evidence_path = trip_path.with_name("evidence.json")
    if not evidence_path.exists():
        return set()
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    return {
        normalized_id
        for raw in [
            _normalize_evidence_reference_id(entry.get("reference_id"))
            for entry in payload.get("entries", [])
            if isinstance(entry, dict)
        ]
        for normalized_id in [raw]
        if normalized_id
    }


def _collect_selected_fact_ids(selected: dict[str, object]) -> set[str]:
    selected_fact_keys = {
        "flight_ids": "selected-flight",
        "hotel_place_ids": "selected-hotel",
        "place_ids": "selected-place",
    }
    required: set[str] = set()

    for key in selected_fact_keys:
        ids = selected.get(key)
        if isinstance(ids, list):
            required.update(id_ for id_ in ids if isinstance(id_, str))

    return required


def _compute_next_refresh(trip: dict, now: datetime) -> dict[str, str | None]:
    local_tz = ZoneInfo(trip.get("local_timezone", "Asia/Tokyo"))
    now_local = now.astimezone(local_tz)
    trip_start = trip.get("date_range", {}).get("start_date")
    if not isinstance(trip_start, str):
        return {"next_refresh_at": None, "next_refresh_label": None}

    try:
        trip_start_date = datetime.fromisoformat(trip_start).replace(tzinfo=local_tz)
    except ValueError:
        return {"next_refresh_at": None, "next_refresh_label": None}

    windows = []
    for window in REFRESH_WINDOWS:
        refresh_at = (trip_start_date - timedelta(days=window["days_before"])).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
        windows.append({
            "label": window["label"],
            "status": window["status"],
            "due_at": refresh_at.isoformat(),
        })

    upcoming = [entry for entry in windows if datetime.fromisoformat(entry["due_at"]) >= now_local]
    if not upcoming:
        return {
            "next_refresh_at": windows[-1]["due_at"],
            "next_refresh_label": windows[-1]["label"],
        }
    return {
        "next_refresh_at": upcoming[0]["due_at"],
        "next_refresh_label": upcoming[0]["label"],
    }


def _bundle_places(places: dict[str, dict[str, object]]) -> list[dict]:
    return sorted(
        [
            {
                "id": place_id,
                "name": place.get("name"),
                "address": place.get("address"),
                "kind": place.get("kind"),
                "maps_query": place.get("name"),
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
        output.append(
            {
                "id": _safe_str(leg.get("id")) or f"{from_id}-{to_id}",
                "mode": _safe_str(leg.get("mode")) or "car",
                "status": _as_status(leg.get("status")),
                "from_place": _safe_str(from_id),
                "to_place": _safe_str(to_id),
                "from_label": _safe_str(places.get(from_id, {}).get("name")) or from_id,
                "to_label": _safe_str(places.get(to_id, {}).get("name")) or to_id,
                "departure_at": _safe_time(_safe_str(leg.get("departure_at"))),
                "arrival_at": _safe_time(_safe_str(leg.get("arrival_at"))),
                "estimated_duration_minutes": _safe_int(leg.get("estimated_duration")),
                "distance_km": _safe_int(leg.get("distance_km")),
                "note": _safe_str(leg.get("note")),
                "source_refs": _as_list(leg.get("source_refs")),
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


def _bundle_operations(trip: dict) -> dict[str, Any]:
    raw = _as_dict(trip.get("operations"))
    return {
        "fuel": raw.get("fuel") or {},
        "supplies": raw.get("supplies") or [],
        "emergency": raw.get("emergency") or [],
        "handbook": raw.get("handbook") or [],
        "returns": raw.get("returns") or [],
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
                        "kind": "placeholder-anchored-reservation",
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
    evidence_ids = _collect_evidence_ids(trip, trip_path)
    source_hygiene_failures = _source_issues(trip)
    now_local = _now_local(trip.get("local_timezone", "Asia/Tokyo"))
    critical_issues = _collect_critical_issues(trip, trip_path, evidence_ids)
    critical_issues.extend(_collect_stale_selected_evidence_issues(trip, trip_path, now_local))
    if source_hygiene_failures:
        critical_issues.extend(
            [f"invalid source URL: {entry}" for entry in source_hygiene_failures]
        )

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

    severities = {item.get("severity") for item in validation_payload}
    trip_status = "ok"
    if "error" in severities:
        trip_status = "error"
    elif "warning" in severities or critical_issues:
        trip_status = "warning"
    if critical_issues:
        trip_status = "error"

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
        "validation": validation_payload,
        "critical_alerts": _bundle_critical_alerts(validation_payload),
        "source_ledger": source_ledger,
        "evidence_gate": {
            "status": "error" if critical_issues else "ok",
            "critical_issues": critical_issues,
            "source_hygiene_failures": source_hygiene_failures,
        },
        "refresh_schedule": {
            "windows": [
                {
                    "label": window["label"],
                    "days_before_trip_start": window["days_before"],
                    "status": window["status"],
                }
                for window in REFRESH_WINDOWS
            ],
            "next_refresh": _compute_next_refresh(
                trip,
                _now_local(trip.get("local_timezone", "Asia/Tokyo")),
            ),
        },
        "meta": {
            "generated_at": _today_iso(),
            "source_path": str(trip_path),
            "source_sha256": _sha256(trip_path),
            "trust_gate_version": "issue-59-v1",
            "trip_schema": trip.get("schema_version"),
            "theme_id": "setouchi-awaji",
            "source_coverage": {
                "places": len(place_index),
                "days": len(days),
                "selected_hotels": len(selected_hotel_ids),
                "selected_flights": len(selected_flight_ids),
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build public bundle for issue-52 awaji trip")
    parser.add_argument("--trip-path", type=Path, default=TRIP_PATH_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--web-output", type=Path, default=None)
    args = parser.parse_args()

    trip = _read_json(args.trip_path)
    bundle = build_public_bundle(trip, args.trip_path)
    _write_json(args.output, bundle)
    if args.web_output is not None:
        _write_json(args.web_output, bundle)


if __name__ == "__main__":
    main()
