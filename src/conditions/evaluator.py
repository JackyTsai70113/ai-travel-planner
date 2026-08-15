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
        matching = [r for r in records if r.kind is kind and r.valid_from <= starts_at and ends_at <= r.valid_until]
        if not matching:
            findings.append(ConditionFinding("condition.unverified", "warning", f"{kind.value} has no snapshot covering the scheduled interval"))
            continue
        record = max(matching, key=lambda item: item.retrieved_at)
        if record.status is ConditionStatus.STALE or evaluated_at < record.retrieved_at or evaluated_at - record.retrieved_at > policy.max_age:
            findings.append(ConditionFinding("condition.stale", "warning", f"{kind.value} snapshot is stale"))
            continue
        if record.forecast_until is not None and ends_at > record.forecast_until:
            findings.append(ConditionFinding("condition.unverified", "warning", f"{kind.value} exceeds the forecast horizon"))
            continue
        if record.status is ConditionStatus.UNKNOWN:
            findings.append(ConditionFinding("condition.unverified", "warning", f"{kind.value} status is unknown"))
            continue
        if kind in policy.containment_kinds and not any(w.starts_at <= starts_at and ends_at <= w.ends_at for w in record.eligibility_windows):
            findings.append(ConditionFinding(f"condition.{kind.value}.outside_window", "error", f"scheduled interval is outside the {kind.value} eligibility window"))
            continue
        authoritative_hard = kind in policy.hard_exclusion_kinds and record.evidence_class is EvidenceClass.AUTHORITATIVE
        if record.status is ConditionStatus.UNAVAILABLE and authoritative_hard:
            findings.append(ConditionFinding(f"condition.{kind.value}.closed", "error", f"authoritative {kind.value} makes the place unavailable"))
        elif record.status in {ConditionStatus.RISKY, ConditionStatus.UNAVAILABLE}:
            # Forecast and experience evidence are signals, never implicit closures.
            penalty += record.soft_penalty or policy.default_risk_penalty
            findings.append(ConditionFinding(f"condition.{kind.value}.risk", "warning", f"{kind.value} is a soft risk signal"))
    return ConditionDecision(tuple(findings), penalty)
