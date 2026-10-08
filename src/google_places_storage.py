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
    if not isinstance(candidate_sets, dict):
        return result
    for collection in ("places", "restaurants", "hotels"):
        candidates = candidate_sets.get(collection)
        if not isinstance(candidates, list):
            continue
        candidate_sets[collection] = [_durable_candidate(item) for item in candidates]
    return result


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
