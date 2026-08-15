"""Immutable dynamic-condition values shared by planning and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ConditionKind(str, Enum):
    WEATHER = "weather"
    TIDE = "tide"
    DAYLIGHT = "daylight"
    CROWD = "crowd"
    CLOSURE = "closure"
    DISASTER = "disaster"
    VOLCANIC = "volcanic"
    COMMUNITY = "community"


class ConditionStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    RISKY = "risky"
    UNKNOWN = "unknown"
    STALE = "stale"


class EvidenceClass(str, Enum):
    AUTHORITATIVE = "authoritative"
    FORECAST = "forecast"
    EXPERIENCE = "experience"


@dataclass(frozen=True)
class SourceProvenance:
    provider: str
    source_url: str
    retrieved_at: datetime
    evidence_class: EvidenceClass
    source_type: str

    def __post_init__(self) -> None:
        if not self.provider or not self.source_url or not self.source_type:
            raise ValueError("condition provenance fields must not be empty")
        _aware(self.retrieved_at, "provenance retrieved_at")


@dataclass(frozen=True)
class EligibilityWindow:
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        _aware(self.starts_at, "eligibility starts_at")
        _aware(self.ends_at, "eligibility ends_at")
        if self.ends_at <= self.starts_at:
            raise ValueError("eligibility window end must be after start")


@dataclass(frozen=True)
class ConditionRecord:
    id: str
    kind: ConditionKind
    place_ids: tuple[str, ...]
    status: ConditionStatus
    provenance: SourceProvenance
    valid_from: datetime
    valid_until: datetime
    forecast_until: datetime | None = None
    eligibility_windows: tuple[EligibilityWindow, ...] = ()
    soft_penalty: float = 0.0
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, label in ((self.valid_from, "valid_from"), (self.valid_until, "valid_until")):
            _aware(value, label)
        if self.forecast_until is not None:
            _aware(self.forecast_until, "forecast_until")
        if self.valid_until <= self.valid_from:
            raise ValueError("condition valid_until must be after valid_from")
        if self.soft_penalty < 0:
            raise ValueError("soft_penalty must be non-negative")
        if not self.place_ids:
            raise ValueError("condition must target at least one place")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    @property
    def retrieved_at(self) -> datetime:
        return self.provenance.retrieved_at

    @property
    def evidence_class(self) -> EvidenceClass:
        return self.provenance.evidence_class

    @property
    def source(self) -> str:
        """Backward-compatible provider label for pre-provenance callers."""
        return self.provenance.provider


@dataclass(frozen=True)
class ConditionRequirement:
    place_id: str
    kind: ConditionKind


@dataclass(frozen=True)
class ConditionSnapshot:
    records: tuple[ConditionRecord, ...] = ()
    requirements: tuple[ConditionRequirement, ...] = ()


@dataclass(frozen=True)
class ConditionPolicy:
    """Explicit evaluation policy; no wall-clock reads are permitted."""

    max_age: timedelta = timedelta(hours=12)
    hard_exclusion_kinds: frozenset[ConditionKind] = frozenset({ConditionKind.CLOSURE, ConditionKind.DISASTER, ConditionKind.VOLCANIC})
    containment_kinds: frozenset[ConditionKind] = frozenset({ConditionKind.TIDE, ConditionKind.DAYLIGHT})
    default_risk_penalty: float = 1.0

    def __post_init__(self) -> None:
        if self.max_age.total_seconds() < 0 or self.default_risk_penalty < 0:
            raise ValueError("condition policy durations and penalties must be non-negative")


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
