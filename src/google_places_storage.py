"""Project transient Google Places research into durable Canonical Trip data.

Place IDs are retained indefinitely. Google Places details are request-scoped:
they are not copied into trip JSON, generated HTML, or a public bundle.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

GOOGLE_PLACES_PROVIDER = "Google Places API (New)"


def durable_trip(trip: Mapping[str, Any]) -> dict[str, Any]:
    """Return a storage-safe copy, preserving user-owned trip decisions/notes."""
    result = deepcopy(dict(trip))
    candidate_sets = result.get("candidate_sets")
    google_candidate_ids: set[str] = set()
    if isinstance(candidate_sets, dict):
        for collection in ("places", "restaurants", "hotels"):
            candidates = candidate_sets.get(collection)
            if not isinstance(candidates, list):
                continue
            for candidate in candidates:
                if _has_google_provenance(candidate):
                    google_candidate_ids.update(_candidate_ids(candidate))
            candidate_sets[collection] = [_durable_candidate(item) for item in candidates]
    _sanitize_google_validation(result, google_candidate_ids)
    return result


def _candidate_ids(candidate: Any) -> set[str]:
    """Collect stable IDs used by validation paths for a Google candidate."""
    if not isinstance(candidate, Mapping):
        return set()
    values = [candidate.get(key) for key in ("id", "google_place_id")]
    place = candidate.get("place")
    if isinstance(place, Mapping):
        values.extend(place.get(key) for key in ("id", "google_place_id"))
    return {value for value in values if isinstance(value, str) and value}


def _sanitize_google_validation(trip: dict[str, Any], google_candidate_ids: set[str]) -> None:
    """Remove provider details embedded in validation messages for Google candidates."""
    findings = trip.get("validation")
    if not isinstance(findings, list) or not google_candidate_ids:
        return
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        path = finding.get("path")
        if not isinstance(path, str) or not any(
            segment in google_candidate_ids for segment in path.split("/")
        ):
            continue
        if finding.get("code") == "schedule.poi_candidate_unselected":
            finding["message"] = (
                "Google Places 候選未排入：所需營業時間或路線尚未驗證。"
            )
        else:
            finding["message"] = "Google Places 候選詳細資料已省略。"
        # Validation context can contain the same provider name/address as its message.
        finding.pop("context", None)


def _durable_candidate(candidate: Any) -> Any:
    if not isinstance(candidate, dict):
        return candidate
    place = candidate.get("place")
    if isinstance(place, dict) and _has_google_provenance(place):
        candidate["place"] = _durable_place(place)
    elif "place" not in candidate and _has_google_provenance(candidate):
        candidate = _durable_place(candidate)
    if _has_google_provenance(candidate):
        # Retain only provider identity/metadata and independently sourced
        # fields with explicit field-level provenance. Google-derived values
        # are fetched again when requested.
        safe: dict[str, Any] = {}
        if isinstance(candidate.get("place"), dict):
            # Provenance is sometimes recorded on the candidate wrapper
            # instead of the nested place. Treat all nested detail fields as
            # Google-derived unless field-level provenance proves otherwise.
            safe["place"] = _durable_place(candidate["place"])
        for field in ("id", "google_place_id", "kind"):
            if field in candidate:
                safe[field] = candidate[field]
        for field in ("provenance", "source_provenance"):
            if field in candidate:
                safe[field] = _strip_google_urls(candidate[field])
        field_provenance = candidate.get("field_provenance")
        if isinstance(field_provenance, dict):
            independent = {
                key: _non_google_sources(value)
                for key, value in field_provenance.items()
                if _non_google_sources(value)
            }
            if independent:
                safe["field_provenance"] = independent
                for field in independent:
                    if field in candidate:
                        safe[field] = candidate[field]
        return safe
    return _strip_google_urls(candidate)


def _durable_place(place: dict[str, Any]) -> dict[str, Any]:
    safe = {key: place[key] for key in ("id", "google_place_id", "kind") if key in place}
    provenance = place.get("provenance")
    if isinstance(provenance, dict):
        safe["provenance"] = _strip_google_urls(provenance)
    field_provenance = place.get("field_provenance")
    if isinstance(field_provenance, dict):
        independent = {
            key: _non_google_sources(value)
            for key, value in field_provenance.items()
            if _non_google_sources(value)
        }
        if independent:
            safe["field_provenance"] = independent
            for field in independent:
                if field in place:
                    safe[field] = place[field]
    return safe


def _has_google_provenance(value: Any) -> bool:
    if isinstance(value, Mapping):
        if value.get("provider") == GOOGLE_PLACES_PROVIDER:
            return True
        return any(_has_google_provenance(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_google_provenance(child) for child in value)
    return False


def _non_google_sources(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, list) else [value]
    return [
        _strip_google_urls(item)
        for item in values
        if isinstance(item, dict) and item.get("provider") != GOOGLE_PLACES_PROVIDER
    ]


def _strip_google_urls(value: Any) -> Any:
    if isinstance(value, dict):
        result = {key: _strip_google_urls(child) for key, child in value.items()}
        if value.get("provider") == GOOGLE_PLACES_PROVIDER:
            result.pop("source_url", None)
            result.pop("note", None)
        return result
    if isinstance(value, list):
        return [_strip_google_urls(item) for item in value]
    return value
