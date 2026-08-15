"""Pure condition evaluator used unchanged by planner and validator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import ConditionKind, ConditionPolicy, ConditionSnapshot, ConditionStatus, EvidenceClass


@dataclass(frozen=True)
class ConditionFinding:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ConditionDecision:
    findings: tuple[ConditionFinding, ...]
    soft_penalty: float


def evaluate_conditions(snapshot: ConditionSnapshot, place_id: str, starts_at: datetime, ends_at: datetime, evaluated_at: datetime, policy: ConditionPolicy) -> ConditionDecision:
    for value, label in ((starts_at, "starts_at"), (ends_at, "ends_at"), (evaluated_at, "evaluated_at")):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{label} must be timezone-aware")
    if ends_at <= starts_at:
        raise ValueError("condition interval end must be after start")
    findings: list[ConditionFinding] = []
    penalty = 0.0
    requirements = {r.kind for r in snapshot.requirements if r.place_id == place_id}
    records = [r for r in snapshot.records if place_id in r.place_ids]
    kinds = requirements | {r.kind for r in records}
    for kind in sorted(kinds, key=lambda item: item.value):
        kind_records = [r for r in records if r.kind is kind]
        overlapping = [r for r in kind_records if r.valid_from < ends_at and starts_at < r.valid_until]
        fresh = [r for r in overlapping if _fresh(r, evaluated_at, policy)]
        full_coverage = [
            r for r in fresh
            if r.valid_from <= starts_at and ends_at <= r.valid_until
            and (r.forecast_until is None or ends_at <= r.forecast_until)
        ]

        # A hard safety record applies to any half-open interval overlap. It
        # cannot be hidden by a newer or more optimistic source.
        hard_records = [
            r for r in fresh
            if kind in policy.hard_exclusion_kinds
            and r.evidence_class is EvidenceClass.AUTHORITATIVE
            and r.status is ConditionStatus.UNAVAILABLE
            and _hard_interval_overlaps(r, starts_at, ends_at)
        ]
        if hard_records:
            findings.append(ConditionFinding(f"condition.{kind.value}.closed", "error", f"authoritative {kind.value} makes the place unavailable"))

        if not overlapping:
            findings.append(ConditionFinding("condition.unverified", "warning", f"{kind.value} has no snapshot overlapping the scheduled interval"))
            continue
        if not fresh:
            findings.append(ConditionFinding("condition.stale", "warning", f"{kind.value} snapshot is stale"))
            continue
        if not full_coverage:
            findings.append(ConditionFinding("condition.unverified", "warning", f"{kind.value} has no fresh snapshot covering the scheduled interval and forecast horizon"))

        if any(r.status is ConditionStatus.UNKNOWN for r in full_coverage):
            findings.append(ConditionFinding("condition.unverified", "warning", f"{kind.value} status is unknown"))

        kind_penalties: list[float] = []
        if kind in policy.containment_kinds:
            # Eligibility containment can only be proven by an explicitly
            # available record. Unknown, risky, and unavailable statuses do
            # not establish a usable window.
            available_coverage = [r for r in full_coverage if r.status is ConditionStatus.AVAILABLE]
            authoritative = [r for r in available_coverage if r.evidence_class is EvidenceClass.AUTHORITATIVE]
            advisory = [r for r in available_coverage if r.evidence_class is not EvidenceClass.AUTHORITATIVE]
            if authoritative and not any(_contained(r, starts_at, ends_at) for r in authoritative):
                findings.append(ConditionFinding(f"condition.{kind.value}.outside_window", "error", f"scheduled interval is outside the authoritative {kind.value} eligibility window"))
            if advisory and not any(_contained(r, starts_at, ends_at) for r in advisory):
                kind_penalties.extend((r.soft_penalty or policy.default_risk_penalty) for r in advisory)
                findings.append(ConditionFinding(f"condition.{kind.value}.risk", "warning", f"non-authoritative {kind.value} window is a soft risk signal"))

        soft_records = [
            r for r in full_coverage
            if r.status in {ConditionStatus.RISKY, ConditionStatus.UNAVAILABLE}
            and not (kind in policy.hard_exclusion_kinds and r.evidence_class is EvidenceClass.AUTHORITATIVE)
        ]
        if soft_records:
            kind_penalties.extend((r.soft_penalty or policy.default_risk_penalty) for r in soft_records)
            if not any(item.code == f"condition.{kind.value}.risk" for item in findings):
                findings.append(ConditionFinding(f"condition.{kind.value}.risk", "warning", f"{kind.value} is a soft risk signal"))
        if kind_penalties:
            # Multiple providers corroborating one kind do not multiply its
            # penalty. The strongest explicit signal wins deterministically.
            penalty += max(kind_penalties)
    return ConditionDecision(tuple(findings), penalty)


def _fresh(record, evaluated_at: datetime, policy: ConditionPolicy) -> bool:
    return (
        record.status is not ConditionStatus.STALE
        and record.retrieved_at <= evaluated_at
        and evaluated_at - record.retrieved_at <= policy.max_age
    )


def _contained(record, starts_at: datetime, ends_at: datetime) -> bool:
    return any(window.starts_at <= starts_at and ends_at <= window.ends_at for window in record.eligibility_windows)


def _hard_interval_overlaps(record, starts_at: datetime, ends_at: datetime) -> bool:
    intersection_start = max(starts_at, record.valid_from)
    intersection_end = min(ends_at, record.valid_until)
    if record.forecast_until is not None:
        intersection_end = min(intersection_end, record.forecast_until)
    return intersection_start < intersection_end
