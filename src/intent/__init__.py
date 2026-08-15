"""Natural-language request parsing boundary."""

from .contracts import (
    AmbiguousField, ConstraintCondition, ConstraintIssue, ConstraintScope,
    FieldProvenance, MissingField, RequestConstraint, TimeWindow, TravelIntent,
    TravelerGroup, TripRequest,
)
from .parser import parse_trip_request

__all__ = [
    "AmbiguousField", "ConstraintCondition", "ConstraintIssue", "ConstraintScope",
    "FieldProvenance", "MissingField", "RequestConstraint", "TimeWindow",
    "TravelIntent", "TravelerGroup", "TripRequest", "parse_trip_request",
]
