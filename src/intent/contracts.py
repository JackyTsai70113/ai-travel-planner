"""Typed contract for facts extracted from a free-form trip request.

The contract deliberately represents only what the requester stated.  It is
an input to research and planning, never an itinerary or research result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.planner.contracts import HardConstraint, SoftPreference


@dataclass(frozen=True)
class FieldProvenance:
    """Trace one normalized value back to an exact substring of user input."""

    text: str
    start: int
    end: int
    field: str


@dataclass(frozen=True)
class MissingField:
    field: str
    reason: str


@dataclass(frozen=True)
class AmbiguousField:
    field: str
    text: str
    reason: str


@dataclass(frozen=True)
class ConstraintScope:
    """The explicitly stated calendar scope of a request constraint."""

    day_number: int | None = None
    date: str | None = None
    day_selector: str | None = None


@dataclass(frozen=True)
class TimeWindow:
    """A named or explicit local-time window; no timezone is inferred."""

    start: str | None = None
    end: str | None = None
    period: str | None = None


@dataclass(frozen=True)
class ConstraintCondition:
    """A condition stated by the requester, without evaluating it."""

    kind: str
    value: str | bool = True


@dataclass(frozen=True)
class RequestConstraint:
    """Planner-neutral extension contract for a single stated constraint."""

    id: str
    kind: str
    strength: str
    subject: str | None = None
    scope: ConstraintScope | None = None
    time_window: TimeWindow | None = None
    relation: str | None = None
    object: str | None = None
    condition: ConstraintCondition | None = None
    provenance: tuple[FieldProvenance, ...] = ()


@dataclass(frozen=True)
class ConstraintIssue:
    """Machine-readable problem that must be resolved before planning."""

    code: str
    constraint_ids: tuple[str, ...] = ()
    field: str = "request_constraints"
    text: str = ""
    reason: str = ""


@dataclass(frozen=True)
class TravelerGroup:
    adults: int | None = None
    children: int | None = None
    child_ages: tuple[int, ...] = ()


@dataclass(frozen=True)
class TripRequest:
    """Normalized user intent, without unstated defaults or researched facts."""

    raw_text: str
    destinations: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    start_date: str | None = None
    end_date: str | None = None
    duration_days: int | None = None
    duration_nights: int | None = None
    origin: str | None = None
    travelers: TravelerGroup = field(default_factory=TravelerGroup)
    budget_amount: int | None = None
    currency: str | None = None
    transport: tuple[str, ...] = ()
    required_places: tuple[str, ...] = ()
    forbidden_places: tuple[str, ...] = ()
    accommodation_preferences: tuple[str, ...] = ()
    food_preferences: tuple[str, ...] = ()
    pace: str | None = None
    hard_constraints: tuple[HardConstraint, ...] = ()
    soft_preferences: tuple[SoftPreference, ...] = ()
    missing_fields: tuple[MissingField, ...] = ()
    ambiguous_fields: tuple[AmbiguousField, ...] = ()
    provenance: dict[str, tuple[FieldProvenance, ...]] = field(default_factory=dict)
    request_constraints: tuple[RequestConstraint, ...] = ()
    constraint_issues: tuple[ConstraintIssue, ...] = ()

    def planner_constraints(self) -> tuple[tuple[HardConstraint, ...], tuple[SoftPreference, ...]]:
        """Return constraints in the existing planner's native contract."""

        return self.hard_constraints, self.soft_preferences

    def as_dict(self) -> dict[str, Any]:
        """A serialization-friendly representation for an orchestrator boundary."""

        def provenance_dict(item: FieldProvenance) -> dict[str, Any]:
            return {"text": item.text, "start": item.start, "end": item.end, "field": item.field}

        def constraint_dict(item: RequestConstraint) -> dict[str, Any]:
            return {
                "id": item.id,
                "kind": item.kind,
                "strength": item.strength,
                "subject": item.subject,
                "scope": None if item.scope is None else {
                    "day_number": item.scope.day_number, "date": item.scope.date,
                    "day_selector": item.scope.day_selector,
                },
                "time_window": None if item.time_window is None else {
                    "start": item.time_window.start, "end": item.time_window.end,
                    "period": item.time_window.period,
                },
                "relation": item.relation,
                "object": item.object,
                "condition": None if item.condition is None else {
                    "kind": item.condition.kind, "value": item.condition.value,
                },
                "provenance": [provenance_dict(value) for value in item.provenance],
            }

        return {
            "raw_text": self.raw_text,
            "destinations": list(self.destinations),
            "regions": list(self.regions),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "duration_days": self.duration_days,
            "duration_nights": self.duration_nights,
            "origin": self.origin,
            "travelers": {"adults": self.travelers.adults, "children": self.travelers.children, "child_ages": list(self.travelers.child_ages)},
            "budget_amount": self.budget_amount,
            "currency": self.currency,
            "transport": list(self.transport),
            "required_places": list(self.required_places),
            "forbidden_places": list(self.forbidden_places),
            "accommodation_preferences": list(self.accommodation_preferences),
            "food_preferences": list(self.food_preferences),
            "pace": self.pace,
            "hard_constraints": [
                {"id": item.id, "kind": item.kind, "value": item.value, "strict": item.strict}
                for item in self.hard_constraints
            ],
            "soft_preferences": [
                {"id": item.id, "kind": item.kind, "value": item.value, "weight": item.weight}
                for item in self.soft_preferences
            ],
            "missing_fields": [{"field": item.field, "reason": item.reason} for item in self.missing_fields],
            "ambiguous_fields": [
                {"field": item.field, "text": item.text, "reason": item.reason}
                for item in self.ambiguous_fields
            ],
            "provenance": {
                key: [provenance_dict(item) for item in values]
                for key, values in self.provenance.items()
            },
            "request_constraints": [constraint_dict(item) for item in self.request_constraints],
            "constraint_issues": [
                {"code": item.code, "constraint_ids": list(item.constraint_ids),
                 "field": item.field, "text": item.text, "reason": item.reason}
                for item in self.constraint_issues
            ],
        }


TravelIntent = TripRequest
