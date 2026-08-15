"""Contracts for user-supplied, offline reservation evidence.

This boundary records extraction results; it does not perform OCR, fetch URLs,
or infer missing booking facts. Sensitive evidence stays here and is deliberately
excluded from planner bindings.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.planner import HardConstraint


_TRIP_ID = re.compile(r"^[a-z][a-z0-9_-]*$")


class EvidenceKind(str, Enum):
    TEXT = "text"
    PASTED_EMAIL = "pasted_email"
    IMAGE_OCR = "image_ocr_result"
    PDF_TEXT = "pdf_extracted_text"
    URL_METADATA = "url_metadata"


class ReservationType(str, Enum):
    RESTAURANT = "restaurant"
    HOTEL = "hotel"
    FLIGHT = "flight"
    ATTRACTION = "attraction"


class ReservationStatus(str, Enum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
    CANCELLED = "cancelled"
    UNVERIFIED = "unverified"


class ResolutionIssue(str, Enum):
    MISSING_PLACE = "missing_place"
    MISSING_TIME = "missing_time"
    MISSING_TIMEZONE = "missing_timezone"
    CONFLICTING_TIME = "conflicting_time"
    MISSING_CANCELLATION_TIMEZONE = "missing_cancellation_timezone"
    INVALID_TIMEZONE = "invalid_timezone"
    TIMEZONE_MISMATCH = "timezone_mismatch"


class ResolutionState(str, Enum):
    READY = "ready"
    PENDING = "pending"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class EvidenceArtifact:
    """A recorded input. ``content`` is never copied into a Trip document."""

    kind: EvidenceKind
    content: str
    source_url: str | None = None
    media_type: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceProvenance:
    artifact_sha256: str
    retrieved_at: str
    user_provided: bool = True
    source_url: str | None = None

    def __post_init__(self) -> None:
        if len(self.artifact_sha256) != 64 or any(character not in "0123456789abcdef" for character in self.artifact_sha256):
            raise ValueError("artifact_sha256 must be a lowercase SHA-256 digest")
        _aware_datetime(self.retrieved_at, "retrieved_at")
        if not self.user_provided:
            raise ValueError("reservation evidence must have explicit user provenance")


@dataclass(frozen=True)
class ReservationEvidence:
    id: str
    reservation_type: ReservationType
    status: ReservationStatus
    provider: str
    provenance: EvidenceProvenance
    evidence_kind: EvidenceKind
    timezone: str | None = None
    item_id: str | None = None
    place_id: str | None = None
    place_name: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    party_size: int | None = None
    duration_minutes: int | None = None
    arrival_buffer_minutes: int | None = None
    cancellation_deadline: str | None = None
    confirmation_number: str | None = field(default=None, repr=False)
    traveler_name: str | None = field(default=None, repr=False)
    raw_evidence: str | None = field(default=None, repr=False)
    reported_times: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _TRIP_ID.fullmatch(self.id):
            raise ValueError("id must match Trip schema pattern ^[a-z][a-z0-9_-]*$")
        if not self.provider or not self.provider.strip():
            raise ValueError("provider is required")
        if self.party_size is not None and self.party_size < 1:
            raise ValueError("party_size must be positive")
        if self.duration_minutes is not None and self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")
        if self.arrival_buffer_minutes is not None and self.arrival_buffer_minutes < 0:
            raise ValueError("arrival_buffer_minutes must be non-negative")
        for field_name, value in (("start_at", self.start_at), ("end_at", self.end_at), ("cancellation_deadline", self.cancellation_deadline)):
            if value is not None:
                try:
                    datetime.fromisoformat(value)
                except ValueError as error:
                    raise ValueError(f"{field_name} must be an ISO 8601 timestamp") from error
        for value in self.reported_times:
            try:
                datetime.fromisoformat(value)
            except ValueError as error:
                raise ValueError("reported_times must contain ISO 8601 timestamps") from error

    @property
    def resolution_issues(self) -> tuple[ResolutionIssue, ...]:
        issues: list[ResolutionIssue] = []
        if not self.place_id:
            issues.append(ResolutionIssue.MISSING_PLACE)
        parsed = []
        for value in (self.start_at, self.effective_end_at):
            if value is None:
                issues.append(ResolutionIssue.MISSING_TIME)
                break
            parsed.append(datetime.fromisoformat(value))
        if parsed and any(value.utcoffset() is None for value in parsed):
            issues.append(ResolutionIssue.MISSING_TIMEZONE)
        if self.timezone is None:
            issues.append(ResolutionIssue.MISSING_TIMEZONE)
        else:
            try:
                zone = ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError:
                issues.append(ResolutionIssue.INVALID_TIMEZONE)
            else:
                aware_values = [value for value in parsed if value.utcoffset() is not None]
                if any(not _offset_matches_zone(value, zone) for value in aware_values):
                    issues.append(ResolutionIssue.TIMEZONE_MISMATCH)
        reported = [datetime.fromisoformat(value) for value in self.reported_times]
        if any(value.utcoffset() is None for value in reported):
            issues.append(ResolutionIssue.MISSING_TIMEZONE)
        normalized_times = {value.astimezone(timezone.utc) for value in reported if value.utcoffset() is not None}
        if len(normalized_times) > 1 or (len(parsed) == 2 and parsed[1] <= parsed[0]):
            issues.append(ResolutionIssue.CONFLICTING_TIME)
        if self.cancellation_deadline is not None and datetime.fromisoformat(self.cancellation_deadline).utcoffset() is None:
            issues.append(ResolutionIssue.MISSING_CANCELLATION_TIMEZONE)
        return tuple(dict.fromkeys(issues))

    @property
    def effective_end_at(self) -> str | None:
        if self.end_at is not None:
            return self.end_at
        if self.start_at is None or self.duration_minutes is None:
            return None
        return (datetime.fromisoformat(self.start_at) + timedelta(minutes=self.duration_minutes)).isoformat()

    @property
    def resolution_state(self) -> ResolutionState:
        if ResolutionIssue.CONFLICTING_TIME in self.resolution_issues:
            return ResolutionState.CONFLICT
        return ResolutionState.READY if not self.resolution_issues else ResolutionState.PENDING

    def planner_bindings(self) -> tuple[HardConstraint, tuple[dict[str, Any], ...]] | None:
        """Return a strict anchor and schema-compatible preservation overrides.

        Cancellation, pending/unverified status, or unresolved evidence cannot
        silently become a hard constraint. The returned values intentionally do
        not contain booking codes, traveler names, raw evidence, artifact hashes,
        or URL queries.
        """

        if self.status is not ReservationStatus.CONFIRMED or self.resolution_state is not ResolutionState.READY or not self.item_id:
            return None
        assert self.start_at is not None and self.effective_end_at is not None
        value = {"item_id": self.item_id, "start_at": self.start_at, "end_at": self.effective_end_at}
        constraint = HardConstraint(f"reservation-{self.id}", "fixed_time", value, strict=True)
        provenance: dict[str, Any] = {
            "source_type": "user_input",
            "provider": self.provider,
            "retrieved_at": self.provenance.retrieved_at,
            "status": "confirmed",
            "note": f"reservation_evidence_id={self.id}; artifact_sha256={self.provenance.artifact_sha256}",
        }
        if self.provenance.source_url:
            provenance["source_url"] = _public_url(self.provenance.source_url)
        overrides = tuple(
            {
                "id": f"reservation-{self.id}-{field_name.replace('_at', '')}",
                "path": f"/days/{{day_index}}/items/{{item_index}}/{field_name}",
                "value": value[field_name],
                "preserve_on_replan": True,
                "provenance": dict(provenance),
            }
            for field_name in ("start_at", "end_at")
        )
        return constraint, overrides

    def overrides_for(self, day_index: int, item_index: int) -> tuple[dict[str, Any], ...]:
        bindings = self.planner_bindings()
        if bindings is None:
            return ()
        return tuple({**override, "path": override["path"].format(day_index=day_index, item_index=item_index)} for override in bindings[1])


def _aware_datetime(value: str, field_name: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return parsed


def _public_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    if parts.username is not None or parts.password is not None:
        raise ValueError("source_url must not contain userinfo")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _offset_matches_zone(value: datetime, zone: ZoneInfo) -> bool:
    wall_time = value.replace(tzinfo=None)
    for fold in (0, 1):
        candidate = wall_time.replace(tzinfo=zone, fold=fold)
        round_trip = candidate.astimezone(timezone.utc).astimezone(zone)
        if (
            candidate.utcoffset() == value.utcoffset()
            and round_trip.replace(tzinfo=None) == wall_time
            and round_trip.utcoffset() == candidate.utcoffset()
        ):
            return True
    return False


def reservation_from_record(record: Mapping[str, Any]) -> ReservationEvidence:
    """Load a deterministic recorded extraction result without external I/O."""

    artifact_record = record["artifact"]
    artifact = EvidenceArtifact(
        kind=EvidenceKind(artifact_record["kind"]),
        content=artifact_record["content"],
        source_url=artifact_record.get("source_url"),
        media_type=artifact_record.get("media_type"),
    )
    provenance = EvidenceProvenance(
        artifact_sha256=artifact.sha256,
        retrieved_at=record["retrieved_at"],
        source_url=artifact.source_url,
    )
    values = {key: value for key, value in record.items() if key not in {"artifact", "retrieved_at"}}
    values["reservation_type"] = ReservationType(values["reservation_type"])
    values["status"] = ReservationStatus(values["status"])
    values["reported_times"] = tuple(values.get("reported_times", ()))
    return ReservationEvidence(provenance=provenance, evidence_kind=artifact.kind, raw_evidence=artifact.content, **values)


def load_recorded_fixtures() -> tuple[ReservationEvidence, ...]:
    fixture_path = Path(__file__).with_name("recorded_fixtures.json")
    records = json.loads(fixture_path.read_text(encoding="utf-8"))
    return tuple(reservation_from_record(record) for record in records)
