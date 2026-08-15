"""Deterministic validation rules for Canonical Trip V1 itineraries.

The validator deliberately does not enrich a trip or call external services.
Facts that are not part of Trip V1 (routing results and opening hours) are
passed in as a :class:`ValidationContext`, making every result reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Callable, Mapping, Sequence

from src.opening_hours import Eligibility, evaluate_opening_hours

from src.conditions import ConditionPolicy, ConditionSnapshot, evaluate_conditions


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
    context: Mapping[str, object] = field(default_factory=dict)
    repairable: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "context": dict(self.context),
            "repairable": self.repairable,
        }


@dataclass(frozen=True)
class OpeningInterval:
    """A local opening interval; weekday uses Python's Monday=0 convention."""

    weekday: int
    opens_at: time
    closes_at: time


@dataclass(frozen=True)
class BudgetLimit:
    amount: float
    currency: str


@dataclass(frozen=True)
class RouteConstraint:
    """Deterministic facts describing one transition in a planned day."""

    status: str | None = None
    minutes: int | None = None
    reason: str | None = None
    source_status: str | None = None
    road_closed: bool = False
    weather_open: bool | None = None
    tide_open: bool | None = None
    daylight_open: bool | None = None
    arrival_buffer_minutes: int = 0
    parking_buffer_minutes: int = 0
    walking_buffer_minutes: int = 0
    entry_buffer_minutes: int = 0


@dataclass(frozen=True)
class PlaceConstraint:
    """Deterministic operational constraints tied to a place."""

    temporarily_closed: bool = False
    last_admission_at: time | None = None
    booking_deadline: datetime | None = None
    parking_buffer_minutes: int = 0
    entry_buffer_minutes: int = 0
    walking_buffer_minutes: int = 0
    source_status: str | None = None


@dataclass(frozen=True)
class ValidationContext:
    """Explicit derived inputs needed by rules which Trip V1 does not contain.

    ``travel_minutes`` is keyed by ``(from_place_id, to_place_id)``. Omit a
    route when it is unknown; the travel rule will emit an unverified warning.
    ``opening_hours`` is keyed by place ID and lists local weekly intervals.
    Omit a scheduled place when its hours are unknown.
    """

    travel_minutes: Mapping[tuple[str, str], int] = field(default_factory=dict)
    opening_hours: Mapping[str, Sequence[OpeningInterval] | Mapping[str, object]] = field(default_factory=dict)
    budget_limit: BudgetLimit | None = None
    route_facts: Mapping[tuple[str, str], RouteConstraint] = field(default_factory=dict)
    place_constraints: Mapping[str, PlaceConstraint] = field(default_factory=dict)
    fixed_anchors: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    required_transport_pairs: Sequence[tuple[str, str]] = field(default_factory=tuple)
    required_locations: Sequence[str] = field(default_factory=tuple)
    forbidden_locations: Sequence[str] = field(default_factory=tuple)
    required_locations_by_day: Mapping[int, Sequence[str]] = field(default_factory=dict)
    forbidden_locations_by_day: Mapping[int, Sequence[str]] = field(default_factory=dict)
    daily_hotel_constraints: Mapping[int, tuple[str | None, str | None]] = field(default_factory=dict)
    require_fresh_critical_facts: bool = True
    condition_snapshot: ConditionSnapshot | None = None
    condition_evaluated_at: datetime | None = None
    condition_policy: ConditionPolicy = field(default_factory=ConditionPolicy)


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
        return {
            "outcome": self.outcome.value,
            "violations": [v.as_dict() for v in self.violations],
        }


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


def required_forbidden_locations_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    violations: list[Violation] = []

    scheduled = [
        item["place_id"]
        for day in trip.get("days", [])
        for item in day.get("items", [])
    ]
    for location in context.required_locations:
        if location not in scheduled:
            violations.append(_error("location.required", f"required location is missing: {location}", "/days", {"location": location}))
    for location in context.forbidden_locations:
        if location in scheduled:
            violations.append(_error("location.forbidden", f"forbidden location is scheduled: {location}", "/days", {"location": location}))

    for day_index, day in enumerate(trip.get("days", [])):
        place_ids = [item["place_id"] for item in day.get("items", [])]
        for location in context.required_locations_by_day.get(day_index, ()):  # type: ignore[union-attr]
            if location not in place_ids:
                violations.append(
                    _error(
                        "location.required_by_day",
                        f"required location is absent on day {day_index}: {location}",
                        f"/days/{day_index}",
                        {"day": day_index, "location": location},
                    )
                )
        for location in context.forbidden_locations_by_day.get(day_index, ()):  # type: ignore[union-attr]
            if location in place_ids:
                violations.append(
                    _error(
                        "location.forbidden_by_day",
                        f"forbidden location is scheduled on day {day_index}: {location}",
                        f"/days/{day_index}",
                        {"day": day_index, "location": location},
                    )
                )
    return violations


def reservation_anchor_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    violations: list[Violation] = []
    for day_index, day in enumerate(trip.get("days", [])):
        for item_index, item in enumerate(day.get("items", [])):
            anchor = context.fixed_anchors.get(item.get("id"))
            if anchor is None:
                continue
            path = _item_path(day_index, item_index)
            start = item["start_at"]
            end = item["end_at"]
            if start != anchor[0] or end != anchor[1]:
                violations.append(
                    _error(
                        "reservation.fixed_anchor_drift",
                        "reservation or fixed anchor time has drifted",
                        path,
                        {
                            "expected_start": anchor[0],
                            "expected_end": anchor[1],
                            "actual_start": start,
                            "actual_end": end,
                        },
                    )
                )
    return violations


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
                violations.append(
                    _error(
                        "time.invalid_interval",
                        "item end must be after its start",
                        path,
                        repairable=True,
                    )
                )
            if previous_end is not None and start < previous_end:
                violations.append(
                    _error(
                        "time.overlap",
                        "item overlaps the preceding scheduled item",
                        path,
                        repairable=True,
                    )
                )
            if previous_end is None or end > previous_end:
                previous_index, previous_end = item_index, end
    return violations


def transport_leg_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    """Enforce explicit route requirements and detect required-but-missing legs."""

    violations: list[Violation] = []
    required = {tuple(pair) for pair in context.required_transport_pairs}
    if not required:
        return violations

    known_routes = set(context.route_facts.keys()) | set(context.travel_minutes.keys())
    for day_index, day in enumerate(trip.get("days", [])):
        scheduled = sorted(enumerate(day.get("items", [])), key=lambda pair: pair[1]["start_at"])
        for (_, previous), (item_index, item) in zip(scheduled, scheduled[1:]):
            route = (previous["place_id"], item["place_id"])
            if route not in required:
                continue
            if route not in known_routes and "transport_leg_id" not in item:
                violations.append(
                    _warning(
                        "transport.leg_missing",
                        "required transport leg is missing",
                        _item_path(day_index, item_index),
                        {"route": route},
                    )
                )
            if route in required and "transport_leg_id" not in item:
                violations.append(
                    _warning(
                        "transport.leg_unreferenced",
                        "required transport context is known but item has no transport_leg_id",
                        _item_path(day_index, item_index),
                        {"route": route},
                    )
                )
    return violations


def travel_time_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    violations: list[Violation] = []
    for day_index, day in enumerate(trip.get("days", [])):
        scheduled = sorted(enumerate(day.get("items", [])), key=lambda pair: pair[1]["start_at"])
        for (previous_index, previous), (item_index, item) in zip(scheduled, scheduled[1:]):
            if previous["place_id"] == item["place_id"]:
                continue
            route = (previous["place_id"], item["place_id"])
            path = _item_path(day_index, item_index)
            fact = _resolve_route_constraint(route, context)
            if fact is None:
                violations.append(
                    _warning(
                        "travel_time.unverified",
                        f"travel time for {route[0]} to {route[1]} is unknown",
                        path,
                        {"route": route},
                    )
                )
                continue

            if _is_route_unknown(fact):
                violations.append(
                    _warning(
                        "route_unknown",
                        f"route status for {route[0]} to {route[1]} is {fact.status}",
                        path,
                        {"route": route, "status": fact.status},
                    )
                )
                continue

            if fact.status == "no_route":
                violations.append(
                    _error(
                        "route.no_route",
                        f"no route available for {route[0]} to {route[1]}",
                        path,
                        {"route": route},
                    )
                )
                continue

            if fact.minutes is None:
                violations.append(
                    _warning(
                        "travel_time.unverified",
                        f"travel time for {route[0]} to {route[1]} is unknown",
                        path,
                        {"route": route},
                    )
                )
                continue

            if fact.minutes < 0:
                violations.append(_error("travel_time.invalid", "travel duration cannot be negative", path, repairable=False))
                continue

            required_minutes = _required_route_minutes(route, fact, context)
            available_minutes = (_timestamps(item)[0] - _timestamps(previous)[1]).total_seconds() / 60
            if available_minutes < required_minutes:
                violations.append(
                    _error(
                        "travel_time.insufficient",
                        f"requires {required_minutes:g} minutes but only {available_minutes:g} minutes are scheduled",
                        path,
                        {
                            "route": route,
                            "required_minutes": required_minutes,
                            "available_minutes": available_minutes,
                        },
                        repairable=True,
                    )
                )
    return violations


def route_condition_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    """Validate weather / tide / daylight / road constraints for routed movement."""

    violations: list[Violation] = []
    for day_index, day in enumerate(trip.get("days", [])):
        scheduled = sorted(enumerate(day.get("items", [])), key=lambda pair: pair[1]["start_at"])
        for (_, previous), (item_index, item) in zip(scheduled, scheduled[1:]):
            if previous["place_id"] == item["place_id"]:
                continue
            route = (previous["place_id"], item["place_id"])
            fact = _resolve_route_constraint(route, context)
            if fact is None:
                continue
            path = _item_path(day_index, item_index)
            if fact.road_closed:
                violations.append(_error("condition.road", "route is blocked by a closed road", path, {"route": route}))
            if fact.weather_open is False:
                violations.append(_error("condition.weather", "route is blocked by weather restriction", path, {"route": route}))
            if fact.tide_open is False:
                violations.append(_error("condition.tide", "route is blocked by tide restriction", path, {"route": route}))
            if fact.daylight_open is False:
                violations.append(_error("condition.daylight", "route is blocked outside daylight window", path, {"route": route}))
            if fact.source_status is not None and context.require_fresh_critical_facts and _is_unfresh(fact.source_status):
                violations.append(
                    _warning(
                        "fact.unverified",
                        "route critical fact is not confirmed",
                        path,
                        {"route": route, "source_status": fact.source_status},
                    )
                )
    return violations


def place_condition_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    """Validate place-level operational constraints."""

    violations: list[Violation] = []
    for day_index, day in enumerate(trip.get("days", [])):
        for item_index, item in enumerate(day.get("items", [])):
            constraint = context.place_constraints.get(item["place_id"])
            if constraint is None:
                continue
            path = _item_path(day_index, item_index)
            start, end = _timestamps(item)
            if constraint.temporarily_closed:
                violations.append(_error("place.temporarily_closed", "place is temporarily closed", path, {"place_id": item["place_id"]}))
            if constraint.last_admission_at is not None:
                latest_end = datetime.combine(end.date(), constraint.last_admission_at).replace(tzinfo=end.tzinfo)
                if end > latest_end:
                    violations.append(
                        _error(
                            "place.last_admission",
                            "visit overlaps or exceeds last-admission time",
                            path,
                            {"place_id": item["place_id"], "last_admission_at": constraint.last_admission_at.isoformat(), "actual_end_at": item["end_at"]},
                        )
                    )
            if constraint.booking_deadline is not None and start > constraint.booking_deadline:
                violations.append(
                    _error(
                        "reservation.booking_deadline",
                        "planned interval starts after booking deadline",
                        path,
                        {"place_id": item["place_id"], "booking_deadline": constraint.booking_deadline.isoformat(), "actual_start_at": item["start_at"]},
                    )
                )
            if context.require_fresh_critical_facts and _is_unfresh(constraint.source_status):
                violations.append(
                    _warning(
                        "fact.unverified",
                        "critical place fact is not confirmed",
                        path,
                        {"place_id": item["place_id"], "source_status": str(constraint.source_status)},
                    )
                )
    return violations


def condition_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    violations: list[Violation] = []
    if context.condition_snapshot is None:
        return violations

    for day_index, day in enumerate(trip.get("days", [])):
        for item_index, item in enumerate(day.get("items", [])):
            place_id = item.get("place_id")
            if not isinstance(place_id, str) or item.get("start_at") is None or item.get("end_at") is None:
                continue
            if context.condition_evaluated_at is None:
                violations.append(
                    _warning("condition.unverified", "condition evaluated_at is required", _item_path(day_index, item_index))
                )
                continue
            try:
                start, end = _timestamps(item)
                decision = evaluate_conditions(
                    context.condition_snapshot, place_id, start, end, context.condition_evaluated_at, context.condition_policy
                )
            except (TypeError, ValueError):
                violations.append(
                    _warning("condition.unverified", "condition interval is invalid", _item_path(day_index, item_index))
                )
                continue
            violations.extend(
                Violation(item.code, item.severity, item.message, _item_path(day_index, item_index)) for item in decision.findings
            )
    return violations


def hotel_consistency_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    violations: list[Violation] = []
    for day_index, day in enumerate(trip.get("days", [])):
        required_start_end = context.daily_hotel_constraints.get(day_index)
        if required_start_end is None:
            continue
        required_start, required_end = required_start_end
        items = day.get("items", [])
        if required_start is not None:
            if not items:
                violations.append(_error("hotel.missing_start", "day has no items for required start hotel", f"/days/{day_index}", {"required_start": required_start}))
            elif items[0]["place_id"] != required_start:
                violations.append(
                    _error(
                        "hotel.start",
                        "day does not start at required hotel",
                        f"/days/{day_index}",
                        {"expected": required_start, "actual": items[0]["place_id"]},
                    )
                )
        if required_end is not None:
            if not items:
                violations.append(_error("hotel.missing_end", "day has no items for required end hotel", f"/days/{day_index}", {"required_end": required_end}))
            elif items[-1]["place_id"] != required_end:
                violations.append(
                    _error(
                        "hotel.end",
                        "day does not end at required hotel",
                        f"/days/{day_index}",
                        {"expected": required_end, "actual": items[-1]["place_id"]},
                    )
                )
    return violations


def opening_hours_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    violations: list[Violation] = []
    restaurant_hours = {
        candidate.get("place", {}).get("id"): candidate.get("opening_hours")
        for candidate in trip.get("candidate_sets", {}).get("restaurants", [])
        if isinstance(candidate, Mapping) and isinstance(candidate.get("place"), Mapping)
    }
    trip_timezone = str(trip.get("local_timezone", "UTC"))
    for day_index, day in enumerate(trip.get("days", [])):
        for item_index, item in enumerate(day.get("items", [])):
            if item.get("kind") not in {"visit", "meal"}:
                continue
            path = _item_path(day_index, item_index)
            intervals = context.opening_hours.get(item["place_id"])
            if not intervals and item.get("kind") == "meal":
                intervals = restaurant_hours.get(item["place_id"])
            if intervals is None:
                violations.append(
                    _warning(
                        "opening_hours.unverified",
                        "opening hours are unknown",
                        path,
                        {"place_id": item["place_id"], "reason": "missing_opening_hours"},
                    )
                )
                continue

            start, end = _timestamps(item)
            try:
                result = (
                    evaluate_opening_hours(intervals, start, end, default_timezone=trip_timezone)
                    if not isinstance(intervals, Sequence) or isinstance(intervals, (str, bytes, Mapping))
                    else Eligibility.ELIGIBLE
                )
            except (KeyError, TypeError, ValueError):
                violations.append(_error("opening_hours.closed", "opening hours schedule is invalid", path))
                continue
            if not isinstance(intervals, Sequence) or isinstance(intervals, (str, bytes, Mapping)):
                if result.status is not Eligibility.ELIGIBLE:
                    code = "opening_hours.closed" if result.status is Eligibility.CLOSED else "opening_hours.unverified"
                    violations.append(Violation(code, "error" if code == "opening_hours.closed" else "warning", result.reason, path))
            elif start.date() != end.date() or not any(
                interval.weekday == start.weekday()
                and interval.opens_at <= start.timetz().replace(tzinfo=None)
                and end.timetz().replace(tzinfo=None) <= interval.closes_at
                for interval in intervals
            ):
                violations.append(
                    _error(
                        "opening_hours.closed",
                        "scheduled time falls outside opening hours",
                        path,
                        {"place_id": item["place_id"], "start_at": item["start_at"], "end_at": item["end_at"]},
                    )
                )
    return violations


def budget_rule(trip: dict, context: ValidationContext) -> Sequence[Violation]:
    budget = trip.get("budget", {})
    path = "/budget"
    total = budget.get("total", {})
    currency = budget.get("currency")
    category_values = budget.get("categories", {}).values()
    if not total or currency is None:
        return [_warning("budget.unverified", "budget data is incomplete", path, {"reason": "budget_missing"})]
    if total.get("currency") != currency or any(value.get("currency") != currency for value in category_values):
        return [_error("budget.currency_mismatch", "budget values must use the trip budget currency", path)]
    category_total = sum(value["amount"] for value in category_values)
    if category_total != total["amount"]:
        return [_error("budget.total_mismatch", "budget total does not equal category total", path)]
    if context.budget_limit is None:
        return []
    if context.budget_limit.currency != currency:
        return [_warning("budget.unverified", "budget limit currency differs from trip budget currency", path, {"limit_currency": context.budget_limit.currency, "trip_currency": currency})]
    if total["amount"] > context.budget_limit.amount:
        return [_error("budget.exceeded", "budget total exceeds the supplied budget limit", path)]
    return []


def _timestamps(item: dict) -> tuple[datetime, datetime]:
    return datetime.fromisoformat(item["start_at"]), datetime.fromisoformat(item["end_at"])


def _item_path(day_index: int, item_index: int) -> str:
    return f"/days/{day_index}/items/{item_index}"


def _is_unfresh(status: str | None) -> bool:
    return status is not None and status != "confirmed"


def _resolve_route_constraint(route: tuple[str, str], context: ValidationContext) -> RouteConstraint | None:
    direct = context.route_facts.get(route)
    if direct is not None:
        minutes = direct.minutes
        if minutes is None:
            minutes = context.travel_minutes.get(route)
        return RouteConstraint(
            status=direct.status or "verified",
            minutes=minutes,
            reason=direct.reason,
            source_status=direct.source_status,
            road_closed=direct.road_closed,
            weather_open=direct.weather_open,
            tide_open=direct.tide_open,
            daylight_open=direct.daylight_open,
            arrival_buffer_minutes=direct.arrival_buffer_minutes,
            parking_buffer_minutes=direct.parking_buffer_minutes,
            walking_buffer_minutes=direct.walking_buffer_minutes,
            entry_buffer_minutes=direct.entry_buffer_minutes,
        )

    minutes = context.travel_minutes.get(route)
    if minutes is None:
        return None
    return RouteConstraint(minutes=minutes)


def _is_route_unknown(fact: RouteConstraint) -> bool:
    return fact.status in {"unverified", "unknown", "unsupported", "timeout", "error", "stale"}


def _required_route_minutes(route: tuple[str, str], fact: RouteConstraint, context: ValidationContext) -> float:
    route_minutes = fact.minutes if fact.minutes is not None else 0
    destination = context.place_constraints.get(route[1])
    origin = context.place_constraints.get(route[0])
    return route_minutes + fact.arrival_buffer_minutes + fact.parking_buffer_minutes + fact.walking_buffer_minutes + fact.entry_buffer_minutes + (
        destination.parking_buffer_minutes if destination else 0
    ) + (destination.entry_buffer_minutes if destination else 0) + (destination.walking_buffer_minutes if destination else 0) + (
        origin.parking_buffer_minutes if origin else 0
    ) + (origin.entry_buffer_minutes if origin else 0) + (origin.walking_buffer_minutes if origin else 0)


def _warning(
    code: str,
    message: str,
    path: str,
    context: Mapping[str, object] | None = None,
    repairable: bool = False,
) -> Violation:
    return Violation(code, "warning", message, path, context or {}, repairable)


def _error(
    code: str,
    message: str,
    path: str,
    context: Mapping[str, object] | None = None,
    repairable: bool = False,
) -> Violation:
    return Violation(code, "error", message, path, context or {}, repairable)


DEFAULT_RULES = RuleRegistry(
    (
        required_forbidden_locations_rule,
        reservation_anchor_rule,
        time_overlap_rule,
        transport_leg_rule,
        travel_time_rule,
        route_condition_rule,
        place_condition_rule,
        condition_rule,
        hotel_consistency_rule,
        opening_hours_rule,
        budget_rule,
    )
)
