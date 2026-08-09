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
    source_type: str = "provider"
    source_url: str | None = None
    note: str | None = None


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

    def __post_init__(self) -> None:
        if self.status is RouteStatus.AVAILABLE:
            if self.duration_seconds is None or self.distance_meters is None:
                raise ValueError("available routes require duration_seconds and distance_meters")
            if self.duration_seconds < 0 or self.distance_meters < 0:
                raise ValueError("route costs cannot be negative")
        elif self.duration_seconds is not None or self.distance_meters is not None:
            raise ValueError("unavailable routes cannot contain guessed duration or distance")

    @property
    def cache_key(self) -> tuple[str, str, str]:
        return (self.mode.value, self.origin.place_id, self.destination.place_id)
