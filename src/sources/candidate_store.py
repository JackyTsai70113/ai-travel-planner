"""Lifecycle-aware store for research candidates before planner selection.

The store intentionally has no method that accepts or returns an itinerary day.
It stores canonical Trip V1 candidate payloads and lifecycle state separately, so
the state does not leak into the immutable Trip schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable


class CandidateState(str, Enum):
    FETCHED = "fetched"
    NORMALIZED = "normalized"
    SELECTED = "selected"
    REJECTED = "rejected"


class StaleCandidateError(ValueError):
    """Raised when a dynamic fact is too old for its caller-defined freshness limit."""


@dataclass(frozen=True)
class CandidateRecord:
    collection: str
    candidate: dict[str, Any]
    state: CandidateState
    stored_at: datetime

    @property
    def candidate_id(self) -> str:
        if self.collection in {"restaurants", "hotels"}:
            return self.candidate["place"]["id"]
        return self.candidate["id"]


class CandidateStore:
    """In-memory candidate lifecycle store for one research job.

    Candidate payloads remain compatible with Trip V1's ``candidate_sets``.  The
    store's lifecycle state is operational metadata only and is never serialized
    into that schema.
    """

    VALID_COLLECTIONS = frozenset({"places", "restaurants", "hotels", "flights", "transport_legs"})

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime.now(timezone.utc)
        self._records: dict[str, CandidateRecord] = {}

    def ingest(self, collection: str, candidate: dict[str, Any]) -> CandidateRecord:
        """Store a fetched canonical candidate after enforcing provenance invariants."""

        if collection not in self.VALID_COLLECTIONS:
            raise ValueError(f"unsupported candidate collection: {collection}")
        provenance = candidate.get("provenance")
        if not isinstance(provenance, dict) and collection in {"restaurants", "hotels"}:
            provenance = candidate.get("place", {}).get("provenance")
        retrieved_at = _parse_retrieved_at(provenance)
        if not isinstance(provenance.get("provider"), str) or not provenance["provider"]:
            raise ValueError("candidate provenance requires a provider")
        record = CandidateRecord(collection, candidate, CandidateState.FETCHED, self._now)
        self._records[record.candidate_id] = record
        return record

    def normalize(self, candidate_id: str) -> CandidateRecord:
        return self._transition(candidate_id, {CandidateState.FETCHED}, CandidateState.NORMALIZED)

    def select(self, candidate_id: str) -> CandidateRecord:
        return self._transition(candidate_id, {CandidateState.NORMALIZED}, CandidateState.SELECTED)

    def reject(self, candidate_id: str) -> CandidateRecord:
        return self._transition(candidate_id, {CandidateState.FETCHED, CandidateState.NORMALIZED}, CandidateState.REJECTED)

    def fresh(self, max_age: timedelta, now: datetime | None = None) -> list[CandidateRecord]:
        """Return non-rejected records whose canonical provenance is still fresh."""

        reference = now or datetime.now(timezone.utc)
        records = []
        for record in self._records.values():
            if record.state is CandidateState.REJECTED:
                continue
            retrieved_at = _parse_retrieved_at(_provenance_for(record))
            if reference - retrieved_at <= max_age:
                records.append(record)
        return records

    def require_fresh(self, candidate_id: str, max_age: timedelta, now: datetime | None = None) -> CandidateRecord:
        record = self._records[candidate_id]
        reference = now or datetime.now(timezone.utc)
        if reference - _parse_retrieved_at(_provenance_for(record)) > max_age:
            raise StaleCandidateError(f"candidate {candidate_id} exceeds freshness limit")
        return record

    def records(self) -> Iterable[CandidateRecord]:
        return tuple(self._records.values())

    def _transition(self, candidate_id: str, allowed: set[CandidateState], target: CandidateState) -> CandidateRecord:
        record = self._records[candidate_id]
        if record.state not in allowed:
            raise ValueError(f"cannot transition {candidate_id} from {record.state} to {target}")
        updated = CandidateRecord(record.collection, record.candidate, target, record.stored_at)
        self._records[candidate_id] = updated
        return updated


def _provenance_for(record: CandidateRecord) -> dict[str, Any]:
    return record.candidate.get("provenance") or record.candidate["place"]["provenance"]


def _parse_retrieved_at(provenance: Any) -> datetime:
    if not isinstance(provenance, dict) or not provenance.get("retrieved_at"):
        raise ValueError("candidate provenance requires retrieved_at")
    try:
        parsed = datetime.fromisoformat(provenance["retrieved_at"])
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate provenance retrieved_at must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("candidate provenance retrieved_at must include a timezone offset")
    return parsed
