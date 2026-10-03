"""Provider-neutral route records used by planning, optimisation and validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class RouteMode(str, Enum):
    DRIVING = "driving"
    TRANSIT = "transit"
    WALKING = "walking"


class RouteStatus(str, Enum):
    AVAILABLE = "available"
    UNKNOWN = "unknown"
    NO_ROUTE = "no_route"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class RouteFreshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlaceRef:
    """A canonical place ID, optionally accompanied by coordinates for a provider."""

    place_id: str
    latitude: float | None = None
    longitude: float | None = None

    def __post_init__(self) -> None:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")


@dataclass(frozen=True)
class RouteProvenance:
    provider: str
    retrieved_at: datetime
    freshness: RouteFreshness = RouteFreshness.FRESH
    source_type: str = "provider"
    source_url: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class RouteStep:
    """One provider-reported walking or transit segment with scheduled times."""

    mode: str
    departure_at: datetime | None = None
    arrival_at: datetime | None = None
    departure_stop: str | None = None
    arrival_stop: str | None = None
    line_name: str | None = None
    headsign: str | None = None

    def __post_init__(self) -> None:
        if (self.departure_at is None) != (self.arrival_at is None):
            raise ValueError("step departure_at and arrival_at must be provided together")
        if self.departure_at is not None and self.arrival_at is not None and self.arrival_at < self.departure_at:
            raise ValueError("step arrival cannot precede departure")


@dataclass(frozen=True)
class Route:
    """A route result. Unknown results deliberately have no invented cost."""

    origin: PlaceRef
    destination: PlaceRef
    mode: RouteMode
    status: RouteStatus
    provenance: RouteProvenance
    duration_seconds: int | None = None
    distance_meters: int | None = None
    departure_at: datetime | None = None
    arrival_at: datetime | None = None
    steps: tuple[RouteStep, ...] = ()
    wait_seconds: int = 0
    transfer_count: int = 0

    def __post_init__(self) -> None:
        if self.status is RouteStatus.AVAILABLE:
            if self.duration_seconds is None or self.distance_meters is None:
                raise ValueError("available routes require duration_seconds and distance_meters")
            if self.duration_seconds < 0 or self.distance_meters < 0:
                raise ValueError("route costs cannot be negative")
        elif self.duration_seconds is not None or self.distance_meters is not None:
            raise ValueError("unavailable routes cannot contain guessed duration or distance")
        if (self.departure_at is None) != (self.arrival_at is None):
            raise ValueError("departure_at and arrival_at must be provided together")
        if self.departure_at is not None and self.arrival_at is not None and self.arrival_at < self.departure_at:
            raise ValueError("route arrival cannot precede departure")
        if self.wait_seconds < 0 or self.transfer_count < 0:
            raise ValueError("route wait and transfer counts cannot be negative")

    @property
    def cache_key(self) -> tuple[str, str, str]:
        return (self.mode.value, self.origin.place_id, self.destination.place_id)
