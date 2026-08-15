"""Route-aware synthesis of Canonical Trip day plans from normalized facts."""

from __future__ import annotations

import copy
from datetime import date, datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from src.conditions import evaluate_conditions
from src.validator import OpeningInterval, Violation

from .contracts import ScheduledTrip, ScheduleState, SchedulingInput, SchedulingOutput


def schedule(request: SchedulingInput) -> SchedulingOutput:
    """Build one deterministic Candidate Trip without filling unknown facts.

    Candidate facts are read only from the canonical candidate sets.  In
    particular, an absent route, duration, or opening-hour interval is an
    explicit failure, never a zero-minute/default assumption.
    """
    trip = copy.deepcopy(request.trip)
    violations: list[Violation] = []
    start, end = _date_range(trip, violations)
    hotel_id = _hotel_id(trip, violations)
    activities = _activities(trip, violations)
    if violations or start is None or end is None or hotel_id is None:
        return SchedulingOutput((ScheduledTrip(trip, ScheduleState.FAILED, tuple(violations)),))

    anchors_by_date = _anchors(trip, violations)
    days: list[dict] = []
    unscheduled = {activity["id"] for activity in activities if activity["schedule"].get("day") is None}
    total_days = (end - start).days + 1
    for offset in range(total_days):
        current = start + timedelta(days=offset)
        planned, day_violations, placed = _schedule_day(
            current, offset + 1, hotel_id, activities, anchors_by_date.get(current.isoformat(), ()), unscheduled, request,
        )
        violations.extend(day_violations)
        unscheduled.difference_update(placed)
        days.append({"date": current.isoformat(), "summary": "", "items": planned})
    for activity_id in unscheduled:
        violations.append(_failure("schedule.no_feasible_day", f"required activity {activity_id} has no feasible day", "/candidate_sets"))
    if violations:
        return SchedulingOutput((ScheduledTrip(trip, ScheduleState.FAILED, tuple(violations)),))
    trip["days"] = days
    return SchedulingOutput((ScheduledTrip(trip, ScheduleState.READY, (),),))


def _date_range(trip: dict, violations: list[Violation]) -> tuple[date | None, date | None]:
    try:
        dates = trip["date_range"]
        start, end = date.fromisoformat(dates["start_date"]), date.fromisoformat(dates["end_date"])
        if end < start:
            raise ValueError
        return start, end
    except (KeyError, TypeError, ValueError):
        violations.append(_failure("schedule.date_range_missing", "trip requires a valid explicit date range", "/date_range"))
        return None, None


def _hotel_id(trip: dict, violations: list[Violation]) -> str | None:
    hotels = trip.get("selected", {}).get("hotel_place_ids", [])
    if len(hotels) != 1 or not isinstance(hotels[0], str):
        violations.append(_failure("schedule.hotel_missing", "exactly one selected hotel is required for daily routing", "/selected/hotel_place_ids"))
        return None
    return hotels[0]


def _activities(trip: dict, violations: list[Violation]) -> list[dict]:
    records: list[dict] = []
    for collection in ("places", "restaurants"):
        for index, candidate in enumerate(trip.get("candidate_sets", {}).get(collection, [])):
            place = candidate.get("place", candidate) if collection == "restaurants" else candidate
            details = candidate.get("schedule")
            if not details or not details.get("selected", True):
                continue
            if not isinstance(details.get("duration_minutes"), int) or details["duration_minutes"] <= 0:
                violations.append(_failure("schedule.duration_missing", "selected activity requires an explicit positive duration", f"/candidate_sets/{collection}/{index}/schedule/duration_minutes"))
                continue
            if not isinstance(place.get("id"), str):
                violations.append(_failure("schedule.place_missing", "activity has no canonical place id", f"/candidate_sets/{collection}/{index}"))
                continue
            day = details.get("day")
            if day is not None and (not isinstance(day, int) or day < 1):
                violations.append(_failure("schedule.day_invalid", "activity day must be a positive integer", f"/candidate_sets/{collection}/{index}/schedule/day"))
                continue
            if (details.get("fixed_start_at") is None) != (details.get("fixed_end_at") is None):
                violations.append(_failure("schedule.fixed_anchor_invalid", "fixed anchors require both start and end timestamps", f"/candidate_sets/{collection}/{index}/schedule"))
                continue
            if not isinstance(details.get("fatigue", 0), (int, float)) or details.get("fatigue", 0) < 0:
                violations.append(_failure("schedule.fatigue_invalid", "fatigue must be a non-negative number", f"/candidate_sets/{collection}/{index}/schedule/fatigue"))
                continue
            records.append({"id": place["id"], "kind": "meal" if collection == "restaurants" else "visit", "schedule": details, "path": f"/candidate_sets/{collection}/{index}"})
    return records


def _anchors(trip: dict, violations: list[Violation]) -> dict[str, tuple[dict, ...]]:
    """Retain confirmed operational items already present in the Canonical Trip."""
    anchors: dict[str, tuple[dict, ...]] = {}
    for day_index, day in enumerate(trip.get("days", [])):
        current_date = day.get("date")
        if not isinstance(current_date, str):
            violations.append(_failure("schedule.anchor_date_missing", "existing DayPlan anchor lacks a date", f"/days/{day_index}/date"))
            continue
        items = []
        for item_index, item in enumerate(day.get("items", [])):
            if item.get("kind") in {"visit", "meal"}:
                continue
            try:
                datetime.fromisoformat(item["start_at"])
                datetime.fromisoformat(item["end_at"])
                if not item.get("place_id"):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                violations.append(_failure("schedule.anchor_invalid", "confirmed anchor requires place and timestamps", f"/days/{day_index}/items/{item_index}"))
                continue
            items.append(copy.deepcopy(item))
        anchors[current_date] = tuple(sorted(items, key=lambda item: item["start_at"]))
    return anchors


def _schedule_day(current: date, day_number: int, hotel_id: str, activities: Iterable[dict], anchors: Iterable[dict], unscheduled: set[str], request: SchedulingInput) -> tuple[list[dict], list[Violation], set[str]]:
    violations: list[Violation] = []
    selected = [activity for activity in activities if activity["schedule"].get("day") == day_number]
    # An unassigned required activity is tried once, then removed only after it
    # was actually placed.  It is never duplicated across five daily plans.
    selected.extend(activity for activity in activities if activity["id"] in unscheduled and activity["schedule"].get("required", False))
    if not selected and not tuple(anchors):
        return [], violations, set()
    try:
        zone = ZoneInfo(request.trip["local_timezone"])
        cursor = datetime.combine(current, time.fromisoformat(request.daily_start), zone)
        closes = datetime.combine(current, time.fromisoformat(request.daily_end), zone)
    except (KeyError, ValueError):
        return [], [_failure("schedule.daily_window_invalid", "daily start/end must be HH:MM", "/")], set()
    anchor_items = list(anchors)
    previous, items = hotel_id, []
    if anchor_items:
        # Anchors are immutable.  Activities are placed only after the last
        # confirmed arrival/check-in/reservation boundary for that day.
        items.extend(anchor_items)
        previous = anchor_items[-1]["place_id"]
        cursor = datetime.fromisoformat(anchor_items[-1]["end_at"])
    placed: set[str] = set()
    low_fatigue = any(preference.get("kind") in {"low_fatigue", "pace"} and preference.get("value") in {True, "low"}
                      for preference in request.trip.get("preferences", {}).get("soft_preferences", []))
    for activity in sorted(selected, key=lambda value: (
        not value["schedule"].get("required", False),
        value["schedule"].get("fatigue", 0) if low_fatigue else 0,
        value["id"],
    )):
        details = activity["schedule"]
        travel = request.validation_context.travel_minutes.get((previous, activity["id"]))
        if travel is None:
            violations.append(_failure("schedule.route_unknown", f"route from {previous} to {activity['id']} is required", activity["path"]))
            continue
        if travel < 0:
            violations.append(_failure("schedule.route_invalid", "route duration cannot be negative", activity["path"]))
            continue
        buffers = details.get("parking_buffer_minutes", 0) + details.get("walking_buffer_minutes", 0)
        if not isinstance(buffers, int) or buffers < 0:
            violations.append(_failure("schedule.buffer_invalid", "parking/walking buffers must be non-negative integers", activity["path"]))
            continue
        cursor += timedelta(minutes=travel + buffers)
        fixed = details.get("fixed_start_at")
        if fixed:
            try:
                fixed_start = datetime.fromisoformat(fixed)
            except ValueError:
                violations.append(_failure("schedule.fixed_time_invalid", "fixed_start_at must be ISO-8601", activity["path"]))
                continue
            if fixed_start.date() != current or fixed_start < cursor:
                violations.append(_failure("schedule.fixed_anchor_infeasible", "confirmed anchor cannot be reached without moving it", activity["path"]))
                continue
            cursor = fixed_start
        end_at = cursor + timedelta(minutes=details["duration_minutes"])
        fixed_end = details.get("fixed_end_at")
        if fixed_end:
            try:
                confirmed_end = datetime.fromisoformat(fixed_end)
            except ValueError:
                violations.append(_failure("schedule.fixed_time_invalid", "fixed_end_at must be ISO-8601", activity["path"]))
                continue
            if confirmed_end != end_at:
                violations.append(_failure("schedule.fixed_anchor_infeasible", "confirmed anchor end cannot be moved or re-durationed", activity["path"]))
                continue
        if end_at > closes or not _is_open(activity["id"], cursor, end_at, request):
            violations.append(_failure("schedule.closed_or_unverified", "activity lacks a verified open interval for its scheduled time", activity["path"]))
            continue
        condition_errors = _condition_errors(activity["id"], cursor, end_at, request, activity["path"])
        if condition_errors:
            violations.extend(condition_errors)
            continue
        items.append({"id": f"day{day_number}-{activity['id']}", "kind": activity["kind"], "place_id": activity["id"], "start_at": cursor.isoformat(), "end_at": end_at.isoformat(), "selection_status": "selected"})
        previous, cursor = activity["id"], end_at
        if activity["schedule"].get("day") is None:
            placed.add(activity["id"])
    if placed or any(activity["schedule"].get("day") == day_number for activity in selected):
        back = request.validation_context.travel_minutes.get((previous, hotel_id))
        if back is None:
            violations.append(_failure("schedule.route_unknown", f"route from {previous} to {hotel_id} is required for daily hotel consistency", "/days"))
        elif cursor + timedelta(minutes=back) > closes:
            violations.append(_failure("schedule.hotel_return_infeasible", "cannot return to selected hotel within daily end", "/days"))
    return items, violations, placed


def _is_open(place_id: str, start: datetime, end: datetime, request: SchedulingInput) -> bool:
    intervals = request.validation_context.opening_hours.get(place_id)
    if not intervals:
        return False
    return any(interval.weekday == start.weekday() and interval.opens_at <= start.time() and end.time() <= interval.closes_at for interval in intervals)


def _condition_errors(place_id: str, start: datetime, end: datetime, request: SchedulingInput, path: str) -> list[Violation]:
    context = request.validation_context
    if context.condition_snapshot is None or context.condition_evaluated_at is None:
        return []
    decision = evaluate_conditions(
        context.condition_snapshot, place_id, start, end,
        context.condition_evaluated_at, context.condition_policy,
    )
    # Scheduler feasibility is binary: only evaluator errors reject a
    # placement. Warnings and their soft penalties remain schedulable signals.
    return [Violation(item.code, item.severity, item.message, path) for item in decision.findings if item.severity == "error"]


def _failure(code: str, message: str, path: str) -> Violation:
    return Violation(code, "error", message, path)
