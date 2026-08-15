"""Deterministic validation rules for Canonical Trip V1 itineraries.

The validator deliberately does not enrich a trip or call external services.
Facts that are not part of Trip V1 (routing results and opening hours) are
passed in as a :class:`ValidationContext`, making every result reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Mapping, Sequence

from src.opening_hours import (
    Eligibility,
    OpeningHoursSnapshot,
    OpeningInterval,
    evaluate_opening_hours,
    legacy_snapshot,
    snapshot_from_mapping,
)


class Outcome(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class Violation:
    """A stable, machine-readable result emitted by one validation rule."""

    code: str
    severity: str
    message: str
    path: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
        }


@dataclass(frozen=True)
class BudgetLimit:
    amount: float
    currency: str


@dataclass(frozen=True)
class ValidationContext:
    """Explicit derived inputs needed by rules which Trip V1 does not contain.

    ``travel_minutes`` is keyed by ``(from_place_id, to_place_id)``. Omit a
    route when it is unknown; the travel rule will emit an unverified warning.
    ``opening_hours`` is keyed by place ID and lists local weekly intervals.
    Omit a scheduled place when its hours are unknown.
    """

    travel_minutes: Mapping[tuple[str, str], int] = field(default_factory=dict)
    opening_hours: Mapping[str, Sequence[OpeningInterval] | OpeningHoursSnapshot | Mapping[str, object]] = field(default_factory=dict)
    budget_limit: BudgetLimit | None = None


Rule = Callable[[dict, ValidationContext], Sequence[Violation]]


class RuleRegistry:
    """Ordered registry so callers can add deterministic rules without forking."""

    def __init__(self, rules: Sequence[Rule] = ()) -> None:
        self._rules = list(rules)

    def register(self, rule: Rule) -> Rule:
        self._rules.append(rule)
        return rule

    def run(self, trip: dict, context: ValidationContext) -> list[Violation]:
        return [violation for rule in self._rules for violation in rule(trip, context)]


@dataclass(frozen=True)
class ValidationResult:
    outcome: Outcome
    violations: tuple[Violation, ...]

    @property
    def is_valid(self) -> bool:
        return self.outcome is Outcome.VALID

    def as_dict(self) -> dict[str, object]:
        return {"outcome": self.outcome.value, "violations": [v.as_dict() for v in self.violations]}


def validate_itinerary(
    trip: dict, context: ValidationContext | None = None, registry: RuleRegistry | None = None
) -> ValidationResult:
    """Run deterministic itinerary rules against an already canonical Trip V1 model."""

    violations = tuple((registry or DEFAULT_RULES).run(trip, context or ValidationContext()))
    if any(item.severity == "error" for item in violations):
        outcome = Outcome.INVALID
    elif violations:
        outcome = Outcome.INCOMPLETE
    else:
        outcome = Outcome.VALID
    return ValidationResult(outcome, violations)


def time_overlap_rule(trip: dict, _: ValidationContext) -> Sequence[Violation]:
    violations: list[Violation] = []
    for day_index, day in enumerate(trip.get("days", [])):
        scheduled = sorted(enumerate(day.get("items", [])), key=lambda pair: pair[1]["start_at"])
        previous_index: int | None = None
        previous_end: datetime | None = None
        for item_index, item in scheduled:
            start, end = _timestamps(item)
            path = _item_path(day_index, item_index)
            if end <= start:
                violations.append(_error("time.invalid_interval", "item end must be after its start", path))
            if previous_end is not None and start < previous_end:
                violations.append(_error("time.overlap", "item overlaps the preceding scheduled item", path))
            if previous_end is None or end > previous_end:
                previous_index, previous_end = item_index, end
    return violations


def travel_time_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    violations: list[Violation] = []
    for day_index, day in enumerate(trip.get("days", [])):
        scheduled = sorted(enumerate(day.get("items", [])), key=lambda pair: pair[1]["start_at"])
        for (previous_index, previous), (item_index, item) in zip(scheduled, scheduled[1:]):
            if previous["place_id"] == item["place_id"]:
                continue
            path = _item_path(day_index, item_index)
            route = (previous["place_id"], item["place_id"])
            minutes = context.travel_minutes.get(route)
            if minutes is None:
                violations.append(_warning("travel_time.unverified", f"travel time for {route[0]} to {route[1]} is unknown", path))
                continue
            if minutes < 0:
                violations.append(_error("travel_time.invalid", "travel duration cannot be negative", path))
                continue
            available_minutes = (_timestamps(item)[0] - _timestamps(previous)[1]).total_seconds() / 60
            if available_minutes < minutes:
                violations.append(_error("travel_time.insufficient", f"requires {minutes} minutes but only {available_minutes:g} minutes are scheduled", path))
    return violations


def opening_hours_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    restaurant_hours = {
        candidate.get("place", {}).get("id"): candidate.get("opening_hours")
        for candidate in trip.get("candidate_sets", {}).get("restaurants", [])
        if isinstance(candidate, Mapping) and isinstance(candidate.get("place"), Mapping)
    }
    trip_timezone = str(trip.get("local_timezone", "UTC"))
    violations: list[Violation] = []
    for day_index, day in enumerate(trip.get("days", [])):
        for item_index, item in enumerate(day.get("items", [])):
            if item.get("kind") not in {"visit", "meal"}:
                continue
            path = _item_path(day_index, item_index)
            value = context.opening_hours.get(item["place_id"])
            from_candidate = False
            if value is None and item.get("kind") == "meal":
                value = restaurant_hours.get(item["place_id"])
                from_candidate = value is not None
            if value is None:
                violations.append(_warning("opening_hours.unverified", "opening hours are unknown", path))
                continue
            start, end = _timestamps(item)
            try:
                if isinstance(value, Sequence) and not isinstance(value, (str, bytes, Mapping)):
                    snapshot = legacy_snapshot(value, trip_timezone)
                else:
                    snapshot = snapshot_from_mapping(value, default_timezone=None if from_candidate else trip_timezone)
                result = evaluate_opening_hours(snapshot, start, end)
            except (KeyError, TypeError, ValueError):
                result = None
            if result is None or result.status is Eligibility.UNVERIFIED:
                violations.append(_warning("opening_hours.unverified", "opening hours are not confirmed for this interval", path))
            elif result.status is Eligibility.CLOSED:
                violations.append(_error("opening_hours.closed", "scheduled time falls outside opening hours", path))
    return violations


def budget_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    budget = trip.get("budget", {})
    path = "/budget"
    total = budget.get("total", {})
    currency = budget.get("currency")
    category_values = budget.get("categories", {}).values()
    if not total or currency is None:
        return [_warning("budget.unverified", "budget data is incomplete", path)]
    if total.get("currency") != currency or any(value.get("currency") != currency for value in category_values):
        return [_error("budget.currency_mismatch", "budget values must use the trip budget currency", path)]
    category_total = sum(value["amount"] for value in category_values)
    if category_total != total["amount"]:
        return [_error("budget.total_mismatch", "budget total does not equal category total", path)]
    if context.budget_limit is None:
        return []
    if context.budget_limit.currency != currency:
        return [_warning("budget.unverified", "budget limit currency differs from trip budget currency", path)]
    if total["amount"] > context.budget_limit.amount:
        return [_error("budget.exceeded", "budget total exceeds the supplied budget limit", path)]
    return []


DEFAULT_RULES = RuleRegistry((time_overlap_rule, travel_time_rule, opening_hours_rule, budget_rule))


def _timestamps(item: dict) -> tuple[datetime, datetime]:
    return datetime.fromisoformat(item["start_at"]), datetime.fromisoformat(item["end_at"])


def _item_path(day_index: int, item_index: int) -> str:
    return f"/days/{day_index}/items/{item_index}"


def _error(code: str, message: str, path: str) -> Violation:
    return Violation(code, "error", message, path)


def _warning(code: str, message: str, path: str) -> Violation:
    return Violation(code, "warning", message, path)
