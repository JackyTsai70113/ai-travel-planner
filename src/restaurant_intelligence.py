"""Canonical restaurant operational facts and deterministic meal eligibility.

This module is deliberately provider-neutral.  It consumes normalized weekly
hours and is shared by scheduling composition and validation-context builders;
it never reads provider payloads or mutates a final itinerary.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Iterable, Mapping, Sequence

from src.validator import OpeningInterval


def opening_intervals(candidate: Mapping[str, object]) -> tuple[OpeningInterval, ...]:
    hours = candidate.get("opening_hours")
    if not isinstance(hours, Mapping) or hours.get("status") != "fresh":
        return ()
    intervals = []
    for value in hours.get("intervals", []):
        if not isinstance(value, Mapping):
            continue
        try:
            intervals.append(OpeningInterval(int(value["weekday"]), time.fromisoformat(str(value["opens_at"])), time.fromisoformat(str(value["closes_at"]))))
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(intervals)


def restaurant_intelligence(
    candidate: Mapping[str, object], *, recommended_dishes: Sequence[Mapping[str, object]] = ()
) -> dict[str, object]:
    """Return a canonical restaurant candidate with evidence-bound dish facts.

    Places providers are authoritative for operational facts such as ratings and
    hours, but they do not generally supply a reliable menu.  Callers may add
    dish recommendations only with their own canonical provenance record.  The
    helper deliberately rejects provider-specific payloads and never upgrades
    reported community evidence into a confirmed operational fact.
    """
    normalized = dict(candidate)
    accepted: list[dict[str, object]] = []
    for dish in recommended_dishes:
        name = dish.get("name")
        provenance = dish.get("provenance")
        if not isinstance(name, str) or not name.strip() or not isinstance(provenance, Mapping):
            continue
        if not isinstance(provenance.get("provider"), str) or not isinstance(provenance.get("retrieved_at"), str):
            continue
        item: dict[str, object] = {"name": name.strip(), "provenance": dict(provenance)}
        if isinstance(dish.get("note"), str):
            item["note"] = dish["note"]
        accepted.append(item)
    if accepted:
        normalized["recommended_dishes"] = accepted
    return normalized


def meal_eligible(candidate: Mapping[str, object], start: datetime, end: datetime) -> bool:
    """Return true only when the complete local meal interval is confirmed open."""
    if start.date() != end.date():
        return False
    return any(interval.weekday == start.weekday() and interval.opens_at <= start.timetz().replace(tzinfo=None) and end.timetz().replace(tzinfo=None) <= interval.closes_at for interval in opening_intervals(candidate))


def eligible_restaurants(candidates: Iterable[Mapping[str, object]], start: datetime, end: datetime) -> list[Mapping[str, object]]:
    return [candidate for candidate in candidates if meal_eligible(candidate, start, end)]


def validation_opening_hours(restaurants: Iterable[Mapping[str, object]]) -> dict[str, tuple[OpeningInterval, ...]]:
    result = {}
    for candidate in restaurants:
        place = candidate.get("place", {})
        if isinstance(place, Mapping) and isinstance(place.get("id"), str):
            intervals = opening_intervals(candidate)
            if intervals:
                result[place["id"]] = intervals
    return result
