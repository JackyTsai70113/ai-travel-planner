"""Canonical restaurant operational facts and deterministic meal eligibility.

This module is deliberately provider-neutral.  It consumes normalized weekly
hours and is shared by scheduling composition and validation-context builders;
it never reads provider payloads or mutates a final itinerary.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Iterable, Mapping

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
