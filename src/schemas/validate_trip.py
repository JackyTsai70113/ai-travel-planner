"""Dependency-free integrity checks for Canonical Trip V1 JSON documents."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
import re

from src.opening_hours import parse_clock, snapshot_from_mapping


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
    places = trip["candidate_sets"].get("places", [])
    place_ids = {place["id"] for place in places}
    if len(place_ids) != len(places):
        raise TripValidationError("candidate_sets.places contains duplicate place IDs")
    for index, place in enumerate(places):
        _require_canonical_id(place.get("id"), "candidate_sets.places[].id")
        _validate_place(place, f"candidate_sets.places[{index}]")
    transport_ids = {leg["id"] for leg in trip["candidate_sets"].get("transport_legs", [])}
    restaurant_ids: set[str] = set()
    for index, candidate in enumerate(trip["candidate_sets"].get("restaurants", [])):
        _validate_restaurant(candidate, index)
        place_id = candidate.get("place", {}).get("id")
        if place_id in restaurant_ids:
            raise TripValidationError("candidate_sets.restaurants contains duplicate canonical place IDs")
        restaurant_ids.add(place_id)
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
    except (TypeError, ValueError) as exc:
        raise TripValidationError(f"{path} is not ISO 8601 date-time") from exc


def _validate_place(place: object, path: str) -> None:
    if not isinstance(place, dict):
        raise TripValidationError(f"{path} must be an object")
    if "coordinates" in place:
        _validate_coordinates(place["coordinates"], f"{path}.coordinates")
    if "timezone" in place:
        try:
            ZoneInfo(place["timezone"])
        except (ZoneInfoNotFoundError, TypeError) as exc:
            raise TripValidationError(f"{path}.timezone must be a valid IANA timezone") from exc
    identifiers = place.get("identifiers", [])
    if not isinstance(identifiers, list):
        raise TripValidationError(f"{path}.identifiers must be an array")
    for index, identifier in enumerate(identifiers):
        identifier_path = f"{path}.identifiers[{index}]"
        if not isinstance(identifier, dict) or set(identifier) != {"type", "value", "provenance"}:
            raise TripValidationError(f"{identifier_path} has invalid fields")
        if identifier.get("type") not in {"google_place_id", "official_url", "provider_reference", "reservation_reference"}:
            raise TripValidationError(f"{identifier_path}.type is invalid")
        if not isinstance(identifier.get("value"), str) or not identifier["value"].strip():
            raise TripValidationError(f"{identifier_path}.value is required")
        _require_provenance(identifier.get("provenance"), f"{identifier_path}.provenance")
    points = place.get("navigation_points", [])
    if not isinstance(points, list):
        raise TripValidationError(f"{path}.navigation_points must be an array")
    allowed_point_fields = {"id", "kind", "name", "coordinates", "google_maps_url", "phone", "mapcode", "provenance"}
    for index, point in enumerate(points):
        point_path = f"{path}.navigation_points[{index}]"
        if not isinstance(point, dict) or set(point) - allowed_point_fields:
            raise TripValidationError(f"{point_path} has invalid fields")
        _require_canonical_id(point.get("id"), f"{point_path}.id")
        if point.get("kind") not in {"entrance", "parking", "station_exit", "meeting_point", "other"}:
            raise TripValidationError(f"{point_path}.kind is invalid")
        if not any(key in point for key in ("coordinates", "google_maps_url", "phone", "mapcode")):
            raise TripValidationError(f"{point_path} requires a routing reference")
        if "coordinates" in point:
            _validate_coordinates(point["coordinates"], f"{point_path}.coordinates")
        if "provenance" in point:
            _require_provenance(point["provenance"], f"{point_path}.provenance")
    conflicts = place.get("coordinate_conflicts", [])
    if not isinstance(conflicts, list):
        raise TripValidationError(f"{path}.coordinate_conflicts must be an array")
    for index, conflict in enumerate(conflicts):
        conflict_path = f"{path}.coordinate_conflicts[{index}]"
        if not isinstance(conflict, dict) or set(conflict) != {"coordinates", "provenance"}:
            raise TripValidationError(f"{conflict_path} has invalid fields")
        _validate_coordinates(conflict["coordinates"], f"{conflict_path}.coordinates")
        _require_provenance(conflict["provenance"], f"{conflict_path}.provenance")
    field_provenance = place.get("field_provenance", {})
    if not isinstance(field_provenance, dict):
        raise TripValidationError(f"{path}.field_provenance must be an object")
    for field_name, values in field_provenance.items():
        provenance_path = f"{path}.field_provenance.{field_name}"
        if not isinstance(values, list) or not values:
            raise TripValidationError(f"{provenance_path} must be a non-empty array")
        for index, value in enumerate(values):
            _require_provenance(value, f"{provenance_path}[{index}]")
    resolution = place.get("resolution")
    if resolution is not None:
        if not isinstance(resolution, dict) or set(resolution) - {"state", "confidence", "clarification"}:
            raise TripValidationError(f"{path}.resolution has invalid fields")
        if resolution.get("state") not in {"resolved", "clarification_required", "unresolved"}:
            raise TripValidationError(f"{path}.resolution.state is invalid")
        confidence = resolution.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise TripValidationError(f"{path}.resolution.confidence must be between 0 and 1")


def _validate_coordinates(value: object, path: str) -> None:
    if not isinstance(value, dict) or set(value) != {"latitude", "longitude"}:
        raise TripValidationError(f"{path} requires latitude and longitude")
    latitude, longitude = value["latitude"], value["longitude"]
    if (
        not isinstance(latitude, (int, float)) or isinstance(latitude, bool)
        or not isinstance(longitude, (int, float)) or isinstance(longitude, bool)
        or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
    ):
        raise TripValidationError(f"{path} is outside coordinate bounds")


def _validate_restaurant(candidate: object, index: int) -> None:
    path = f"candidate_sets.restaurants[{index}]"
    if not isinstance(candidate, dict) or not isinstance(candidate.get("place"), dict):
        raise TripValidationError(f"{path} must contain place")
    _require_canonical_id(candidate["place"].get("id"), f"{path}.place.id")
    _require_provenance(candidate.get("provenance"), f"{path}.provenance")
    for rating_index, rating in enumerate(candidate.get("ratings", [])):
        rating_path = f"{path}.ratings[{rating_index}]"
        if not isinstance(rating, dict):
            raise TripValidationError(f"{rating_path} must be an object")
        values = (rating.get("value"), rating.get("scale_min"), rating.get("scale_max"))
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
            raise TripValidationError(f"{rating_path} requires numeric value and original scale")
        value, scale_min, scale_max = values
        if scale_min >= scale_max or not scale_min <= value <= scale_max:
            raise TripValidationError(f"{rating_path}.value must fall within its original scale")
        if "review_count" in rating and (
            not isinstance(rating["review_count"], int)
            or isinstance(rating["review_count"], bool)
            or rating["review_count"] < 0
        ):
            raise TripValidationError(f"{rating_path}.review_count must be a non-negative integer")
        _require_provenance(rating.get("provenance"), f"{rating_path}.provenance")
    for dish_index, dish in enumerate(candidate.get("recommended_dishes", [])):
        dish_path = f"{path}.recommended_dishes[{dish_index}]"
        if not isinstance(dish, dict) or not isinstance(dish.get("name"), str) or not dish["name"].strip():
            raise TripValidationError(f"{dish_path}.name is required")
        _require_provenance(dish.get("provenance"), f"{dish_path}.provenance")
    for signal_index, signal in enumerate(candidate.get("meal_price_signals", [])):
        signal_path = f"{path}.meal_price_signals[{signal_index}]"
        if not isinstance(signal, dict) or signal.get("meal") not in {"breakfast", "lunch", "dinner", "unspecified"}:
            raise TripValidationError(f"{signal_path}.meal is invalid")
        if not any(key in signal for key in ("label", "minimum", "maximum")):
            raise TripValidationError(f"{signal_path} requires a price label or bound")
        _require_provenance(signal.get("provenance"), f"{signal_path}.provenance")
    for source_index, source in enumerate(candidate.get("source_provenance", [])):
        _require_provenance(source, f"{path}.source_provenance[{source_index}]")
    for alternative_index, alternative in enumerate(candidate.get("alternatives", [])):
        alternative_path = f"{path}.alternatives[{alternative_index}]"
        if not isinstance(alternative, dict) or not isinstance(alternative.get("field"), str) or "value" not in alternative:
            raise TripValidationError(f"{alternative_path} requires field and value")
        _require_provenance(alternative.get("provenance"), f"{alternative_path}.provenance")
    hours = candidate.get("opening_hours")
    if hours is not None:
        _validate_opening_hours(hours, f"{path}.opening_hours")


def _validate_opening_hours(hours: object, path: str) -> None:
    if not isinstance(hours, dict):
        raise TripValidationError(f"{path} must be an object")
    if hours.get("status") not in {"fresh", "stale", "unverified", "conflicting"}:
        raise TripValidationError(f"{path}.status is invalid")
    timezone_name = hours.get("timezone")
    if timezone_name is not None:
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, TypeError) as exc:
            raise TripValidationError(f"{path}.timezone must be a valid IANA timezone") from exc
    raw_intervals = hours.get("intervals")
    if not isinstance(raw_intervals, list) or not all(isinstance(interval, dict) for interval in raw_intervals):
        raise TripValidationError(f"{path}.intervals must contain objects")
    closed_weekdays = hours.get("closed_weekdays", [])
    if (
        not isinstance(closed_weekdays, list)
        or not all(isinstance(day, int) and not isinstance(day, bool) and 0 <= day <= 6 for day in closed_weekdays)
        or len(closed_weekdays) != len(set(closed_weekdays))
    ):
        raise TripValidationError(f"{path}.closed_weekdays must contain unique weekdays 0-6")
    raw_special = hours.get("special_hours", [])
    if not isinstance(raw_special, list) or not all(isinstance(item, dict) for item in raw_special):
        raise TripValidationError(f"{path}.special_hours must contain objects")
    for special_index, special in enumerate(raw_special):
        special_path = f"{path}.special_hours[{special_index}]"
        try:
            datetime.strptime(str(special.get("date")), "%Y-%m-%d")
        except ValueError as exc:
            raise TripValidationError(f"{special_path}.date must be an ISO date") from exc
        if special.get("status") not in {"open", "closed", "unverified"}:
            raise TripValidationError(f"{special_path}.status is invalid")
        if not isinstance(special.get("intervals"), list) or not all(isinstance(item, dict) for item in special["intervals"]):
            raise TripValidationError(f"{special_path}.intervals must contain objects")
    if "provenance" in hours:
        _require_provenance(hours["provenance"], f"{path}.provenance")
    try:
        snapshot = snapshot_from_mapping(hours, default_timezone=timezone_name or "UTC")
    except (KeyError, TypeError, ValueError) as exc:
        raise TripValidationError(f"{path} contains an invalid interval: {exc}") from exc
    for interval_index, interval in enumerate(snapshot.intervals):
        _validate_parsed_interval(interval, f"{path}.intervals[{interval_index}]")
    for special_index, special in enumerate(snapshot.special_hours):
        for interval_index, interval in enumerate(special.intervals):
            _validate_parsed_interval(interval, f"{path}.special_hours[{special_index}].intervals[{interval_index}]")
    dates = [value.date for value in snapshot.special_hours]
    if len(dates) != len(set(dates)):
        raise TripValidationError(f"{path}.special_hours contains duplicate dates")
    for special in snapshot.special_hours:
        if special.status == "closed" and special.intervals:
            raise TripValidationError(f"{path}.special_hours closed dates cannot contain intervals")
        if special.status == "open" and not special.intervals:
            raise TripValidationError(f"{path}.special_hours open dates require intervals")
    # Explicitly exercise the same parser used at runtime so 24-29h values can
    # never pass contract validation and fail later in the planner.
    for interval in hours.get("intervals", []):
        if isinstance(interval, dict):
            for field in ("opens_at", "closes_at", "last_order_at"):
                if field in interval:
                    try:
                        parse_clock(interval[field], field=field)
                    except ValueError as exc:
                        raise TripValidationError(f"{path}.{field}: {exc}") from exc


def _validate_parsed_interval(interval, path: str) -> None:
    if interval.opens_at == interval.closes_at and interval.closes_day_offset != 1:
        raise TripValidationError(f"{path} equal endpoints require closes_day_offset=1")
    if interval.last_order_at is not None:
        from datetime import timedelta

        base = datetime(2026, 1, 5)
        opens = datetime.combine(base.date(), interval.opens_at)
        closes = datetime.combine(base.date(), interval.closes_at) + timedelta(days=interval.closes_day_offset)
        last_order = datetime.combine(base.date(), interval.last_order_at) + timedelta(days=interval.last_order_day_offset)
        if not opens <= last_order <= closes:
            raise TripValidationError(f"{path}.last_order_at must fall within the interval")


def _require_provenance(value: object, path: str) -> None:
    if not isinstance(value, dict):
        raise TripValidationError(f"{path} is required")
    for field in ("source_type", "provider", "retrieved_at", "status"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise TripValidationError(f"{path}.{field} is required")
    _require_offset(value["retrieved_at"], f"{path}.retrieved_at")


def _require_canonical_id(value: object, path: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[a-z][a-z0-9_-]*", value) is None:
        raise TripValidationError(f"{path} must be a canonical lowercase ID")


def load_trip(path: str | Path) -> dict:
    """Load JSON, validate it, and return a JSON-compatible Trip V1 object."""
    with Path(path).open(encoding="utf-8") as source:
        trip = json.load(source)
    validate_trip(trip)
    return trip
