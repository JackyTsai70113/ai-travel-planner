"""Natural-language request parsing boundary."""

from .contracts import AmbiguousField, FieldProvenance, MissingField, TravelIntent, TravelerGroup, TripRequest
from .parser import parse_trip_request

__all__ = [
    "AmbiguousField", "FieldProvenance", "MissingField", "TravelIntent",
    "TravelerGroup", "TripRequest", "parse_trip_request",
]
