"""Machine-readable route availability checks reusable by a trip validator."""

from __future__ import annotations

from src.optimizer import OptimizationResult
from .itinerary import Violation


def validate_route_availability(result: OptimizationResult, path: str = "/days") -> list[Violation]:
    """Expose unknown routing as a validator warning; never silently zero-cost it."""
    return [
        Violation("route_unknown", "warning", f"Route is unavailable for {origin} -> {destination} ({mode})", path)
        for mode, origin, destination in result.unknown_route_keys
    ]
