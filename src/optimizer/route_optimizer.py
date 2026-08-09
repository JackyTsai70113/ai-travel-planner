"""Deterministic first-pass POI ordering using the shared route matrix."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import permutations

from src.sources.routing import PlaceRef, RouteMatrix, RouteMode, RouteStatus


@dataclass(frozen=True)
class Stop:
    place: PlaceRef
    fixed_start_at: datetime | None = None
    fixed_end_at: datetime | None = None

    @property
    def is_fixed_anchor(self) -> bool:
        return self.fixed_start_at is not None or self.fixed_end_at is not None

    def __post_init__(self) -> None:
        if (self.fixed_start_at is None) != (self.fixed_end_at is None):
            raise ValueError("fixed anchors require both start and end times")
        if self.fixed_start_at is not None and self.fixed_start_at >= self.fixed_end_at:
            raise ValueError("fixed anchor end must be after start")


@dataclass(frozen=True)
class OptimizationResult:
    stops: tuple[Stop, ...]
    travel_seconds: int | None
    travel_meters: int | None
    unknown_route_keys: tuple[tuple[str, str, str], ...]

    @property
    def has_unknown_routes(self) -> bool:
        return bool(self.unknown_route_keys)


class RouteOptimizer:
    """Order flexible POIs inside fixed-anchor boundaries without scheduling changes.

    Anchor timestamps are immutable and no stop may cross an anchor. Unknown routes make
    the result explicitly unscored instead of being treated as zero-cost travel.
    """

    def __init__(self, matrix: RouteMatrix, mode: RouteMode) -> None:
        self.matrix = matrix
        self.mode = mode

    def optimize(self, stops: list[Stop] | tuple[Stop, ...]) -> OptimizationResult:
        result: list[Stop] = []
        flexible: list[Stop] = []
        previous_boundary: Stop | None = None

        for stop in stops:
            if stop.is_fixed_anchor:
                result.extend(self._best_block(flexible, previous_boundary, stop))
                flexible = []
                result.append(stop)
                previous_boundary = stop
            else:
                flexible.append(stop)
        result.extend(self._best_block(flexible, previous_boundary, None))
        return self._score(tuple(result))

    def _best_block(self, stops: list[Stop], before: Stop | None, after: Stop | None) -> tuple[Stop, ...]:
        if len(stops) < 2:
            return tuple(stops)
        candidates = tuple(permutations(stops))
        scored = [(self._candidate_cost(order, before, after), order) for order in candidates]
        usable = [candidate for candidate in scored if candidate[0] is not None]
        if not usable:
            return candidates[0]
        return min(usable, key=lambda candidate: (candidate[0], tuple(s.place.place_id for s in candidate[1])))[1]

    def _candidate_cost(self, stops: tuple[Stop, ...], before: Stop | None, after: Stop | None) -> int | None:
        chain = ((before,) if before else ()) + stops + ((after,) if after else ())
        total = 0
        for first, second in zip(chain, chain[1:]):
            route = self.matrix.route(first.place, second.place, self.mode)
            if route.status is RouteStatus.UNKNOWN:
                return None
            total += route.duration_seconds or 0
        return total

    def _score(self, stops: tuple[Stop, ...]) -> OptimizationResult:
        total_seconds = total_meters = 0
        unknown: list[tuple[str, str, str]] = []
        for first, second in zip(stops, stops[1:]):
            route = self.matrix.route(first.place, second.place, self.mode)
            if route.status is RouteStatus.UNKNOWN:
                unknown.append(route.cache_key)
                continue
            total_seconds += route.duration_seconds or 0
            total_meters += route.distance_meters or 0
        if unknown:
            return OptimizationResult(stops, None, None, tuple(unknown))
        return OptimizationResult(stops, total_seconds, total_meters, ())
