"""Candidate evaluation and bounded, violation-scoped itinerary repair."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Iterable

from src.validator import Outcome, Violation, validate_itinerary

from .contracts import CandidatePlan, HardConstraint, PlanState, PlannerInput, PlannerOutput, SoftPreference


def plan(request: PlannerInput) -> PlannerOutput:
    """Validate, repair, and rank explicit Trip V1 candidate plans.

    This module deliberately does not turn research candidates into scheduled
    visits: it lacks authoritative routing, opening-hours, and duration facts.
    Upstream scheduling can submit multiple Trip V1 candidates here, where hard
    constraints are checked before soft-preference scoring.
    """

    if request.max_repair_iterations < 0:
        raise ValueError("max_repair_iterations must be non-negative")
    plans = [_evaluate(copy.deepcopy(trip), request) for trip in request.candidate_trips]
    return PlannerOutput(tuple(sorted(plans, key=lambda item: (item.state is PlanState.FAILED, -item.score))))


def _evaluate(trip: dict, request: PlannerInput) -> CandidatePlan:
    _preserve_overrides(trip)
    iterations = 0
    violations = _validate(trip, request)
    while _has_errors(violations) and iterations < request.max_repair_iterations:
        changed = _repair_only_violating_scope(trip, violations, request)
        if not changed:
            return CandidatePlan(trip, float("-inf"), PlanState.FAILED, tuple(violations), iterations)
        iterations += 1
        _preserve_overrides(trip)
        violations = _validate(trip, request)
    if _has_errors(violations):
        return CandidatePlan(trip, float("-inf"), PlanState.FAILED, tuple(violations), iterations)
    state = PlanState.REPAIRED if iterations else PlanState.READY
    return CandidatePlan(trip, _score(trip, request.soft_preferences), state, tuple(violations), iterations)


def _validate(trip: dict, request: PlannerInput) -> list[Violation]:
    result = validate_itinerary(trip, request.validation_context)
    return [*result.violations, *_hard_constraint_violations(trip, request.hard_constraints)]


def _hard_constraint_violations(trip: dict, constraints: Iterable[HardConstraint]) -> list[Violation]:
    violations: list[Violation] = []
    items = [(day_index, item_index, item) for day_index, day in enumerate(trip.get("days", [])) for item_index, item in enumerate(day.get("items", []))]
    for constraint in constraints:
        if not constraint.strict:
            continue
        value = constraint.value
        if constraint.kind in {"fixed_time", "reservation_time"}:
            matched = [(day, index, item) for day, index, item in items if item.get("id") == value.get("item_id")]
            if len(matched) != 1 or any(item.get(key) != value.get(key) for _, _, item in matched for key in ("start_at", "end_at")):
                violations.append(_constraint_violation(constraint, "/days", "fixed or reserved time is not preserved"))
        elif constraint.kind == "required_location":
            if not any(item.get("place_id") == value for _, _, item in items):
                violations.append(_constraint_violation(constraint, "/days", "required location is absent"))
        elif constraint.kind == "forbidden_location":
            if any(item.get("place_id") == value for _, _, item in items):
                violations.append(_constraint_violation(constraint, "/days", "forbidden location is scheduled"))
        elif constraint.kind == "max_daily_duration":
            maximum = float(value)
            for day_index, day in enumerate(trip.get("days", [])):
                scheduled = day.get("items", [])
                if scheduled:
                    starts_ends = [(_timestamp(item["start_at"]), _timestamp(item["end_at"])) for item in scheduled]
                    duration = (max(end for _, end in starts_ends) - min(start for start, _ in starts_ends)).total_seconds() / 60
                    if duration > maximum:
                        violations.append(_constraint_violation(constraint, f"/days/{day_index}", f"daily duration {duration:g} exceeds {maximum:g} minutes"))
        else:
            raise ValueError(f"unsupported hard constraint kind: {constraint.kind}")
    return violations


def _repair_only_violating_scope(trip: dict, violations: Iterable[Violation], request: PlannerInput) -> bool:
    """Repair only time-related violating item paths; leave all other scope intact."""

    changed = False
    for violation in violations:
        if violation.code not in {"time.overlap", "travel_time.insufficient"}:
            continue
        location = _parse_item_path(violation.path)
        if location is None:
            continue
        day_index, item_index = location
        day = trip["days"][day_index]
        item = day["items"][item_index]
        previous = _previous_item(day["items"], item_index)
        if previous is None:
            continue
        start, end = _timestamp(item["start_at"]), _timestamp(item["end_at"])
        required_start = _timestamp(previous["end_at"])
        travel = request.validation_context.travel_minutes.get((previous["place_id"], item["place_id"]), 0)
        required_start += timedelta(minutes=travel)
        if start < required_start:
            duration = end - start
            item["start_at"] = required_start.isoformat()
            item["end_at"] = (required_start + duration).isoformat()
            changed = True
    return changed


def _preserve_overrides(trip: dict) -> None:
    for override in trip.get("overrides", []):
        if override.get("preserve_on_replan"):
            _set_json_pointer(trip, override["path"], copy.deepcopy(override["value"]))


def _set_json_pointer(document: dict, pointer: str, value: object) -> None:
    parts = pointer.lstrip("/").split("/")
    if not pointer.startswith("/") or not all(parts):
        raise ValueError(f"invalid override path: {pointer}")
    current: object = document
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"override path is not present: {pointer}")
        current = current[part]
    if not isinstance(current, dict):
        raise ValueError(f"override path cannot be set: {pointer}")
    current[parts[-1]] = value


def _score(trip: dict, preferences: Iterable[SoftPreference]) -> float:
    score = 0.0
    item_count = sum(len(day.get("items", [])) for day in trip.get("days", []))
    for preference in preferences:
        if preference.kind == "low_fatigue":
            score -= item_count * preference.weight
        elif preference.kind == "few_hotel_changes":
            score -= max(0, len(trip.get("selected", {}).get("hotel_place_ids", [])) - 1) * preference.weight
        # Other preference kinds remain neutral when the candidate data has no
        # explicit matching fact; a planner must not infer it.
    return score


def _constraint_violation(constraint: HardConstraint, path: str, message: str) -> Violation:
    return Violation(f"constraint.{constraint.kind}", "error", message, path)


def _has_errors(violations: Iterable[Violation]) -> bool:
    return any(violation.severity == "error" for violation in violations)


def _parse_item_path(path: str) -> tuple[int, int] | None:
    parts = path.strip("/").split("/")
    if len(parts) != 4 or parts[0] != "days" or parts[2] != "items":
        return None
    try:
        return int(parts[1]), int(parts[3])
    except ValueError:
        return None


def _previous_item(items: list[dict], item_index: int) -> dict | None:
    item = items[item_index]
    earlier = [candidate for index, candidate in enumerate(items) if index != item_index and _timestamp(candidate["start_at"]) <= _timestamp(item["start_at"])]
    return max(earlier, key=lambda candidate: _timestamp(candidate["start_at"]), default=None)


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)
