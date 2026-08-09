"""Dependency-free integrity checks for Canonical Trip V1 JSON documents."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json


class TripValidationError(ValueError):
    """Raised when a Trip V1 contract invariant is violated."""


def validate_trip(trip: dict) -> None:
    required = {"schema_version", "local_timezone", "candidate_sets", "days", "budget", "provenance"}
    missing = required - trip.keys()
    if missing:
        raise TripValidationError(f"missing required fields: {', '.join(sorted(missing))}")
    if trip["schema_version"] != "trip-v1":
        raise TripValidationError("schema_version must be trip-v1")
    try:
        ZoneInfo(trip["local_timezone"])
    except (ZoneInfoNotFoundError, TypeError) as exc:
        raise TripValidationError("local_timezone must be a valid IANA timezone") from exc

    _require_money_currency(trip, "trip")
    place_ids = {place["id"] for place in trip["candidate_sets"].get("places", [])}
    transport_ids = {leg["id"] for leg in trip["candidate_sets"].get("transport_legs", [])}
    for day_index, day in enumerate(trip["days"]):
        for item_index, item in enumerate(day.get("items", [])):
            path = f"days[{day_index}].items[{item_index}]"
            if item.get("place_id") not in place_ids:
                raise TripValidationError(f"{path}.place_id does not reference candidate_sets.places")
            if "transport_leg_id" in item and item["transport_leg_id"] not in transport_ids:
                raise TripValidationError(f"{path}.transport_leg_id does not reference candidate_sets.transport_legs")
            _require_offset(item["start_at"], f"{path}.start_at")
            _require_offset(item["end_at"], f"{path}.end_at")


def _require_money_currency(value: object, path: str) -> None:
    if isinstance(value, dict):
        if "amount" in value and "currency" not in value:
            raise TripValidationError(f"{path} monetary value is missing currency")
        for key, child in value.items():
            _require_money_currency(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _require_money_currency(child, f"{path}[{index}]")


def _require_offset(value: str, path: str) -> None:
    try:
        if datetime.fromisoformat(value).tzinfo is None:
            raise TripValidationError(f"{path} must include a timezone offset")
    except ValueError as exc:
        raise TripValidationError(f"{path} is not ISO 8601 date-time") from exc


def load_trip(path: str | Path) -> dict:
    """Load JSON, validate it, and return a JSON-compatible Trip V1 object."""
    with Path(path).open(encoding="utf-8") as source:
        trip = json.load(source)
    validate_trip(trip)
    return trip
