"""Provider-neutral canonical place resolution contracts."""

from .resolution import (
    CanonicalPlace,
    MatchDecision,
    NavigationPoint,
    PlaceObservation,
    PlaceResolution,
    merge_observations,
    resolve_places,
    select_navigation_target,
)

__all__ = [
    "CanonicalPlace",
    "MatchDecision",
    "NavigationPoint",
    "PlaceObservation",
    "PlaceResolution",
    "merge_observations",
    "resolve_places",
    "select_navigation_target",
]
