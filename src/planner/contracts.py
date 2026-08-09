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
