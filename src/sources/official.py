"""Offline normalization and reconciliation of official operational facts.

The parsers in this module consume recorded text.  Fetching pages, respecting
robots.txt, and retaining a permitted recording are deliberately outside this
boundary.  Planner and validator code therefore never sees raw HTML.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Protocol


class FactKind(str, Enum):
    REGULAR_OPENING_HOURS = "regular_opening_hours"
    SPECIAL_OPENING_HOURS = "special_opening_hours"
    CLOSED_DATE = "closed_date"
    TEMPORARY_CLOSURE = "temporary_closure"
    LAST_ADMISSION = "last_admission"
    RESERVATION_REQUIREMENT = "reservation_requirement"
    TICKET_PRICE = "ticket_price"
    AGE_POLICY = "age_policy"
    PARKING = "parking"
    ACCESSIBILITY = "accessibility"
    STROLLER_RESTRICTION = "stroller_restriction"
    EVENT_WINDOW = "event_window"
    SEASONAL_RESTRICTION = "seasonal_restriction"
    OFFICIAL_ADVISORY = "official_advisory"
    ROAD_CLOSURE = "road_closure"


class FactStatus(str, Enum):
    CONFIRMED = "confirmed"
    STALE = "stale"
    CONTRADICTORY = "contradictory"
    UNVERIFIED = "unverified"


class SourceAuthority(str, Enum):
    OFFICIAL = "official"
    PROVIDER = "provider"
    COMMUNITY = "community"


@dataclass(frozen=True)
class FactEvidence:
    source_type: SourceAuthority
    provider: str
    source_url: str
    retrieved_at: datetime
    excerpt: str | None = None


@dataclass(frozen=True)
class OperationalFact:
    """A typed assertion with its validity window and complete evidence."""

    subject_id: str
    kind: FactKind
    value: Any
    evidence: FactEvidence
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    status: FactStatus = FactStatus.UNVERIFIED

    def status_at(self, now: datetime, *, max_age: timedelta) -> FactStatus:
        """Return freshness-derived status without mutating recorded evidence."""

        now = _aware(now)
        if self.status == FactStatus.CONTRADICTORY:
            return FactStatus.CONTRADICTORY
        if self.valid_from is not None and now < _aware(self.valid_from):
            return FactStatus.UNVERIFIED
        if self.valid_until is not None and now > _aware(self.valid_until):
            return FactStatus.STALE
        if now - _aware(self.evidence.retrieved_at) > max_age:
            return FactStatus.STALE
        return (
            FactStatus.CONFIRMED
            if self.evidence.source_type
            in {
                SourceAuthority.OFFICIAL,
                SourceAuthority.PROVIDER,
            }
            else FactStatus.UNVERIFIED
        )


@dataclass(frozen=True)
class ParseResult:
    facts: tuple[OperationalFact, ...]
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconciledFact:
    """Deterministic decision plus every source record used to reach it."""

    subject_id: str
    kind: FactKind
    value: Any
    status: FactStatus
    selected: OperationalFact
    evidence: tuple[OperationalFact, ...]


class OfficialFixtureParser(Protocol):
    def parse(self, text: str) -> ParseResult: ...


class TourismSiteParser:
    """Parse the recorded tourism-site profile in ``fixtures/official-sites``."""

    def parse(self, text: str) -> ParseResult:
        payload, error = _json_object(text)
        if error:
            return ParseResult((), (error,))
        records = payload.get("records")
        if not isinstance(records, list):
            return ParseResult((), ("records must be a list",))
        facts: list[OperationalFact] = []
        errors: list[str] = []
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                errors.append(f"records[{index}] must be an object")
                continue
            facts.extend(_facts_from_map(record, payload, f"records[{index}]", errors))
        return ParseResult(tuple(facts), tuple(errors))


class OperatorAdvisoryParser:
    """Parse an operator advisory profile without performing network I/O."""

    def parse(self, text: str) -> ParseResult:
        payload, error = _json_object(text)
        if error:
            return ParseResult((), (error,))
        advisories = payload.get("advisories")
        if not isinstance(advisories, list):
            return ParseResult((), ("advisories must be a list",))
        facts: list[OperationalFact] = []
        errors: list[str] = []
        for index, advisory in enumerate(advisories):
            if not isinstance(advisory, Mapping):
                errors.append(f"advisories[{index}] must be an object")
                continue
            normalized = dict(advisory)
            normalized["subject_id"] = advisory.get("asset_id")
            normalized["facts"] = advisory.get("operational_facts")
            facts.extend(
                _facts_from_map(normalized, payload, f"advisories[{index}]", errors)
            )
        return ParseResult(tuple(facts), tuple(errors))


PARSERS: Mapping[str, OfficialFixtureParser] = {
    "tourism-site-v1": TourismSiteParser(),
    "operator-advisory-v1": OperatorAdvisoryParser(),
}


def parse_official_fixture(text: str, profile: str) -> ParseResult:
    """Parse recorded text by explicit profile; unknown profiles yield no facts."""

    parser = PARSERS.get(profile)
    if parser is None:
        return ParseResult((), (f"unknown official-site profile: {profile}",))
    return parser.parse(text)


def reconcile_facts(
    facts: Iterable[OperationalFact],
    *,
    now: datetime,
    max_age: timedelta = timedelta(days=30),
) -> tuple[ReconciledFact, ...]:
    """Resolve official > provider > community, retaining conflicting evidence.

    A disagreement among currently applicable sources is surfaced as
    ``contradictory``.  Authority still makes selection deterministic, but the
    selected assertion is deliberately not described as confirmed.
    """

    grouped: dict[tuple[str, FactKind], list[OperationalFact]] = {}
    for fact in facts:
        grouped.setdefault((fact.subject_id, fact.kind), []).append(fact)
    output: list[ReconciledFact] = []
    rank = {
        SourceAuthority.OFFICIAL: 0,
        SourceAuthority.PROVIDER: 1,
        SourceAuthority.COMMUNITY: 2,
    }
    for (subject_id, kind), records in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1].value)
    ):
        ordered = sorted(
            records,
            key=lambda fact: (
                rank[fact.evidence.source_type],
                -_aware(fact.evidence.retrieved_at).timestamp(),
                fact.evidence.source_url,
            ),
        )
        selected = ordered[0]
        selected_status = selected.status_at(now, max_age=max_age)
        applicable = [
            fact
            for fact in ordered
            if _currently_applicable(fact, now=now, max_age=max_age)
        ]
        contradictory = len({_stable_value(fact.value) for fact in applicable}) > 1
        status = FactStatus.CONTRADICTORY if contradictory else selected_status
        output.append(
            ReconciledFact(
                subject_id,
                kind,
                selected.value,
                status,
                replace(selected, status=status),
                tuple(ordered),
            )
        )
    return tuple(output)


def is_temporarily_closed(
    facts: Iterable[OperationalFact | ReconciledFact],
    at: datetime,
    *,
    subject_id: str | None = None,
) -> bool | None:
    """Pure tri-state closure evaluation: True, False, or unknown (None)."""

    records = list(facts)
    subject_id = _resolve_subject(records, subject_id)
    if subject_id is None:
        return None
    candidates = [
        _decision_view(fact)
        for fact in records
        if fact.subject_id == subject_id
        and fact.kind in {FactKind.TEMPORARY_CLOSURE, FactKind.ROAD_CLOSURE}
    ]
    applicable = [
        fact for fact in candidates if _within(at, fact.valid_from, fact.valid_until)
    ]
    usable = [fact for fact in applicable if fact.status == FactStatus.CONFIRMED]
    if not usable:
        return None
    return any(fact.value is True for fact in usable)


def last_admission_at(
    facts: Iterable[OperationalFact | ReconciledFact],
    on: date,
    *,
    subject_id: str | None = None,
) -> time | None:
    """Return a confirmed last-admission time applicable on ``on``."""

    records = list(facts)
    subject_id = _resolve_subject(records, subject_id)
    if subject_id is None:
        return None
    candidates = [
        _decision_view(fact)
        for fact in records
        if fact.subject_id == subject_id and fact.kind == FactKind.LAST_ADMISSION
    ]
    for fact in candidates:
        probe = datetime.combine(on, time(12), tzinfo=timezone.utc)
        if fact.status != FactStatus.CONFIRMED or not _within(
            probe, fact.valid_from, fact.valid_until
        ):
            continue
        if isinstance(fact.value, str):
            try:
                return time.fromisoformat(fact.value)
            except ValueError:
                return None
    return None


# Verbose aliases make call sites self-documenting.
evaluate_temporary_closure = is_temporarily_closed
evaluate_last_admission = last_admission_at


def _facts_from_map(
    record: Mapping[str, Any], root: Mapping[str, Any], path: str, errors: list[str]
) -> list[OperationalFact]:
    subject_id, values = record.get("subject_id"), record.get("facts")
    if (
        not isinstance(subject_id, str)
        or not subject_id
        or not isinstance(values, Mapping)
    ):
        errors.append(f"{path} requires subject_id and facts object")
        return []
    provider = record.get("provider", root.get("provider", root.get("site")))
    source_url = record.get("source_url")
    retrieved_at = _parse_datetime(record.get("retrieved_at", root.get("retrieved_at")))
    if (
        not isinstance(provider, str)
        or not isinstance(source_url, str)
        or retrieved_at is None
    ):
        errors.append(f"{path} requires provider, source_url, and ISO retrieved_at")
        return []
    valid_from = _parse_datetime(record.get("valid_from"), end_of_day=False)
    valid_until = _parse_datetime(record.get("valid_until"), end_of_day=True)
    if (
        record.get("valid_from") is not None
        and valid_from is None
        or record.get("valid_until") is not None
        and valid_until is None
    ):
        errors.append(f"{path} has an invalid validity timestamp")
        return []
    evidence = FactEvidence(
        SourceAuthority.OFFICIAL,
        provider,
        source_url,
        retrieved_at,
        record.get("excerpt") if isinstance(record.get("excerpt"), str) else None,
    )
    output: list[OperationalFact] = []
    for raw_kind, value in values.items():
        try:
            kind = FactKind(raw_kind)
        except ValueError:
            errors.append(f"{path}.facts has unsupported kind: {raw_kind}")
            continue
        if value is None:
            errors.append(f"{path}.facts.{raw_kind} has no value")
            continue
        output.append(
            OperationalFact(
                subject_id,
                kind,
                value,
                evidence,
                valid_from,
                valid_until,
                FactStatus.CONFIRMED,
            )
        )
    return output


def _json_object(text: str) -> tuple[Mapping[str, Any], str | None]:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        return {}, f"invalid recorded JSON: {exc}"
    return (
        (payload, None)
        if isinstance(payload, Mapping)
        else ({}, "recorded JSON must be an object")
    )


def _parse_datetime(value: object, *, end_of_day: bool = False) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        if "T" not in value:
            parsed_date = date.fromisoformat(value)
            return datetime.combine(
                parsed_date, time.max if end_of_day else time.min, tzinfo=timezone.utc
            )
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _aware(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _stable_value(value: Any) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError):
        return repr(value)


def _within(
    at: datetime, valid_from: datetime | None, valid_until: datetime | None
) -> bool:
    at = _aware(at)
    return (valid_from is None or at >= _aware(valid_from)) and (
        valid_until is None or at <= _aware(valid_until)
    )


def _currently_applicable(
    fact: OperationalFact, *, now: datetime, max_age: timedelta
) -> bool:
    """Whether evidence can describe current state for conflict detection.

    This intentionally does not use ``status_at == confirmed`` because current
    community reports remain relevant conflict evidence even though authority
    rules never promote them to confirmed.  Temporal and freshness failures,
    however, cannot contradict a fact about the present.
    """

    now = _aware(now)
    retrieved_at = _aware(fact.evidence.retrieved_at)
    return (
        retrieved_at <= now
        and now - retrieved_at <= max_age
        and _within(now, fact.valid_from, fact.valid_until)
        and fact.status != FactStatus.STALE
    )


def _decision_view(fact: OperationalFact | ReconciledFact) -> OperationalFact:
    return fact.selected if isinstance(fact, ReconciledFact) else fact


def _resolve_subject(
    facts: Iterable[OperationalFact | ReconciledFact], subject_id: str | None
) -> str | None:
    """Safely support legacy single-subject calls without cross-subject reads."""

    if subject_id is not None:
        return subject_id
    subjects = {fact.subject_id for fact in facts}
    return next(iter(subjects)) if len(subjects) == 1 else None
