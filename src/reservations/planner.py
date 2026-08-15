"""Adapter that makes confirmed reservation anchors immutable during planning."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Sequence

from src.planner import CandidatePlan, PlanState, PlannerInput, PlannerOutput, plan

from .contracts import ReservationEvidence


def plan_with_reservations(request: PlannerInput, reservations: Sequence[ReservationEvidence]) -> PlannerOutput:
    """Plan through the existing boundary, then restore and revalidate anchors.

    Reservation overrides use valid Trip JSON pointers containing array indexes,
    which the generic planner override writer does not support. This adapter
    consumes those overrides before calling it, restores immutable values after
    ordinary repair, and calls the planner again with zero repairs so every
    returned verdict describes the restored schedule.
    """

    bindings = [(reservation, reservation.planner_bindings()) for reservation in reservations]
    bindings = [(reservation, binding) for reservation, binding in bindings if binding is not None]
    constraints = [binding[0] for _, binding in bindings]
    results: list[CandidatePlan] = []
    for source_trip in request.candidate_trips:
        prepared = copy.deepcopy(source_trip)
        emitted_overrides: list[dict] = []
        for reservation, _ in bindings:
            location = _item_location(prepared, reservation.item_id)
            if location is None:
                continue
            day_index, item_index = location
            overrides = reservation.overrides_for(day_index, item_index)
            emitted_overrides.extend(overrides)
            _apply_anchor(prepared, reservation)
        emitted_ids = {override["id"] for override in emitted_overrides}
        prepared["overrides"] = [
            override for override in prepared.get("overrides", [])
            if override.get("id") not in emitted_ids
        ]
        first = plan(replace(request, candidate_trips=[prepared], hard_constraints=(*request.hard_constraints, *constraints))).plans[0]
        restored = copy.deepcopy(first.trip)
        for reservation, _ in bindings:
            _apply_anchor(restored, reservation)
        verified = plan(replace(
            request,
            candidate_trips=[restored],
            hard_constraints=(*request.hard_constraints, *constraints),
            max_repair_iterations=0,
        )).plans[0]
        verified.trip.setdefault("overrides", []).extend(emitted_overrides)
        state = verified.state
        if state is not PlanState.FAILED and first.repair_iterations:
            state = PlanState.REPAIRED
        results.append(CandidatePlan(
            trip=verified.trip,
            score=verified.score,
            state=state,
            violations=verified.violations,
            repair_iterations=first.repair_iterations,
        ))
    return PlannerOutput(tuple(sorted(results, key=lambda item: (item.state is PlanState.FAILED, -item.score))))


def _item_location(trip: dict, item_id: str | None) -> tuple[int, int] | None:
    matches = [
        (day_index, item_index)
        for day_index, day in enumerate(trip.get("days", []))
        for item_index, item in enumerate(day.get("items", []))
        if item.get("id") == item_id
    ]
    return matches[0] if len(matches) == 1 else None


def _apply_anchor(trip: dict, reservation: ReservationEvidence) -> None:
    location = _item_location(trip, reservation.item_id)
    if location is None:
        return
    day_index, item_index = location
    item = trip["days"][day_index]["items"][item_index]
    item["start_at"] = reservation.start_at
    item["end_at"] = reservation.effective_end_at
