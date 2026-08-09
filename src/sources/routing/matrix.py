"""Shared route matrix with a cache for planner, optimizer and validator reuse."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from .models import PlaceRef, Route, RouteMode
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

    def route(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode) -> Route:
        key = (mode.value, origin.place_id, destination.place_id)
        cached = self._cache.get(key)
        if cached is not None and not self._expired(cached[1]):
            return cached[0]
        route = self.provider.fetch(origin, destination, mode)
        if route.cache_key != key:
            raise ValueError("routing provider returned a route for a different request")
        self._cache[key] = (route, self._now())
        return route

    def _expired(self, stored_at: datetime) -> bool:
        return self.ttl is not None and self._now() - stored_at >= self.ttl

    @property
    def cached_routes(self) -> tuple[Route, ...]:
        return tuple(item[0] for item in self._cache.values())
