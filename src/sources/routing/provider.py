"""Routing provider contract and a fixture-backed deterministic implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
import os
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import PlaceRef, Route, RouteMode, RouteProvenance, RouteStatus


class RoutingProvider(ABC):
    """Provider SDKs stay behind this contract."""

    @abstractmethod
    def fetch(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode) -> Route:
        """Fetch one route. Implementations must return UNKNOWN on an unavailable route."""

    def fetch_matrix(self, places: Iterable[PlaceRef], mode: RouteMode) -> dict[tuple[str, str, str], Route]:
        """Optional batched lookup; the default preserves compatibility with single-route SDKs."""
        refs = tuple(places)
        return {
            (mode.value, origin.place_id, destination.place_id): self.fetch(origin, destination, mode)
            for origin in refs for destination in refs if origin != destination
        }


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


class OpenRouteServiceProvider(RoutingProvider):
    """OpenRouteService matrix API adapter (driving-car and foot-walking only).

    The key is deliberately read only from ``OPENROUTESERVICE_API_KEY`` unless supplied
    by the process owner.  No request is made until ``fetch``/``fetch_matrix`` is called.
    """

    provider_name = "openrouteservice"
    _PROFILES = {RouteMode.DRIVING: "driving-car", RouteMode.WALKING: "foot-walking"}

    def __init__(self, *, api_key: str | None = None, timeout_seconds: float = 10,
                 endpoint: str = "https://api.openrouteservice.org/v2/matrix",
                 opener: Callable[..., object] = urlopen, now: Callable[[], datetime] | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTESERVICE_API_KEY")
        self.timeout_seconds = timeout_seconds
        self.endpoint = endpoint.rstrip("/")
        self._opener = opener
        self._now = now or (lambda: datetime.now(timezone.utc))

    def fetch(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode) -> Route:
        return self.fetch_matrix((origin, destination), mode).get(
            (mode.value, origin.place_id, destination.place_id), self._unavailable(origin, destination, mode, RouteStatus.NO_ROUTE)
        )

    def fetch_matrix(self, places: Iterable[PlaceRef], mode: RouteMode) -> dict[tuple[str, str, str], Route]:
        refs = tuple(places)
        if mode not in self._PROFILES:
            return self._all_unavailable(refs, mode, RouteStatus.UNSUPPORTED, "OpenRouteService matrix has no transit profile")
        if not self.api_key:
            return self._all_unavailable(refs, mode, RouteStatus.ERROR, "OPENROUTESERVICE_API_KEY is not configured")
        if len(refs) > 50:
            raise ValueError("OpenRouteService matrix request supports at most 50 locations; batch at caller")
        if any(ref.latitude is None for ref in refs):
            return self._all_unavailable(refs, mode, RouteStatus.ERROR, "coordinates are required by OpenRouteService")
        payload = json.dumps({"locations": [[ref.longitude, ref.latitude] for ref in refs], "metrics": ["duration", "distance"]}).encode()
        request = Request(f"{self.endpoint}/{self._PROFILES[mode]}", data=payload, method="POST", headers={"Authorization": self.api_key, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode())
        except TimeoutError:
            return self._all_unavailable(refs, mode, RouteStatus.TIMEOUT, "provider request timed out")
        except HTTPError as exc:
            status = RouteStatus.RATE_LIMITED if exc.code == 429 else RouteStatus.ERROR
            try:
                return self._all_unavailable(refs, mode, status, f"provider HTTP {exc.code}")
            finally:
                exc.close()
        except URLError as exc:
            status = RouteStatus.TIMEOUT if "timed out" in str(exc.reason).lower() else RouteStatus.ERROR
            return self._all_unavailable(refs, mode, status, f"provider network error: {exc.reason}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return self._all_unavailable(refs, mode, RouteStatus.ERROR, f"provider response error: {exc}")
        durations, distances = body.get("durations"), body.get("distances")
        if not isinstance(durations, list) or not isinstance(distances, list):
            return self._all_unavailable(refs, mode, RouteStatus.ERROR, "provider response omitted matrix metrics")
        result: dict[tuple[str, str, str], Route] = {}
        for i, origin in enumerate(refs):
            for j, destination in enumerate(refs):
                if i == j:
                    continue
                duration = durations[i][j] if i < len(durations) and j < len(durations[i]) else None
                distance = distances[i][j] if i < len(distances) and j < len(distances[i]) else None
                if duration is None or distance is None:
                    route = self._unavailable(origin, destination, mode, RouteStatus.NO_ROUTE, "provider returned no route")
                else:
                    route = Route(origin, destination, mode, RouteStatus.AVAILABLE, self._provenance(), int(round(duration)), int(round(distance)))
                result[route.cache_key] = route
        return result

    def _provenance(self, note: str | None = None) -> RouteProvenance:
        return RouteProvenance(self.provider_name, self._now(), source_url="https://openrouteservice.org/dev/#/api-docs/matrix", note=note)

    def _unavailable(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode, status: RouteStatus, note: str | None = None) -> Route:
        return Route(origin, destination, mode, status, self._provenance(note))

    def _all_unavailable(self, refs: tuple[PlaceRef, ...], mode: RouteMode, status: RouteStatus, note: str) -> dict[tuple[str, str, str], Route]:
        return {route.cache_key: route for origin in refs for destination in refs if origin != destination
                for route in (self._unavailable(origin, destination, mode, status, note),)}
