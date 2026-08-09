"""Routing provider contract and a fixture-backed deterministic implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Iterable

from .models import PlaceRef, Route, RouteMode, RouteProvenance, RouteStatus


class RoutingProvider(ABC):
    """Provider SDKs stay behind this contract."""

    @abstractmethod
    def fetch(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode) -> Route:
        """Fetch one route. Implementations must return UNKNOWN on an unavailable route."""


class FixtureRoutingProvider(RoutingProvider):
    """In-memory provider stub for tests and repeatable local planning."""

    def __init__(self, routes: Iterable[Route], provider_name: str = "fixture-routing") -> None:
        self._routes = {route.cache_key: route for route in routes}
        self.provider_name = provider_name
        self.calls = 0

    def fetch(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode) -> Route:
        self.calls += 1
        key = (mode.value, origin.place_id, destination.place_id)
        route = self._routes.get(key)
        if route is not None:
            return route
        return Route(
            origin=origin,
            destination=destination,
            mode=mode,
            status=RouteStatus.UNKNOWN,
            provenance=RouteProvenance(
                provider=self.provider_name,
                retrieved_at=datetime.now(timezone.utc),
                source_type="provider",
                note="No fixture route is available",
            ),
        )
