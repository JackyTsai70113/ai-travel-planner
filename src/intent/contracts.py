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

    def planner_constraints(self) -> tuple[tuple[HardConstraint, ...], tuple[SoftPreference, ...]]:
        """Return constraints in the existing planner's native contract."""

        return self.hard_constraints, self.soft_preferences

    def as_dict(self) -> dict[str, Any]:
        """A serialization-friendly representation for an orchestrator boundary."""

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
        }


TravelIntent = TripRequest
