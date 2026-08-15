"""Dependency-aware composition of the existing travel planning modules.

This module owns execution state and failure propagation only.  Research,
schedule construction, route optimisation, validation, repair, and rendering
remain delegated to their existing modules or to explicit injected adapters.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Sequence

from src.intent import TravelIntent
from src.planner import PlannerInput, plan
from src.renderer.build_site import build_site
from src.schemas.validate_trip import TripValidationError, validate_trip
from src.sources import CandidateStore, SourceAdapter, SourceQuery, collect_from_adapters
from src.validator import BudgetLimit, ValidationContext


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class StageName(str, Enum):
    RESEARCH = "research"
    CANDIDATE_STORE = "candidate_store"
    ROUTING = "routing"
    PLANNER = "planner"
    OPTIMIZER = "optimizer"
    VALIDATOR_REPAIR = "validator_repair"
    CANONICAL_TRIP = "canonical_trip"
    RENDERER = "renderer"


@dataclass(frozen=True)
class WarningRecord:
    code: str
    message: str
    stage: StageName
    path: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "stage": self.stage.value, "path": self.path}


@dataclass(frozen=True)
class StageReport:
    name: StageName
    status: StageStatus = StageStatus.PENDING
    attempts: int = 0
    warnings: tuple[WarningRecord, ...] = ()
    errors: tuple[WarningRecord, ...] = ()


@dataclass(frozen=True)
class OrchestrationResult:
    intent: TravelIntent
    stages: tuple[StageReport, ...]
    warnings: tuple[WarningRecord, ...]
    trip: dict | None
    render_path: Path | None
    trip_path: Path | None = None

    @property
    def succeeded(self) -> bool:
        return self.trip is not None and self.render_path is not None and not any(
            stage.status is StageStatus.FAILED for stage in self.stages
        )

    def stage(self, name: StageName) -> StageReport:
        return next(report for report in self.stages if report.name is name)


CandidateTripFactory = Callable[[TravelIntent, CandidateStore], Sequence[dict]]
RoutingContextFactory = Callable[[TravelIntent, CandidateStore], ValidationContext]
Optimizer = Callable[[Sequence[dict], ValidationContext], Sequence[dict]]
Renderer = Callable[[dict], str]


@dataclass(frozen=True)
class TravelOrchestratorConfig:
    """Explicit integration boundaries for one planning run.

    ``candidate_trip_factory`` is the schedule-construction boundary.  It may
    select from the store but must return candidate Trip V1 documents; this
    orchestrator deliberately does not decide which places to schedule.
    """

    adapters: Sequence[SourceAdapter]
    candidate_trip_factory: CandidateTripFactory
    output_directory: Path
    trip_output_directory: Path | None = None
    research_categories: tuple[str, ...] = ("pois", "restaurants", "hotels", "flights", "transport")
    routing_context_factory: RoutingContextFactory | None = None
    optimizer: Optimizer | None = None
    renderer: Renderer = build_site
    max_stage_attempts: int = 1
    max_repair_iterations: int = 3

    def __post_init__(self) -> None:
        if self.max_stage_attempts < 1:
            raise ValueError("max_stage_attempts must be at least one")
        if self.max_repair_iterations < 0:
            raise ValueError("max_repair_iterations must be non-negative")


class TravelOrchestrator:
    """Run the declared pipeline with bounded retries and explicit states."""

    ORDER = tuple(StageName)

    def __init__(self, config: TravelOrchestratorConfig) -> None:
        self.config = config

    def run(self, intent: TravelIntent) -> OrchestrationResult:
        reports = {name: StageReport(name) for name in self.ORDER}
        aggregate_warnings: list[WarningRecord] = []

        query = SourceQuery(destination=_destination(intent), categories=self.config.research_categories)
        research, failures = collect_from_adapters(self.config.adapters, query)
        research_warnings = tuple(
            WarningRecord("research.provider_failed", f"{failure.adapter}: {failure.message}", StageName.RESEARCH)
            for failure in failures
        )
        if not research:
            error = WarningRecord("research.unavailable", "no research candidates were collected", StageName.RESEARCH)
            reports[StageName.RESEARCH] = StageReport(StageName.RESEARCH, StageStatus.FAILED, 1, research_warnings, (error,))
            return self._result(intent, reports, [*aggregate_warnings, *research_warnings, error])
        research_status = StageStatus.INCOMPLETE if failures else StageStatus.SUCCEEDED
        reports[StageName.RESEARCH] = StageReport(StageName.RESEARCH, research_status, 1, research_warnings)
        aggregate_warnings.extend(research_warnings)

        store = CandidateStore()
        ingest_warnings: list[WarningRecord] = []
        for collection, candidate in research:
            try:
                record = store.ingest(collection, candidate)
                store.normalize(record.candidate_id)
            except (KeyError, TypeError, ValueError) as exc:
                ingest_warnings.append(WarningRecord("candidate.invalid", str(exc), StageName.CANDIDATE_STORE))
        if not tuple(store.records()):
            error = WarningRecord("candidate_store.empty", "no valid research candidates are available", StageName.CANDIDATE_STORE)
            reports[StageName.CANDIDATE_STORE] = StageReport(StageName.CANDIDATE_STORE, StageStatus.FAILED, 1, tuple(ingest_warnings), (error,))
            return self._result(intent, reports, [*aggregate_warnings, *ingest_warnings, error])
        store_status = StageStatus.INCOMPLETE if ingest_warnings else StageStatus.SUCCEEDED
        reports[StageName.CANDIDATE_STORE] = StageReport(StageName.CANDIDATE_STORE, store_status, 1, tuple(ingest_warnings))
        aggregate_warnings.extend(ingest_warnings)

        routing, routing_report = self._run_routing(intent, store)
        reports[StageName.ROUTING] = routing_report
        aggregate_warnings.extend(routing_report.warnings)
        if routing_report.status is StageStatus.FAILED:
            return self._result(intent, reports, aggregate_warnings)

        candidates, planner_report = self._run_candidate_factory(intent, store)
        reports[StageName.PLANNER] = planner_report
        aggregate_warnings.extend(planner_report.warnings)
        if planner_report.status is StageStatus.FAILED:
            return self._result(intent, reports, aggregate_warnings)

        optimized, optimizer_report = self._run_optimizer(candidates, routing)
        reports[StageName.OPTIMIZER] = optimizer_report
        aggregate_warnings.extend(optimizer_report.warnings)
        if optimizer_report.status is StageStatus.FAILED:
            return self._result(intent, reports, aggregate_warnings)

        trip, repair_report = self._run_validation_repair(intent, optimized, routing)
        reports[StageName.VALIDATOR_REPAIR] = repair_report
        aggregate_warnings.extend(repair_report.warnings)
        if repair_report.status is StageStatus.FAILED:
            return self._result(intent, reports, aggregate_warnings)

        assert trip is not None
        canonical_trip, canonical_report = self._run_canonical_trip(trip, aggregate_warnings)
        reports[StageName.CANONICAL_TRIP] = canonical_report
        aggregate_warnings.extend(canonical_report.warnings)
        if canonical_report.status is StageStatus.FAILED:
            return self._result(intent, reports, aggregate_warnings)

        trip_path, persistence_report = self._persist_trip(canonical_trip)
        if persistence_report.status is StageStatus.FAILED:
            reports[StageName.CANONICAL_TRIP] = persistence_report
            return self._result(intent, reports, [*aggregate_warnings, *persistence_report.errors])
        render_path, renderer_report = self._run_renderer(canonical_trip)
        reports[StageName.RENDERER] = renderer_report
        aggregate_warnings.extend(renderer_report.warnings)
        if renderer_report.status is StageStatus.FAILED:
            return self._result(intent, reports, aggregate_warnings)
        return self._result(intent, reports, aggregate_warnings, canonical_trip, render_path, trip_path)

    def _run_routing(self, intent: TravelIntent, store: CandidateStore) -> tuple[ValidationContext, StageReport]:
        if self.config.routing_context_factory is None:
            warning = WarningRecord("routing.unverified", "no routing context provider configured", StageName.ROUTING)
            return ValidationContext(), StageReport(StageName.ROUTING, StageStatus.INCOMPLETE, 0, (warning,))
        result, report = self._retry(StageName.ROUTING, lambda: self.config.routing_context_factory(intent, store))
        return (result or ValidationContext()), report

    def _run_candidate_factory(self, intent: TravelIntent, store: CandidateStore) -> tuple[Sequence[dict], StageReport]:
        result, report = self._retry(StageName.PLANNER, lambda: self.config.candidate_trip_factory(intent, store))
        if report.status is StageStatus.FAILED:
            return (), report
        if not result:
            error = WarningRecord("planner.no_candidates", "planner boundary returned no candidate trips", StageName.PLANNER)
            return (), StageReport(StageName.PLANNER, StageStatus.FAILED, report.attempts, (), (error,))
        return result, report

    def _run_optimizer(self, candidates: Sequence[dict], routing: ValidationContext) -> tuple[Sequence[dict], StageReport]:
        if self.config.optimizer is None:
            return candidates, StageReport(StageName.OPTIMIZER, StageStatus.SUCCEEDED, 0)
        result, report = self._retry(StageName.OPTIMIZER, lambda: self.config.optimizer(candidates, routing))
        if report.status is StageStatus.FAILED or not result:
            if report.status is StageStatus.FAILED:
                return (), report
            error = WarningRecord("optimizer.no_candidates", "optimizer returned no candidate trips", StageName.OPTIMIZER)
            return (), StageReport(StageName.OPTIMIZER, StageStatus.FAILED, report.attempts, (), (error,))
        return result, report

    def _run_validation_repair(self, intent: TravelIntent, candidates: Sequence[dict], routing: ValidationContext) -> tuple[dict | None, StageReport]:
        context = _with_intent_budget(routing, intent)
        output = plan(PlannerInput(candidates, context, intent.hard_constraints, intent.soft_preferences, self.config.max_repair_iterations))
        best = output.best_plan
        if best is None:
            violations = tuple(
                WarningRecord(item.code, item.message, StageName.VALIDATOR_REPAIR, item.path)
                for candidate in output.plans for item in candidate.violations
            )
            exhausted = any(candidate.repair_iterations >= self.config.max_repair_iterations for candidate in output.plans)
            code = "repair.exhausted" if exhausted else "validator.invalid"
            error = WarningRecord(code, "no candidate passed deterministic validation", StageName.VALIDATOR_REPAIR)
            return None, StageReport(StageName.VALIDATOR_REPAIR, StageStatus.FAILED, 1, violations, (error,))
        warnings = tuple(WarningRecord(item.code, item.message, StageName.VALIDATOR_REPAIR, item.path) for item in best.violations)
        status = StageStatus.INCOMPLETE if warnings else StageStatus.SUCCEEDED
        return best.trip, StageReport(StageName.VALIDATOR_REPAIR, status, 1, warnings)

    def _run_canonical_trip(self, trip: dict, warnings: Iterable[WarningRecord]) -> tuple[dict, StageReport]:
        canonical = copy.deepcopy(trip)
        unverified = _provenance_warnings(canonical)
        canonical["validation"] = [warning.as_dict() for warning in (*tuple(warnings), *unverified)]
        try:
            validate_trip(canonical)
        except TripValidationError as exc:
            error = WarningRecord("canonical.invalid", str(exc), StageName.CANONICAL_TRIP)
            return canonical, StageReport(StageName.CANONICAL_TRIP, StageStatus.FAILED, 1, (), (error,))
        status = StageStatus.INCOMPLETE if unverified else StageStatus.SUCCEEDED
        return canonical, StageReport(StageName.CANONICAL_TRIP, status, 1, tuple(unverified))

    def _run_renderer(self, trip: dict) -> tuple[Path | None, StageReport]:
        try:
            html = self.config.renderer(trip)
            target = self.config.output_directory / str(trip.get("id", "trip")) / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")
            return target, StageReport(StageName.RENDERER, StageStatus.SUCCEEDED, 1)
        except Exception as exc:
            error = WarningRecord("renderer.failed", str(exc), StageName.RENDERER)
            return None, StageReport(StageName.RENDERER, StageStatus.FAILED, 1, (), (error,))

    def _persist_trip(self, trip: dict) -> tuple[Path | None, StageReport]:
        """Persist only the validated canonical document, never provider raw payloads."""
        if self.config.trip_output_directory is None:
            return None, StageReport(StageName.CANONICAL_TRIP, StageStatus.SUCCEEDED, 0)
        try:
            import json
            target = self.config.trip_output_directory / str(trip.get("id", "trip")) / "trip.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(trip, ensure_ascii=False, indent=2), encoding="utf-8")
            return target, StageReport(StageName.CANONICAL_TRIP, StageStatus.SUCCEEDED, 1)
        except Exception as exc:
            error = WarningRecord("canonical.persist_failed", str(exc), StageName.CANONICAL_TRIP)
            return None, StageReport(StageName.CANONICAL_TRIP, StageStatus.FAILED, 1, (), (error,))

    def _retry(self, name: StageName, operation: Callable[[], object]) -> tuple[object | None, StageReport]:
        errors: list[WarningRecord] = []
        for attempt in range(1, self.config.max_stage_attempts + 1):
            try:
                return operation(), StageReport(name, StageStatus.SUCCEEDED, attempt)
            except Exception as exc:
                errors.append(WarningRecord(f"{name.value}.failed", str(exc), name))
        return None, StageReport(name, StageStatus.FAILED, self.config.max_stage_attempts, (), tuple(errors))

    @staticmethod
    def _result(intent, reports, warnings, trip=None, render_path=None, trip_path=None) -> OrchestrationResult:
        return OrchestrationResult(intent, tuple(reports[name] for name in TravelOrchestrator.ORDER), tuple(warnings), trip, render_path, trip_path)


def _destination(intent: TravelIntent) -> str:
    if intent.destinations:
        return intent.destinations[0]
    if intent.regions:
        return intent.regions[0]
    return ""


def _with_intent_budget(context: ValidationContext, intent: TravelIntent) -> ValidationContext:
    if intent.budget_amount is None or intent.currency is None:
        return context
    return ValidationContext(context.travel_minutes, context.opening_hours, BudgetLimit(intent.budget_amount, intent.currency))


def _provenance_warnings(trip: dict) -> list[WarningRecord]:
    warnings: list[WarningRecord] = []
    for collection, candidates in trip.get("candidate_sets", {}).items():
        for index, candidate in enumerate(candidates):
            provenance = candidate.get("provenance") or candidate.get("place", {}).get("provenance", {})
            if provenance.get("status") in {"reported", "estimated", "unverified"}:
                warnings.append(WarningRecord("source.unverified", f"{collection} candidate is {provenance['status']}", StageName.CANONICAL_TRIP, f"/candidate_sets/{collection}/{index}"))
    return warnings
