"""Trip Operations / Handbook read model.

``evidence`` is normalized evidence supplied by upstream research.  It is not
an itinerary input: records without a Canonical Trip place reference are
excluded, and every displayed operational fact retains its provenance.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus, urlsplit, urlunsplit


_CONFIRMATION_KEYS = {"confirmation_number", "confirmationnumber", "confirmationcode", "booking_reference", "bookingreference", "reservation_code", "reservationcode"}


def build_handbook(trip: dict[str, Any], evidence: dict[str, Any] | None = None, *, now: datetime | None = None, freshness_days: int = 7) -> dict[str, Any]:
    """Return a read-only handbook derived from ``trip`` and verified evidence.

    Evidence records need ``place_id`` (where applicable) and ``provenance``.
    Missing or malformed provenance is surfaced as ``unknown`` rather than
    being presented as fresh information.  This keeps unknown opening and
    operational facts explicitly unknown.
    """
    evidence = evidence or {}
    reference = now or datetime.now(timezone.utc)
    places = {place["id"]: place for place in trip.get("candidate_sets", {}).get("places", []) if "id" in place}
    used_place_ids = {item.get("place_id") for day in trip.get("days", []) for item in day.get("items", [])}

    daily = [_daily_route(day, places) for day in trip.get("days", [])]
    facts = _place_facts(evidence.get("place_operations", []), places, used_place_ids, reference, freshness_days)
    reservations = [_reservation(record, places, used_place_ids, trip, reference, freshness_days) for record in evidence.get("reservations", [])]
    reservations = [record for record in reservations if record is not None]
    conditions = _evidence_records(evidence.get("conditions", []), used_place_ids, reference, freshness_days)
    supplies = _evidence_records(evidence.get("supplies", []), used_place_ids, reference, freshness_days)
    sources = _sources(facts, reservations, conditions, supplies)

    return {
        "read_model": "trip-operations-handbook-v1",
        "canonical_trip": {"id": trip.get("id"), "title": trip.get("title"), "date_range": deepcopy(trip.get("date_range", {}))},
        "daily_operations": daily,
        "place_operations": facts,
        "reservations": reservations,
        "conditions": conditions,
        "supplies": supplies,
        "traveler_notes": _traveler_notes(trip),
        "departure_recheck": _departure_recheck(trip, reservations),
        "emergency": {"number": "110", "medical_fire": "119", "phrases": ["助けてください", "病院はどこですか", "子どもが具合悪いです"]},
        "sources": sources,
    }


def _daily_route(day: dict[str, Any], places: dict[str, dict[str, Any]]) -> dict[str, Any]:
    stops = [item.get("place_id") for item in day.get("items", []) if item.get("place_id") in places]
    names = [places[place_id].get("name", place_id) for place_id in stops]
    query = " -> ".join(names)
    return {"date": day.get("date"), "summary": day.get("summary"), "canonical_item_ids": [item.get("id") for item in day.get("items", [])], "stop_place_ids": stops, "google_maps_url": f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(names[-1])}&waypoints={quote_plus('|'.join(names[:-1]))}" if names else None}


def _place_facts(records: list[dict[str, Any]], places: dict[str, dict[str, Any]], used: set[str], reference: datetime, freshness_days: int) -> list[dict[str, Any]]:
    result = []
    for record in records:
        place_id = record.get("place_id")
        if place_id not in places or place_id not in used:
            continue
        item = {key: deepcopy(value) for key, value in record.items() if key not in {"place_id", "place_name"}}
        item["provenance"] = _public_provenance(item.get("provenance"))
        item.update({"place_id": place_id, "place_name": places[place_id].get("name", place_id)})
        item["freshness"] = _freshness(item.get("provenance"), reference, freshness_days)
        result.append(item)
    return result


def _reservation(record: dict[str, Any], places: dict[str, dict[str, Any]], used: set[str], trip: dict[str, Any], reference: datetime, freshness_days: int) -> dict[str, Any] | None:
    place_id = record.get("place_id")
    selected_flights = set(trip.get("selected", {}).get("flight_ids", []))
    transport_legs = {leg.get("id") for leg in trip.get("candidate_sets", {}).get("transport_legs", [])}
    if not ((place_id in places and place_id in used) or record.get("flight_id") in selected_flights or record.get("transport_leg_id") in transport_legs):
        return None
    # The public read model is an allowlist.  Booking payloads are frequently
    # provider-shaped and may contain arbitrary PII, so copying then redacting
    # cannot safely establish the public boundary.
    allowed = {"kind", "place_id", "flight_id", "transport_leg_id", "start_at", "end_at", "status", "recheck_at", "provenance"}
    item = {key: deepcopy(value) for key, value in record.items() if key in allowed}
    item["provenance"] = _public_provenance(item.get("provenance"), include_source_url=False)
    confirmation = _confirmation_display(record)
    if confirmation:
        item["confirmation_display"] = confirmation
    if place_id is not None:
        item["place_name"] = places[place_id].get("name", place_id)
    item["freshness"] = _freshness(item.get("provenance"), reference, freshness_days)
    return item


def _evidence_records(records: list[dict[str, Any]], used: set[str], reference: datetime, freshness_days: int) -> list[dict[str, Any]]:
    result = []
    for record in records:
        if record.get("place_id") not in used:
            continue
        item = deepcopy(record)
        item["provenance"] = _public_provenance(item.get("provenance"))
        item["freshness"] = _freshness(item.get("provenance"), reference, freshness_days)
        result.append(item)
    return result


def _freshness(provenance: Any, reference: datetime, freshness_days: int) -> dict[str, Any]:
    if not isinstance(provenance, dict) or not provenance.get("retrieved_at"):
        return {"state": "unknown", "retrieved_at": None}
    try:
        retrieved = datetime.fromisoformat(provenance["retrieved_at"])
        if retrieved.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError):
        return {"state": "unknown", "retrieved_at": provenance.get("retrieved_at")}
    age_days = (reference - retrieved).total_seconds() / 86400
    if age_days < 0:
        return {"state": "invalid", "retrieved_at": provenance["retrieved_at"]}
    return {"state": "stale" if age_days > freshness_days else "fresh", "retrieved_at": provenance["retrieved_at"]}


def _public_provenance(provenance: Any, *, include_source_url: bool = True) -> dict[str, Any] | None:
    """Keep only source metadata that is safe for a public static handbook."""
    if not isinstance(provenance, dict):
        return None
    public = {key: deepcopy(provenance[key]) for key in ("source_type", "provider", "retrieved_at", "status", "confidence") if key in provenance}
    if include_source_url and isinstance(provenance.get("source_url"), str):
        parsed = urlsplit(provenance["source_url"])
        try:
            port = parsed.port
        except ValueError:
            port = None
        if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
            hostname = parsed.hostname if ":" not in parsed.hostname else f"[{parsed.hostname}]"
            netloc = f"{hostname}:{port}" if port else hostname
            public["source_url"] = urlunsplit((parsed.scheme.lower(), netloc, parsed.path, "", ""))
    return public


def _confirmation_display(record: dict[str, Any]) -> str | None:
    for key, value in record.items():
        normalized = "".join(character.lower() for character in key if character.isalnum())
        if normalized in _CONFIRMATION_KEYS and value not in (None, ""):
            return f"…{str(value)[-4:]}"
    return None


def _traveler_notes(trip: dict[str, Any]) -> dict[str, Any]:
    profile = trip.get("traveler_profile", {})
    children = profile.get("children", [])
    return {"packing_checklist": ["護照與必要證件", "行程日所需藥物", "充電設備"], "child_notes": [child.get("notes") for child in children if child.get("notes")], "accessibility_needs": deepcopy(profile.get("accessibility_needs", []))}


def _departure_recheck(trip: dict[str, Any], reservations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = [{"kind": "route", "label": "重新確認每日導航、交通與停車資訊"}, {"kind": "conditions", "label": "重新確認天氣、警示與營業狀態"}]
    if trip.get("selected", {}).get("flight_ids"):
        checks.append({"kind": "flight", "label": "重新確認航班時間與報到要求"})
    if reservations:
        checks.append({"kind": "reservation", "label": "重新確認訂位時間與條款"})
    return checks


def _sources(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = []
    for item in (entry for group in groups for entry in group):
        provenance = item.get("provenance")
        if not isinstance(provenance, dict) or not provenance.get("source_url"):
            continue
        url = provenance["source_url"]
        # Do not collapse equal URLs: their retrieval times may differ and
        # every stale operational fact must remain visible to the reader.
        sources.append({"source_url": url, "provider": provenance.get("provider"), "retrieved_at": provenance.get("retrieved_at"), "freshness": item["freshness"]})
    return sources
