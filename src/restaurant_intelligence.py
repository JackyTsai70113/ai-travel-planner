"""Canonical restaurant facts, reconciliation, and meal eligibility."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from src.opening_hours import (
    Eligibility,
    HoursStatus,
    OpeningHoursSnapshot,
    OpeningInterval,
    evaluate_opening_hours,
    snapshot_from_mapping,
    snapshot_to_mapping,
)


def opening_hours_snapshot(candidate: Mapping[str, object], *, default_timezone: str | None = None) -> OpeningHoursSnapshot:
    return snapshot_from_mapping(candidate.get("opening_hours"), default_timezone=default_timezone)


def opening_intervals(candidate: Mapping[str, object]) -> tuple[OpeningInterval, ...]:
    """Legacy projection retained for interval-only callers."""

    try:
        snapshot = opening_hours_snapshot(candidate)
    except (KeyError, TypeError, ValueError):
        return ()
    return snapshot.intervals if snapshot.status is HoursStatus.FRESH else ()


def restaurant_intelligence(
    candidate: Mapping[str, object], *, recommended_dishes: Sequence[Mapping[str, object]] = ()
) -> dict[str, object]:
    """Return a canonical candidate with evidence-bound dish facts only."""

    normalized = dict(candidate)
    accepted: list[dict[str, object]] = []
    for dish in recommended_dishes:
        name = dish.get("name")
        provenance = dish.get("provenance")
        if not isinstance(name, str) or not name.strip() or not _valid_provenance(provenance):
            continue
        item: dict[str, object] = {"name": name.strip(), "provenance": dict(provenance)}
        if isinstance(dish.get("note"), str):
            item["note"] = dish["note"]
        accepted.append(item)
    if accepted:
        normalized["recommended_dishes"] = accepted
    return normalized


def meal_eligibility(candidate: Mapping[str, object], start: datetime, end: datetime) -> Eligibility:
    try:
        if candidate.get("business_status") in {"closed_temporarily", "closed_permanently"}:
            return Eligibility.CLOSED
        return evaluate_opening_hours(opening_hours_snapshot(candidate), start, end).status
    except (KeyError, TypeError, ValueError):
        return Eligibility.UNVERIFIED


def meal_eligible(candidate: Mapping[str, object], start: datetime, end: datetime) -> bool:
    return meal_eligibility(candidate, start, end) is Eligibility.ELIGIBLE


def eligible_restaurants(candidates: Iterable[Mapping[str, object]], start: datetime, end: datetime) -> list[Mapping[str, object]]:
    """Strict production gate: unknown, stale, conflicting, and closed are excluded."""

    return [candidate for candidate in candidates if meal_eligible(candidate, start, end)]


def validation_opening_hours(restaurants: Iterable[Mapping[str, object]]) -> dict[str, OpeningHoursSnapshot | Mapping[str, object]]:
    result: dict[str, OpeningHoursSnapshot | Mapping[str, object]] = {}
    for candidate in restaurants:
        place = candidate.get("place", {})
        if isinstance(place, Mapping) and isinstance(place.get("id"), str):
            hours = candidate.get("opening_hours")
            # Let the validator inject Trip.local_timezone for the legacy shape.
            result[place["id"]] = dict(hours) if isinstance(hours, Mapping) and not hours.get("timezone") else opening_hours_snapshot(candidate)
    return result


def reconcile_restaurant_candidates(candidates: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Merge facts only for an exact canonical place ID.

    Names are never used as identity.  Fresh official operational facts win;
    lower-authority values remain auditable as alternatives.  Contradictory
    top-authority opening-hours snapshots are marked ``conflicting`` so no
    planner can select them as confirmed.
    """

    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    order: list[str] = []
    for candidate in candidates:
        place = candidate.get("place")
        place_id = place.get("id") if isinstance(place, Mapping) else None
        if not isinstance(place_id, str):
            continue
        if place_id not in grouped:
            order.append(place_id)
        grouped[place_id].append(candidate)
    return [_reconcile_group(grouped[place_id]) for place_id in order]


def _reconcile_group(group: Sequence[Mapping[str, object]]) -> dict[str, object]:
    ranked = sorted(group, key=lambda item: (_authority(item), _freshness(item)))
    result: dict[str, object] = {"provenance": _copy_value(_provenance(ranked[0]))}
    place_sources = [candidate for candidate in ranked if isinstance(candidate.get("place"), Mapping)]
    if place_sources:
        place_source = min(place_sources, key=_place_rank)
        result["place"] = _copy_value(place_source["place"])
    source_provenance = _unique_provenance(ranked)
    if source_provenance:
        result["source_provenance"] = source_provenance
    alternatives: list[dict[str, object]] = []
    for candidate in ranked:
        candidate_alternatives = candidate.get("alternatives")
        if isinstance(candidate_alternatives, Sequence) and not isinstance(candidate_alternatives, (str, bytes)):
            alternatives.extend(
                dict(_copy_value(alternative))
                for alternative in candidate_alternatives
                if isinstance(alternative, Mapping)
            )
    operational = (
        "opening_hours", "reservation_required", "reservation_url", "child_friendly",
        "smoking_policy", "parking_available", "business_status",
    )
    for field in operational:
        sources = sorted((candidate for candidate in ranked if field in candidate), key=lambda item: _operational_rank(item, field))
        if not sources:
            continue
        best_rank = _operational_rank(sources[0], field)
        peers = [item for item in sources if _operational_rank(item, field) == best_rank]
        values = {_fact_value(item[field]) for item in peers}
        if field == "opening_hours" and len(values) > 1:
            snapshots = [dict(item[field]) for item in peers if isinstance(item[field], Mapping)]
            base = snapshot_from_mapping(snapshots[0])
            result[field] = snapshot_to_mapping(OpeningHoursSnapshot(
                HoursStatus.CONFLICTING,
                base.timezone,
                base.intervals,
                base.closed_weekdays,
                base.regular_holidays,
                base.special_hours,
                base.provenance,
                tuple(snapshots),
                "same-authority opening-hours conflict",
            ))
        else:
            result[field] = _copy_value(sources[0][field])
        for source in sources[1:]:
            if _fact_value(source[field]) != _fact_value(result[field]):
                alternatives.append({"field": field, "value": _copy_value(source[field]), "provenance": dict(_provenance(source))})
    for candidate in ranked:
        for field in ("ratings", "meal_price_signals", "recommended_dishes"):
            if isinstance(candidate.get(field), list):
                existing = result.setdefault(field, [])
                if isinstance(existing, list):
                    for value in candidate[field]:
                        if _stable_value(value) not in {_stable_value(item) for item in existing}:
                            existing.append(_copy_value(value))
    rating_bundle = ("rating", "rating_source", "review_count")
    rating_sources = sorted((candidate for candidate in ranked if "rating" in candidate), key=lambda item: _quality_rank(item, "rating"))
    if rating_sources:
        selected_rating = rating_sources[0]
        for field in rating_bundle:
            if field in selected_rating:
                result[field] = _copy_value(selected_rating[field])
        for source in rating_sources[1:]:
            for field in rating_bundle:
                if field in source and (field not in result or _fact_value(source[field]) != _fact_value(result[field])):
                    alternatives.append({
                        "field": field,
                        "value": _copy_value(source[field]),
                        "provenance": dict(_provenance(source)),
                    })
    else:
        count_sources = sorted((candidate for candidate in ranked if "review_count" in candidate), key=lambda item: _quality_rank(item, "review_count"))
        if count_sources:
            result["review_count"] = _copy_value(count_sources[0]["review_count"])
            for source in count_sources[1:]:
                if _fact_value(source["review_count"]) != _fact_value(result["review_count"]):
                    alternatives.append({
                        "field": "review_count",
                        "value": _copy_value(source["review_count"]),
                        "provenance": dict(_provenance(source)),
                    })
    quality = ("cuisine", "price_range", "wait_risk")
    for field in quality:
        sources = sorted((candidate for candidate in ranked if field in candidate), key=lambda item: _quality_rank(item, field))
        if not sources:
            continue
        result[field] = _copy_value(sources[0][field])
        for source in sources[1:]:
            if _fact_value(source[field]) != _fact_value(result[field]):
                alternatives.append({
                    "field": field,
                    "value": _copy_value(source[field]),
                    "provenance": dict(_provenance(source)),
                })
    attributions: list[str] = []
    for candidate in ranked:
        values = candidate.get("attributions")
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            attributions.extend(value for value in values if isinstance(value, str) and value)
    if attributions:
        result["attributions"] = list(dict.fromkeys(attributions))
    if alternatives:
        result["alternatives"] = _unique_alternatives(alternatives)
    return result


def _authority(candidate: Mapping[str, object]) -> int:
    return {"official": 0, "provider": 1, "community": 2, "derived": 3, "user_input": 4}.get(
        str(_provenance(candidate).get("source_type")), 99
    )


def _place_rank(candidate: Mapping[str, object]) -> tuple[int, int, int]:
    """Keep one source-coherent place record, preferring routing coordinates."""

    place = candidate.get("place")
    if not isinstance(place, Mapping):
        return 1, 1, _authority(candidate)
    coordinates = place.get("coordinates")
    has_coordinates = (
        isinstance(coordinates, Mapping)
        and isinstance(coordinates.get("latitude"), (int, float))
        and not isinstance(coordinates.get("latitude"), bool)
        and isinstance(coordinates.get("longitude"), (int, float))
        and not isinstance(coordinates.get("longitude"), bool)
    )
    has_address = isinstance(place.get("address"), str) and bool(place["address"])
    return int(not has_coordinates), int(not has_address), _authority(candidate)


def _quality_rank(candidate: Mapping[str, object], field: str) -> tuple[int, int]:
    """Prefer discovery evidence for quality fields; official priority is operational."""

    source_type = str(_provenance(candidate).get("source_type"))
    authority = {"provider": 0, "community": 1, "official": 2, "derived": 3, "user_input": 4}.get(source_type, 99)
    unknown = field == "wait_risk" and candidate.get(field) == "unknown"
    return int(unknown), authority


def _freshness(candidate: Mapping[str, object]) -> int:
    hours = candidate.get("opening_hours")
    if isinstance(hours, Mapping):
        return {"fresh": 0, "stale": 1, "unverified": 2, "conflicting": 3}.get(str(hours.get("status")), 4)
    return 4


def _operational_rank(candidate: Mapping[str, object], field: str) -> tuple[int, int]:
    if field == "opening_hours":
        return _freshness(candidate), _authority(candidate)
    return 0, _authority(candidate)


def _provenance(candidate: Mapping[str, object]) -> Mapping[str, object]:
    value = candidate.get("provenance")
    if isinstance(value, Mapping):
        return value
    place = candidate.get("place")
    if isinstance(place, Mapping) and isinstance(place.get("provenance"), Mapping):
        return place["provenance"]
    return {}


def _valid_provenance(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(value.get("provider"), str)
        and bool(value.get("provider"))
        and isinstance(value.get("retrieved_at"), str)
        and isinstance(value.get("source_type"), str)
        and isinstance(value.get("status"), str)
    )


def _unique_provenance(candidates: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    seen: set[str] = set()
    for candidate in candidates:
        provenance_values: list[Mapping[str, object]] = []
        direct = _provenance(candidate)
        if direct:
            provenance_values.append(direct)
        place = candidate.get("place")
        if isinstance(place, Mapping) and isinstance(place.get("provenance"), Mapping):
            provenance_values.append(place["provenance"])
        nested = candidate.get("source_provenance")
        if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes)):
            provenance_values.extend(value for value in nested if isinstance(value, Mapping))
        for provenance in provenance_values:
            key = _stable_value(provenance)
            if key not in seen:
                seen.add(key)
                values.append(dict(provenance))
    return values


def _unique_alternatives(alternatives: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    seen: set[str] = set()
    for alternative in alternatives:
        key = _stable_value({
            "field": alternative.get("field"),
            "value": alternative.get("value"),
            "provenance": alternative.get("provenance"),
        })
        if key not in seen:
            seen.add(key)
            values.append(dict(alternative))
    return values


def _stable_value(value: object) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _fact_value(value: object) -> str:
    if isinstance(value, Mapping):
        value = {key: child for key, child in value.items() if key not in {"provenance", "alternatives"}}
    return _stable_value(value)


def _copy_value(value: object) -> object:
    import copy
    return copy.deepcopy(value)


def _deep_copy_candidate(value: Mapping[str, object]) -> dict[str, object]:
    copied = _copy_value(value)
    assert isinstance(copied, dict)
    return copied
