"""Shared route matrix with a cache for planner, optimizer and validator reuse."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
from typing import Callable

from .models import PlaceRef, Route, RouteMode, RouteFreshness
from .provider import RoutingProvider


class RouteMatrix:
    """Cache every provider response, including UNKNOWN, by mode and canonical place IDs.

    A finite TTL can be supplied for dynamic providers. A single matrix instance is passed
    through pipeline stages so validation observes exactly the route result used by planning.
    """

    def __init__(
        self,
        provider: RoutingProvider,
        *,
        ttl: timedelta | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.provider = provider
        self.ttl = ttl
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._cache: dict[tuple[str, str, str], tuple[Route, datetime]] = {}
        self._timed_cache: dict[tuple[str, str, str, str], tuple[Route, datetime]] = {}

    def route(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode) -> Route:
        key = (mode.value, origin.place_id, destination.place_id)
        cached = self._cache.get(key)
        if cached is not None and not self._expired(cached[1]):
            return self._with_freshness(cached[0], self._freshness(cached[1]))
        route = self.provider.fetch(origin, destination, mode)
        if route.cache_key != key:
            raise ValueError("routing provider returned a route for a different request")
        stamped = self._with_freshness(route, RouteFreshness.FRESH)
        self._cache[key] = (stamped, self._now())
        return stamped

    def routes(self, places: list[PlaceRef] | tuple[PlaceRef, ...], mode: RouteMode) -> tuple[Route, ...]:
        """Warm and return a multi-POI directed matrix, using provider batching when possible."""
        refs = tuple(places)
        missing = [(origin, destination) for origin in refs for destination in refs if origin != destination
                   if (mode.value, origin.place_id, destination.place_id) not in self._cache or self._expired(self._cache[(mode.value, origin.place_id, destination.place_id)][1])]
        if missing:
            supplied = self.provider.fetch_matrix(refs, mode)
            for origin, destination in missing:
                key = (mode.value, origin.place_id, destination.place_id)
                route = supplied.get(key)
                if route is None or route.cache_key != key:
                    raise ValueError("routing provider did not return requested matrix route")
                self._cache[key] = (self._with_freshness(route, RouteFreshness.FRESH), self._now())
        return tuple(self.route(origin, destination, mode) for origin in refs for destination in refs if origin != destination)

    def route_at(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode,
                 departure_at: datetime) -> Route:
        """Cache a time-dependent route by requested mode, places, and exact departure instant."""
        if departure_at.tzinfo is None or departure_at.utcoffset() is None:
            raise ValueError("departure_at must include a timezone")
        departure_key = departure_at.astimezone(timezone.utc).isoformat()
        key = (mode.value, origin.place_id, destination.place_id, departure_key)
        cached = self._timed_cache.get(key)
        if cached is not None and not self._expired(cached[1]):
            return self._with_freshness(cached[0], self._freshness(cached[1]))
        route = self.provider.fetch_at(origin, destination, mode, departure_at)
        if route.cache_key != key[:3]:
            raise ValueError("routing provider returned a route for a different timed request")
        stamped = self._with_freshness(route, RouteFreshness.FRESH)
        self._timed_cache[key] = (stamped, self._now())
        return stamped

    def routes_at(self, places: list[PlaceRef] | tuple[PlaceRef, ...], mode: RouteMode,
                  departure_at: datetime) -> tuple[Route, ...]:
        """Fetch a directed matrix for one departure snapshot; cached independently per time."""
        refs = tuple(places)
        return tuple(self.route_at(origin, destination, mode, departure_at)
                     for origin in refs for destination in refs if origin != destination)

    def invalidate(self, key: tuple[str, str, str] | None = None) -> None:
        """Explicitly invalidate one entry or the entire shared route snapshot."""
        if key is None:
            self._cache.clear()
            self._timed_cache.clear()
        else:
            self._cache.pop(key, None)
            for timed_key in tuple(self._timed_cache):
                if timed_key[:3] == key:
                    self._timed_cache.pop(timed_key, None)

    def _expired(self, stored_at: datetime) -> bool:
        return self.ttl is not None and self._now() - stored_at >= self.ttl

    @property
    def cached_routes(self) -> tuple[Route, ...]:
        static = tuple(item[0] for _, item in self._cache.items() if not self._expired(item[1]))
        timed = tuple(item[0] for _, item in self._timed_cache.items() if not self._expired(item[1]))
        return static + timed

    def _with_freshness(self, route: Route, freshness: RouteFreshness) -> Route:
        if route.provenance.freshness is freshness:
            return route
        return replace(route, provenance=replace(route.provenance, freshness=freshness))

    def _freshness(self, stored_at: datetime) -> RouteFreshness:
        if self.ttl is None:
            return RouteFreshness.FRESH
        return RouteFreshness.FRESH if self._now() - stored_at < self.ttl else RouteFreshness.STALE
