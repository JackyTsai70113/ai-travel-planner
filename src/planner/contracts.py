"""Explicit, deterministic planner input and output contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from src.validator import ValidationContext, Violation


class PlanState(str, Enum):
    READY = "ready"
    REPAIRED = "repaired"
    FAILED = "failed"


class UnverifiedRestaurantHoursPolicy(str, Enum):
    """How planning treats a scheduled meal whose hours are not confirmed."""

    PENALIZE = "penalize"
    BLOCK = "block"


class ScheduleState(str, Enum):
    """Result of constructing a candidate itinerary from normalized facts."""

    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class HardConstraint:
    """A non-negotiable planning condition, evaluated before soft scoring.

    Supported kinds are ``fixed_time``, ``reservation_time``,
    ``required_location``, ``forbidden_location`` and
    ``max_daily_duration``.  Opening-hours, transport feasibility, and a
    strict budget ceiling are supplied through :class:`ValidationContext` so
    the planner never invents those facts.
    """

    id: str
    kind: str
    value: Any
    strict: bool = True


@dataclass(frozen=True)
class SoftPreference:
    """A ranking signal only; it can never make an invalid plan acceptable."""

    id: str
    kind: str
    value: Any = True
    weight: float = 1.0


@dataclass(frozen=True)
class PlannerInput:
    """Candidate Trip V1 documents plus only explicit derived validation facts."""

    candidate_trips: Sequence[dict]
    validation_context: ValidationContext = field(default_factory=ValidationContext)
    hard_constraints: Sequence[HardConstraint] = ()
    soft_preferences: Sequence[SoftPreference] = ()
    max_repair_iterations: int = 3
    unverified_restaurant_hours_policy: UnverifiedRestaurantHoursPolicy = UnverifiedRestaurantHoursPolicy.PENALIZE


@dataclass(frozen=True)
class CandidatePlan:
    trip: dict
    score: float
    state: PlanState
    violations: tuple[Violation, ...]
    repair_iterations: int


@dataclass(frozen=True)
class PlannerOutput:
    plans: tuple[CandidatePlan, ...]

    @property
    def successful_plans(self) -> tuple[CandidatePlan, ...]:
        return tuple(plan for plan in self.plans if plan.state is not PlanState.FAILED)

    @property
    def best_plan(self) -> CandidatePlan | None:
        successful = self.successful_plans
        return successful[0] if successful else None


@dataclass(frozen=True)
class SchedulingInput:
    """Facts consumed by the deterministic multi-day scheduler.

    ``trip`` is a Canonical Trip shell containing normalized candidates.  A
    schedulable POI or restaurant must provide a ``schedule`` mapping with at
    least ``duration_minutes`` and may provide ``day`` (one-based),
    ``required``, ``fixed_start_at``, parking/walking buffers, and fatigue.
    The scheduler deliberately rejects missing operational facts rather than
    deriving them from a provider payload or a template.
    """

    trip: dict
    validation_context: ValidationContext
    daily_start: str = "09:00"
    daily_end: str = "20:00"


@dataclass(frozen=True)
class ScheduledTrip:
    trip: dict
    state: ScheduleState
    violations: tuple[Violation, ...]


@dataclass(frozen=True)
class SchedulingOutput:
    candidates: tuple[ScheduledTrip, ...]

    @property
    def best_trip(self) -> ScheduledTrip | None:
        return next((candidate for candidate in self.candidates if candidate.state is ScheduleState.READY), None)
