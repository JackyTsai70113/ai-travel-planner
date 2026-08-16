"""Build a deterministic public-safe bundle for the Awaji 2026 trip."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


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
    evidence_ids = _collect_evidence_ids(trip, trip_path)
    source_hygiene_failures = _source_issues(trip)
    critical_issues = _collect_critical_issues(trip, trip_path, evidence_ids)
    if source_hygiene_failures:
        critical_issues.extend(
            [f"invalid source URL: {entry}" for entry in source_hygiene_failures]
        )
    places = {place.get("id"): place for place in trip.get("candidate_sets", {}).get("places", []) if isinstance(place, dict)}
    days = _bundle_days(trip)
    reservations = _bundle_reservations(days, places)
    validation = trip.get("validation", [])
    budget = trip.get("budget", {})

    severities = {item.get("severity") for item in validation if isinstance(item, dict)}
    trip_status = "ok"
    if "error" in severities:
        trip_status = "error"
    elif "warning" in severities or critical_issues:
        trip_status = "warning"
    if critical_issues:
        trip_status = "error"

    return {
        "trip_id": trip.get("id"),
        "title": trip.get("title"),
        "local_timezone": trip.get("local_timezone"),
        "places": _bundle_places(places),
        "status": trip_status,
        "date_range": trip.get("date_range", {}),
        "traveler_profile": _build_profile(trip),
        "selected": {
            "hotel_place_ids": trip.get("selected", {}).get("hotel_place_ids", []),
            "flight_ids": trip.get("selected", {}).get("flight_ids", []),
        },
        "days": days,
        "reservations": reservations,
        "preferences": _public_preferences(trip.get("preferences", {})),
        "budget": {
            "currency": budget.get("currency"),
            "total": budget.get("total"),
            "categories": budget.get("categories", {}),
        },
        "validation": [
            item
            for item in validation
            if isinstance(item, dict)
        ],
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
