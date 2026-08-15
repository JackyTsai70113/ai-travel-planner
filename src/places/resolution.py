"""Deterministic, provider-neutral place entity resolution.

Names and addresses are useful evidence but never sufficient for an automatic
merge.  Only shared stable identifiers establish identity.  This deliberately
keeps ambiguous chain branches separate until a caller supplies clarification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit


STRONG_IDENTIFIER_TYPES = frozenset(
    {"google_place_id", "official_url", "provider_reference"}
)
_AUTHORITY = {"official": 5, "user_input": 4, "provider": 3, "derived": 2, "community": 1}


def _normalise(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _identifier_value(kind: str, value: str) -> str:
    value = value.strip()
    if kind == "official_url":
        parsed = urlsplit(value)
        value = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))
    return value.casefold()


@dataclass(frozen=True)
class NavigationPoint:
    id: str
    kind: str
    name: str | None = None
    coordinates: tuple[float, float] | None = None
    google_maps_url: str | None = None
    phone: str | None = None
    mapcode: str | None = None
    provenance: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"id": self.id, "kind": self.kind}
        for key in ("name", "google_maps_url", "phone", "mapcode"):
            item = getattr(self, key)
            if item is not None:
                value[key] = item
        if self.coordinates is not None:
            value["coordinates"] = {"latitude": self.coordinates[0], "longitude": self.coordinates[1]}
        if self.provenance is not None:
            value["provenance"] = dict(self.provenance)
        return value


@dataclass(frozen=True)
class PlaceObservation:
    observation_id: str
    name: str
    kind: str
    provenance: Mapping[str, Any]
    aliases: tuple[str, ...] = ()
    identifiers: Mapping[str, str] = field(default_factory=dict)
    address: str | None = None
    coordinates: tuple[float, float] | None = None
    phone: str | None = None
    timezone: str | None = None
    navigation_points: tuple[NavigationPoint, ...] = ()


@dataclass(frozen=True)
class MatchDecision:
    observation_id: str
    canonical_place_id: str | None
    confidence: float
    state: str
    matched_identifiers: tuple[str, ...] = ()
    clarification: str | None = None


@dataclass(frozen=True)
class CanonicalPlace:
    id: str
    name: str
    kind: str
    aliases: tuple[str, ...]
    identifiers: Mapping[str, tuple[str, ...]]
    identifier_provenance: Mapping[tuple[str, str], Mapping[str, Any]]
    address: str | None
    coordinates: tuple[float, float] | None
    phone: str | None
    timezone: str | None
    navigation_points: tuple[NavigationPoint, ...]
    field_provenance: Mapping[str, tuple[Mapping[str, Any], ...]]
    coordinate_conflicts: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "aliases": list(self.aliases),
            "identifiers": [
                {
                    "type": key,
                    "value": item,
                    "provenance": dict(self.identifier_provenance[(key, item)]),
                }
                for key, items in self.identifiers.items()
                for item in items
            ],
            "navigation_points": [item.to_dict() for item in self.navigation_points],
            "field_provenance": {
                key: [dict(p) for p in items] for key, items in self.field_provenance.items() if items
            },
        }
        if self.address is not None:
            value["address"] = self.address
        if self.coordinates is not None:
            value["coordinates"] = {"latitude": self.coordinates[0], "longitude": self.coordinates[1]}
        if self.phone is not None:
            value["phone"] = self.phone
        if self.timezone is not None:
            value["timezone"] = self.timezone
        if self.coordinate_conflicts:
            value["coordinate_conflicts"] = [dict(item) for item in self.coordinate_conflicts]
        return value


@dataclass(frozen=True)
class PlaceResolution:
    places: tuple[CanonicalPlace, ...]
    decisions: tuple[MatchDecision, ...]


def resolve_places(observations: Iterable[PlaceObservation]) -> PlaceResolution:
    """Resolve observations using connected components of strong identifiers."""
    observations = tuple(observations)
    parent = list(range(len(observations)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    seen: dict[tuple[str, str], int] = {}
    for index, observation in enumerate(observations):
        for kind, raw in observation.identifiers.items():
            if kind not in STRONG_IDENTIFIER_TYPES or not raw.strip():
                continue
            key = (kind, _identifier_value(kind, raw))
            if key in seen:
                union(index, seen[key])
            else:
                seen[key] = index

    groups: dict[int, list[PlaceObservation]] = {}
    for index, observation in enumerate(observations):
        groups.setdefault(find(index), []).append(observation)

    places: list[CanonicalPlace] = []
    decisions: list[MatchDecision] = []
    for group in groups.values():
        place = merge_observations(group)
        places.append(place)
        has_identifier = any(
            kind in STRONG_IDENTIFIER_TYPES for observation in group for kind in observation.identifiers
        )
        for observation in group:
            if len(group) > 1 or has_identifier:
                matched = tuple(sorted(kind for kind in observation.identifiers if kind in STRONG_IDENTIFIER_TYPES))
                decisions.append(MatchDecision(observation.observation_id, place.id, 1.0, "resolved", matched))
            else:
                decisions.append(MatchDecision(
                    observation.observation_id,
                    place.id,
                    0.35,
                    "clarification_required",
                    clarification="名稱或地址不足以自動確認地點；請提供 stable identifier 或人工確認。",
                ))
    return PlaceResolution(
        tuple(sorted(places, key=lambda item: item.id)),
        tuple(sorted(decisions, key=lambda item: item.observation_id)),
    )


def merge_observations(observations: Iterable[PlaceObservation]) -> CanonicalPlace:
    observations = tuple(observations)
    if not observations:
        raise ValueError("at least one observation is required")
    ranked = sorted(
        observations,
        key=lambda item: (-_AUTHORITY.get(str(item.provenance.get("source_type")), 0), item.observation_id),
    )
    primary = ranked[0]

    def selected(field_name: str) -> Any:
        return next((getattr(item, field_name) for item in ranked if getattr(item, field_name) is not None), None)

    aliases = {item.name for item in observations}
    aliases.update(alias for item in observations for alias in item.aliases)
    identifiers: dict[str, set[str]] = {}
    identifier_provenance: dict[tuple[str, str], Mapping[str, Any]] = {}
    for item in ranked:
        for kind, value in item.identifiers.items():
            identifiers.setdefault(kind, set()).add(value)
            identifier_provenance.setdefault((kind, value), dict(item.provenance))
    stable = sorted(
        f"{kind}:{_identifier_value(kind, value)}"
        for kind, values in identifiers.items() if kind in STRONG_IDENTIFIER_TYPES
        for value in values
    )
    seed = stable[0] if stable else f"observation:{primary.observation_id}"
    canonical_id = "place-" + sha256(seed.encode()).hexdigest()[:12]
    field_provenance: dict[str, tuple[Mapping[str, Any], ...]] = {}
    for field_name in ("name", "address", "coordinates", "phone", "timezone", "identifiers", "navigation_points"):
        field_provenance[field_name] = tuple(
            dict(item.provenance) for item in ranked
            if (getattr(item, field_name) if field_name != "identifiers" else item.identifiers)
        )
    coordinates = selected("coordinates")
    conflicts = tuple(
        {"coordinates": {"latitude": item.coordinates[0], "longitude": item.coordinates[1]}, "provenance": dict(item.provenance)}
        for item in ranked
        if item.coordinates is not None and coordinates is not None and item.coordinates != coordinates
    )
    nav_by_id: dict[str, NavigationPoint] = {}
    for item in ranked:
        for point in item.navigation_points:
            nav_by_id.setdefault(point.id, point)
    return CanonicalPlace(
        id=canonical_id,
        name=primary.name,
        kind=primary.kind,
        aliases=tuple(sorted(aliases - {primary.name}, key=_normalise)),
        identifiers={key: tuple(sorted(values)) for key, values in sorted(identifiers.items())},
        identifier_provenance=identifier_provenance,
        address=selected("address"),
        coordinates=coordinates,
        phone=selected("phone"),
        timezone=selected("timezone"),
        navigation_points=tuple(nav_by_id.values()),
        field_provenance=field_provenance,
        coordinate_conflicts=conflicts,
    )


def select_navigation_target(place: CanonicalPlace | Mapping[str, Any], purpose: str = "main") -> Mapping[str, Any] | None:
    """Return a routing-ready navigation read model without changing the POI."""
    raw = place.to_dict() if isinstance(place, CanonicalPlace) else dict(place)
    points = raw.get("navigation_points", [])
    preferred = {"driving": ("parking", "entrance"), "walking": ("entrance", "station_exit"), "meeting": ("meeting_point",)}
    kinds = preferred.get(purpose, (purpose,))
    point = next((item for kind in kinds for item in points if item.get("kind") == kind), None)
    if point:
        return {"place_id": raw["id"], "navigation_point_id": point["id"], **point}
    if raw.get("coordinates"):
        return {"place_id": raw["id"], "kind": "main", "coordinates": raw["coordinates"]}
    for key in ("google_maps_url", "phone", "mapcode"):
        if raw.get(key):
            return {"place_id": raw["id"], "kind": "main", key: raw[key]}
    return None
