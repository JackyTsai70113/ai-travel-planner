"""Build a deterministic public-safe bundle for the Awaji 2026 trip."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

TRIP_PATH_DEFAULT = Path("trips/awaji-naruto-tokushima-kobe-2026/trip.json")
OUTPUT_DEFAULT = Path("trips/awaji-naruto-tokushima-kobe-2026/public-bundle.json")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


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
    return value[:16]


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
    places = {place.get("id"): place for place in trip.get("candidate_sets", {}).get("places", []) if isinstance(place, dict)}
    days = _bundle_days(trip)
    reservations = _bundle_reservations(days, places)
    validation = trip.get("validation", [])
    budget = trip.get("budget", {})

    return {
        "trip_id": trip.get("id"),
        "title": trip.get("title"),
        "local_timezone": trip.get("local_timezone"),
        "status": "warning" if any(item.get("severity") == "warning" for item in validation if isinstance(item, dict)) else "ok",
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
        "meta": {
            "generated_at": _today_iso(),
            "source_path": str(trip_path),
            "source_sha256": _sha256(trip_path),
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
