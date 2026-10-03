"""Route-aware synthesis of Canonical Trip day plans from normalized facts."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

from src.conditions import evaluate_conditions
from src.validator import OpeningInterval, Violation

from .contracts import ScheduledTrip, ScheduleState, SchedulingInput, SchedulingOutput


def _route_time_description(status: str) -> str:
    return {"confirmed": "已確認", "estimated": "估計", "unverified": "未驗證"}[status]


def schedule(request: SchedulingInput) -> SchedulingOutput:
    """Build a schedule and, when safe, try verified earlier day starts for late returns."""
    initial = _schedule_once(request)
    retryable_return_codes = {"schedule.hotel_return_unverified", "schedule.hotel_return_infeasible"}
    if initial.best_trip is not None or not any(item.code in retryable_return_codes
                                                for candidate in initial.candidates for item in candidate.violations):
        return initial
    hotel_id = request.trip.get("selected", {}).get("hotel_place_ids", [None])[0]
    failed_return_days = set()
    for (_, destination, departure), fact in request.validation_context.timed_route_facts.items():
        if destination != hotel_id or fact.mode not in {"transit", "mixed"}:
            continue
        if fact.status not in {"verified", "available"}:
            failed_return_days.add(departure[:10])
            continue
        if fact.arrival_at is not None:
            query_time = datetime.fromisoformat(departure)
            daily_close = datetime.combine(date.fromisoformat(departure[:10]),
                                           time.fromisoformat(request.daily_end), query_time.tzinfo)
            if fact.arrival_at > daily_close:
                failed_return_days.add(departure[:10])
    if not failed_return_days:
        return initial
    if any(details.get("fixed_start_at") or details.get("fixed_end_at")
           for collection in ("places", "restaurants")
           for candidate in request.trip.get("candidate_sets", {}).get(collection, [])
           for details in [candidate.get("schedule", {}) if collection == "places" else candidate.get("schedule", {})]):
        return initial
    if any(item.get("kind") not in {"visit", "meal"}
           for day in request.trip.get("days", []) for item in day.get("items", [])):
        return initial
    try:
        local_start = time.fromisoformat(request.daily_start)
    except ValueError:
        return initial
    for minutes_earlier in (15, 30, 45, 60):
        shifted = (datetime.combine(date(2000, 1, 1), local_start) - timedelta(minutes=minutes_earlier)).time()
        if shifted < time(6, 0):
            continue
        adjusted_start = shifted.strftime("%H:%M")
        adjusted = _schedule_once(replace(request, daily_start=adjusted_start))
        candidate = adjusted.best_trip
        if candidate is None:
            continue
        evidence = None
        for day in candidate.trip.get("days", []):
            if day.get("date") not in failed_return_days or not day.get("items"):
                continue
            last_item = day["items"][-1]
            fact = request.validation_context.timed_route_facts.get(
                (last_item.get("place_id"), hotel_id, last_item.get("end_at")))
            query_departure = datetime.fromisoformat(last_item["end_at"])
            daily_close = datetime.combine(date.fromisoformat(day["date"]), time.fromisoformat(request.daily_end), query_departure.tzinfo)
            if (fact is not None and fact.status in {"verified", "available"}
                    and fact.mode in {"transit", "mixed"} and fact.departure_at is not None
                    and fact.arrival_at is not None and fact.departure_at >= query_departure
                    and fact.arrival_at >= fact.departure_at and fact.arrival_at <= daily_close):
                evidence = fact
                break
        if evidence is None:
            continue
        verification_status = evidence.source_status if evidence.source_status in {"confirmed", "estimated"} else "unverified"
        route_description = _route_time_description(verification_status)
        warning = Violation(
            "schedule.daily_start_adjustment", "warning",
            f"原每日開始時刻無可查證的末班回程；已將行程開始調整至 {adjusted_start}，新排程的回住宿路線為{route_description}時刻。",
            "/days", {"requested_daily_start": request.daily_start, "adjusted_daily_start": adjusted_start,
                      "return_departure_at": evidence.departure_at.isoformat() if evidence else None,
                      "return_arrival_at": evidence.arrival_at.isoformat() if evidence else None,
                      "mode": evidence.mode if evidence else None, "provider": evidence.provider if evidence else None,
                      "source_url": evidence.source_url if evidence else None,
                      "verification_status": verification_status}, repairable=True)
        candidate.trip.setdefault("validation", []).append({
            "code": warning.code, "severity": warning.severity,
            "message": warning.message, "path": warning.path,
        })
        candidate = replace(candidate, violations=(*candidate.violations, warning))
        return SchedulingOutput((candidate, *initial.candidates))
    return initial


def _schedule_once(request: SchedulingInput) -> SchedulingOutput:
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
    if _has_errors(violations) or start is None or end is None:
        return SchedulingOutput((ScheduledTrip(trip, ScheduleState.FAILED, tuple(violations)),))

    anchors_by_date = _anchors(trip, violations)
    days: list[dict] = []
    unscheduled = {activity["id"] for activity in activities if activity["schedule"].get("day") is None}
    total_days = (end - start).days + 1
    used_meal_ids: set[str] = set()
    for offset in range(total_days):
        current = start + timedelta(days=offset)
        planned, day_violations, placed = _schedule_day(
            current, offset + 1, hotel_id, activities, anchors_by_date.get(current.isoformat(), ()), unscheduled, request, used_meal_ids,
        )
        violations.extend(day_violations)
        unscheduled.difference_update(placed)
        days.append({"date": current.isoformat(), "summary": "", "items": planned})
    for activity_id in unscheduled:
        activity = next((item for item in activities if item["id"] == activity_id), None)
        if activity and activity["kind"] == "meal" and not activity["schedule"].get("required", False):
            violations.append(Violation("meal.schedule_unavailable", "warning", f"optional meal candidate {activity_id} was not schedulable and remains unselected", activity["path"]))
        else:
            violations.append(_failure("schedule.no_feasible_day", f"required activity {activity_id} has no feasible day", "/candidate_sets"))
    if _has_errors(violations):
        return SchedulingOutput((ScheduledTrip(trip, ScheduleState.FAILED, tuple(violations)),))
    trip["days"] = days
    selected_meal_items = {(day_number, item["place_id"]): item
                           for day_number, day in enumerate(days, start=1)
                           for item in day["items"] if item.get("kind") == "meal"}
    for candidate in trip.get("candidate_sets", {}).get("restaurants", []):
        details = candidate.get("schedule")
        place = candidate.get("place", candidate)
        placed_entry = next(((day_number, item) for (day_number, place_id), item in selected_meal_items.items() if place_id == place.get("id")), None)
        if placed_entry is None:
            if isinstance(details, dict):
                details["selected"] = False
            continue
        day_number, placed = placed_entry
        placed_activity = next((item for item in activities if item["id"] == place.get("id")
                                and item["schedule"].get("day") == day_number
                                and item["schedule"].get("fixed_start_at") == placed["start_at"]), None)
        if placed_activity is not None:
            candidate["schedule"] = {key: value for key, value in placed_activity["schedule"].items()
                                      if key != "alternative_for"}
            if placed_activity["kind"] == "meal":
                period = candidate["schedule"].get("meal_period")
                period_label = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}.get(period)
                if period_label and not candidate["schedule"].get("selection_reason"):
                    candidate["schedule"]["selection_reason"] = f"符合第 {day_number} 天{period_label}安排；排程已確認當日營業時間與前後路線可行。"
        candidate.setdefault("schedule", {})["day"] = day_number
        candidate["schedule"]["selected"] = True
    if hotel_id is None:
        trip.setdefault("validation", []).append({"code": "schedule.hotel_missing", "severity": "warning", "message": "住宿尚未選定；每日首段抵達與每日結束後返回住宿的路線尚未驗證。", "path": "/selected/hotel_place_ids"})
        return SchedulingOutput((ScheduledTrip(trip, ScheduleState.PARTIAL, tuple(violations)),))
    return SchedulingOutput((ScheduledTrip(trip, ScheduleState.READY, tuple(violations)),))


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
    if hotels == []:
        return None
    if len(hotels) != 1 or not isinstance(hotels[0], str):
        violations.append(_failure("schedule.hotel_missing", "exactly one selected hotel is required for daily routing", "/selected/hotel_place_ids"))
        return None
    return hotels[0]


def _activities(trip: dict, violations: list[Violation]) -> list[dict]:
    records: list[dict] = []
    pending_alternatives: dict[str, list[dict]] = {}
    restaurant_candidates = trip.get("candidate_sets", {}).get("restaurants", [])
    for collection in ("places", "restaurants"):
        for index, candidate in enumerate(trip.get("candidate_sets", {}).get(collection, [])):
            place = candidate.get("place", candidate) if collection == "restaurants" else candidate
            details = candidate.get("schedule")
            if not details or details.get("selected") is False:
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
            if collection == "restaurants" and details.get("selected", True):
                for alternative in details.get("alternatives", ()):
                    if not isinstance(alternative, dict) or not isinstance(alternative.get("place_id"), str):
                        continue
                    if alternative.get("hours_verified") is not True or alternative.get("route_verified") is not True:
                        continue
                    if alternative.get("day") != details.get("day") or alternative.get("meal_period") != details.get("meal_period"):
                        continue
                    pending_alternatives.setdefault(place["id"], []).append(alternative["place_id"])
    restaurant_by_id = {item.get("place", item).get("id"): item for item in restaurant_candidates}
    for primary_id, backup_ids in pending_alternatives.items():
        primary = next((record for record in records if record["id"] == primary_id and record["kind"] == "meal"), None)
        if primary is None:
            continue
        for backup_id in backup_ids:
            backup = restaurant_by_id.get(backup_id)
            if backup is None:
                continue
            backup_details = primary["schedule"]
            backup_schedule = backup.get("schedule") if isinstance(backup.get("schedule"), Mapping) else {}
            candidate_schedule = {key: value for key, value in backup_details.items() if key != "alternatives"}
            for key in ("duration_minutes", "fixed_start_at", "fixed_end_at", "parking_buffer_minutes", "walking_buffer_minutes", "fatigue"):
                if key in backup_schedule:
                    candidate_schedule[key] = backup_schedule[key]
            records.append({
                "id": backup_id, "kind": "meal",
                "schedule": {**candidate_schedule, "selected": False, "alternative_for": primary_id},
                "path": f"/candidate_sets/restaurants/{restaurant_candidates.index(backup)}",
            })
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


def _schedule_day(current: date, day_number: int, hotel_id: str | None, activities: Iterable[dict], anchors: Iterable[dict], unscheduled: set[str], request: SchedulingInput, used_meal_ids: set[str]) -> tuple[list[dict], list[Violation], set[str]]:
    violations: list[Violation] = []
    selected = [activity for activity in activities if activity["schedule"].get("day") == day_number
                and activity["schedule"].get("selected", True)]
    alternatives_by_primary = {
        activity["id"]: [candidate for candidate in activities
                         if candidate["schedule"].get("selected") is False
                         and candidate["schedule"].get("alternative_for") == activity["id"]]
        for activity in activities if activity["kind"] == "meal"
    }
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
    placed_activity = False
    low_fatigue = any(preference.get("kind") in {"low_fatigue", "pace"} and preference.get("value") in {True, "low"}
                      for preference in request.trip.get("preferences", {}).get("soft_preferences", []))
    def schedule_order(value: dict) -> tuple:
        fixed_start = value["schedule"].get("fixed_start_at")
        if fixed_start:
            try:
                order_time = datetime.fromisoformat(fixed_start).time()
            except ValueError:
                order_time = time(23, 59)
        else:
            order_time = {"breakfast": time(8), "lunch": time(12, 30), "dinner": time(18, 30)}.get(value["schedule"].get("meal_period"), time(11))
        return (
            order_time,
            not value["schedule"].get("required", False),
            _meal_period_order(value["schedule"].get("meal_period")),
            value["schedule"].get("fatigue", 0) if low_fatigue else 0,
            value["id"],
        )
    ordered = sorted(selected, key=schedule_order)
    for primary in ordered:
        attempts = [primary, *alternatives_by_primary.get(primary["id"], [])]
        for attempt_index, activity in enumerate(attempts):
            if activity["kind"] == "meal" and activity["id"] in used_meal_ids:
                continue
            details = activity["schedule"]
            optional_meal = activity["kind"] == "meal" and not details.get("required", False)
            cursor_before, previous_before = cursor, previous
            travel = request.validation_context.travel_minutes_for(previous, activity["id"], cursor) if previous is not None else 0
            if travel is None:
                violations.append(_optional_meal_warning(activity, "schedule.route_unknown", f"route from {previous} to {activity['id']} is not verified") if optional_meal else _failure("schedule.route_unknown", f"route from {previous} to {activity['id']} is required", activity["path"]))
                if optional_meal and attempt_index < len(attempts) - 1:
                    continue
                continue
            if travel < 0:
                violations.append(_failure("schedule.route_invalid", "route duration cannot be negative", activity["path"]))
                continue
            buffers = details.get("parking_buffer_minutes", 0) + details.get("walking_buffer_minutes", 0)
            if not isinstance(buffers, int) or buffers < 0:
                violations.append(_failure("schedule.buffer_invalid", "parking/walking buffers must be non-negative integers", activity["path"]))
                continue
            cursor += timedelta(minutes=travel + buffers)
            if previous is None:
                violations.append(Violation("schedule.origin_unknown", "warning", "每日首個活動的住宿至目的地路線尚未驗證。", activity["path"]))
            meal_period = details.get("meal_period")
            if meal_period in {"breakfast", "lunch", "dinner"}:
                target_time = {"breakfast": time(8, 0), "lunch": time(12, 30), "dinner": time(18, 30)}[meal_period]
                cursor = max(cursor, datetime.combine(current, target_time, zone))
            fixed = details.get("fixed_start_at")
            if fixed:
                try:
                    fixed_start = datetime.fromisoformat(fixed)
                except ValueError:
                    violations.append(_failure("schedule.fixed_time_invalid", "fixed_start_at must be ISO-8601", activity["path"]))
                    continue
                if fixed_start.date() != current or fixed_start < cursor:
                    violations.append(_optional_meal_warning(activity, "schedule.fixed_anchor_infeasible", "restaurant cannot be reached by its meal period") if optional_meal else _failure("schedule.fixed_anchor_infeasible", "confirmed anchor cannot be reached without moving it", activity["path"]))
                    if optional_meal:
                        cursor, previous = cursor_before, previous_before
                        if attempt_index < len(attempts) - 1:
                            continue
                    continue
                cursor = fixed_start
            end_at = cursor + timedelta(minutes=details["duration_minutes"])
            fixed_end = details.get("fixed_end_at")
            if fixed_end:
                try:
                    confirmed_end = datetime.fromisoformat(fixed_end)
                except ValueError:
                    violations.append(_optional_meal_warning(activity, "schedule.fixed_time_invalid", "fixed_end_at must be ISO-8601") if optional_meal else _failure("schedule.fixed_time_invalid", "fixed_end_at must be ISO-8601", activity["path"]))
                    if optional_meal:
                        cursor, previous = cursor_before, previous_before
                        if attempt_index < len(attempts) - 1:
                            continue
                    continue
                if confirmed_end != end_at:
                    violations.append(_optional_meal_warning(activity, "schedule.fixed_anchor_infeasible", "meal duration does not fit its confirmed end time") if optional_meal else _failure("schedule.fixed_anchor_infeasible", "confirmed anchor end cannot be moved or re-durationed", activity["path"]))
                    if optional_meal:
                        cursor, previous = cursor_before, previous_before
                        if attempt_index < len(attempts) - 1:
                            continue
                    continue
            if end_at > closes or not _is_open(activity["id"], cursor, end_at, request):
                violations.append(_optional_meal_warning(activity, "schedule.closed_or_unverified", "restaurant is not confirmed open for the scheduled meal interval") if optional_meal else _failure("schedule.closed_or_unverified", "activity lacks a verified open interval for its scheduled time", activity["path"]))
                if optional_meal:
                    cursor, previous = cursor_before, previous_before
                    if attempt_index < len(attempts) - 1:
                        continue
                continue
            condition_findings = _condition_findings(activity["id"], cursor, end_at, request, activity["path"])
            violations.extend(condition_findings)
            if _has_errors(condition_findings):
                if optional_meal:
                    violations[-len(condition_findings):] = [_optional_meal_warning(activity, item.code, item.message) for item in condition_findings]
                    cursor, previous = cursor_before, previous_before
                    if attempt_index < len(attempts) - 1:
                        continue
                continue
            if attempt_index > 0:
                violations[:] = [item for item in violations
                                 if not (item.path == primary["path"] and item.code.startswith("meal."))]
            items.append({"id": f"day{day_number}-{activity['id']}", "kind": activity["kind"], "place_id": activity["id"], "start_at": cursor.isoformat(), "end_at": end_at.isoformat(), "selection_status": "selected"})
            placed_activity = True
            previous, cursor = activity["id"], end_at
            if activity["schedule"].get("day") is None or not activity["schedule"].get("required", False):
                placed.add(activity["id"])
            if activity["kind"] == "meal":
                used_meal_ids.add(activity["id"])
            break
    if placed_activity and hotel_id is not None:
        back = request.validation_context.travel_minutes_for(previous, hotel_id, cursor)
        while back is None or cursor + timedelta(minutes=back) > closes:
            if items and items[-1].get("kind") == "meal":
                omitted = items.pop()
                used_meal_ids.discard(omitted["place_id"])
                last_item = items[-1] if items else None
                primary = next((activity for activity in activities if activity["id"] == omitted["place_id"]), None)
                if primary is not None:
                    alternative_list = alternatives_by_primary.get(primary["id"], [])
                    origin = last_item["place_id"] if last_item is not None else hotel_id
                    alternative_cursor = (datetime.fromisoformat(last_item["end_at"]) if last_item is not None
                                          else datetime.combine(current, time.fromisoformat(request.daily_start), zone))
                    for alternative in alternative_list:
                        if alternative["id"] in used_meal_ids:
                            continue
                        incoming = request.validation_context.travel_minutes_for(origin, alternative["id"], alternative_cursor)
                        if incoming is None or incoming < 0:
                            continue
                        details = alternative["schedule"]
                        start_at = alternative_cursor + timedelta(minutes=incoming + details.get("parking_buffer_minutes", 0) + details.get("walking_buffer_minutes", 0))
                        period = details.get("meal_period")
                        if period in {"breakfast", "lunch", "dinner"}:
                            meal_time = {"breakfast": time(8), "lunch": time(12, 30), "dinner": time(18, 30)}[period]
                            start_at = max(start_at, datetime.combine(current, meal_time, zone))
                        fixed_start = details.get("fixed_start_at")
                        if fixed_start:
                            fixed_start_dt = datetime.fromisoformat(fixed_start)
                            if fixed_start_dt < start_at or fixed_start_dt.date() != current:
                                continue
                            start_at = fixed_start_dt
                        end_at = start_at + timedelta(minutes=details["duration_minutes"])
                        if details.get("fixed_end_at") and datetime.fromisoformat(details["fixed_end_at"]) != end_at:
                            continue
                        return_minutes = request.validation_context.travel_minutes_for(alternative["id"], hotel_id, end_at)
                        if return_minutes is None or end_at > closes or end_at + timedelta(minutes=return_minutes) > closes:
                            continue
                        if not _is_open(alternative["id"], start_at, end_at, request):
                            continue
                        if _has_errors(_condition_findings(alternative["id"], start_at, end_at, request, alternative["path"])):
                            continue
                        items.append({"id": f"day{day_number}-{alternative['id']}", "kind": "meal", "place_id": alternative["id"], "start_at": start_at.isoformat(), "end_at": end_at.isoformat(), "selection_status": "selected"})
                        previous, cursor, back = alternative["id"], end_at, return_minutes
                        used_meal_ids.add(alternative["id"])
                        violations.append(Violation("meal.hotel_return_alternative", "warning", "restaurant alternative used because the primary meal could not be followed by a verified return to lodging", alternative["path"]))
                        break
                    else:
                        violations.append(Violation("meal.hotel_return_unverified", "warning", "restaurant meal omitted because the return route to lodging is unverified or too late", "/days"))
                else:
                    violations.append(Violation("meal.hotel_return_unverified", "warning", "restaurant meal omitted because the return route to lodging is unverified or too late", "/days"))
                if items and items[-1].get("kind") == "meal" and items[-1].get("place_id") != omitted["place_id"]:
                    continue
                if last_item is None:
                    break
                previous = last_item["place_id"]
                cursor = datetime.fromisoformat(last_item["end_at"])
                back = request.validation_context.travel_minutes_for(previous, hotel_id, cursor)
                continue
            if back is None:
                violations.append(_failure("schedule.hotel_return_unverified", f"route from {previous} to {hotel_id} is required for daily hotel consistency", "/days"))
            else:
                violations.append(_failure("schedule.hotel_return_infeasible", "cannot return to selected hotel within daily end", "/days"))
            break
    return items, violations, placed


def _is_open(place_id: str, start: datetime, end: datetime, request: SchedulingInput) -> bool:
    intervals = request.validation_context.opening_hours.get(place_id)
    if not intervals:
        return False
    return any(interval.weekday == start.weekday() and interval.opens_at <= start.time() and end.time() <= interval.closes_at for interval in intervals)


def _meal_period_order(period: object) -> int:
    return {"breakfast": 0, "lunch": 1, "dinner": 2}.get(period, 3)


def _optional_meal_warning(activity: dict, code: str, message: str) -> Violation:
    return Violation("meal." + code.split(".")[-1], "warning", message, activity["path"])


def _condition_findings(place_id: str, start: datetime, end: datetime, request: SchedulingInput, path: str) -> list[Violation]:
    context = request.validation_context
    if context.condition_snapshot is None:
        return []
    if context.condition_evaluated_at is None:
        return [Violation("condition.unverified", "warning", "condition evaluated_at is required", path)]
    decision = evaluate_conditions(
        context.condition_snapshot, place_id, start, end,
        context.condition_evaluated_at, context.condition_policy,
    )
    return [Violation(item.code, item.severity, item.message, path) for item in decision.findings]


def _has_errors(violations: Iterable[Violation]) -> bool:
    return any(item.severity == "error" for item in violations)


def _failure(code: str, message: str, path: str) -> Violation:
    return Violation(code, "error", message, path)
