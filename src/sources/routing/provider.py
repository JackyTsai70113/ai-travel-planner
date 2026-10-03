"""Routing provider contract and a fixture-backed deterministic implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import PlaceRef, Route, RouteMode, RouteProvenance, RouteStatus, RouteStep


class RoutingProvider(ABC):
    """Provider SDKs stay behind this contract."""

    @abstractmethod
    def fetch(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode) -> Route:
        """Fetch one route. Implementations must return UNKNOWN on an unavailable route."""

    def fetch_at(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode, departure_at: datetime) -> Route:
        """Fetch a departure-sensitive route; static providers cannot verify transit schedules."""
        if mode is RouteMode.TRANSIT:
            return Route(origin, destination, mode, RouteStatus.UNSUPPORTED,
                         RouteProvenance(type(self).__name__, datetime.now(timezone.utc),
                                         note="provider does not support departure-time transit routes"))
        return self.fetch(origin, destination, mode)

    def fetch_matrix(self, places: Iterable[PlaceRef], mode: RouteMode) -> dict[tuple[str, str, str], Route]:
        """Optional batched lookup; the default preserves compatibility with single-route SDKs."""
        refs = tuple(places)
        return {
            (mode.value, origin.place_id, destination.place_id): self.fetch(origin, destination, mode)
            for origin in refs for destination in refs if origin != destination
        }


class ModeRoutingProvider(RoutingProvider):
    """Dispatch normalized requests to providers that support each travel mode."""

    def __init__(self, providers: dict[RouteMode, RoutingProvider]) -> None:
        self.providers = dict(providers)

    def fetch(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode) -> Route:
        provider = self.providers.get(mode)
        if provider is None:
            return Route(origin, destination, mode, RouteStatus.UNSUPPORTED,
                         RouteProvenance("mode-router", datetime.now(timezone.utc),
                                         note=f"no provider supports {mode.value}"))
        return provider.fetch(origin, destination, mode)

    def fetch_at(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode,
                 departure_at: datetime) -> Route:
        provider = self.providers.get(mode)
        if provider is None:
            return self.fetch(origin, destination, mode)
        return provider.fetch_at(origin, destination, mode, departure_at)

    def fetch_matrix(self, places: Iterable[PlaceRef], mode: RouteMode) -> dict[tuple[str, str, str], Route]:
        provider = self.providers.get(mode)
        if provider is None:
            return super().fetch_matrix(places, mode)
        return provider.fetch_matrix(places, mode)


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

    def fetch_at(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode, departure_at: datetime) -> Route:
        del departure_at
        return self.fetch(origin, destination, mode)

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


class GoogleTransitProvider(RoutingProvider):
    """Departure-time transit routes and walking connections from Google Routes API."""

    provider_name = "google-routes-transit"
    endpoint = "https://routes.googleapis.com/directions/v2:computeRoutes"
    field_mask = ",".join((
        "routes.duration", "routes.distanceMeters", "routes.legs.startTime", "routes.legs.endTime",
        "routes.legs.steps.travelMode", "routes.legs.steps.duration", "routes.legs.steps.transitDetails",
    ))

    def __init__(self, *, api_key: str | None = None, timeout_seconds: float = 10,
                 opener: Callable[..., object] = urlopen,
                 now: Callable[[], datetime] | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("GOOGLE_MAPS_API_KEY")
        self.timeout_seconds = timeout_seconds
        self._opener = opener
        self._now = now or (lambda: datetime.now(timezone.utc))

    def fetch(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode) -> Route:
        if mode is RouteMode.TRANSIT:
            return self._unavailable(origin, destination, RouteStatus.UNSUPPORTED,
                                     "transit lookup requires an explicit departure time")
        return Route(origin, destination, mode, RouteStatus.UNSUPPORTED,
                     self._provenance("Google Routes adapter only handles transit"))

    def fetch_at(self, origin: PlaceRef, destination: PlaceRef, mode: RouteMode,
                 departure_at: datetime) -> Route:
        if mode is not RouteMode.TRANSIT:
            return self.fetch(origin, destination, mode)
        if departure_at.tzinfo is None or departure_at.utcoffset() is None:
            return self._unavailable(origin, destination, RouteStatus.ERROR,
                                     "transit departure time must include a timezone")
        if origin.latitude is None or destination.latitude is None:
            return self._unavailable(origin, destination, RouteStatus.ERROR,
                                     "transit routing requires coordinates for both places")
        if not self.api_key:
            return self._unavailable(origin, destination, RouteStatus.ERROR,
                                     "GOOGLE_MAPS_API_KEY is not configured")
        now = self._now()
        if departure_at.astimezone(timezone.utc) < now.astimezone(timezone.utc) - timedelta(days=7) or departure_at.astimezone(timezone.utc) > now.astimezone(timezone.utc) + timedelta(days=100):
            return self._unavailable(origin, destination, RouteStatus.UNSUPPORTED,
                                     "departure time is outside Google's transit query window")
        payload = {
            "origin": {"location": {"latLng": {"latitude": origin.latitude, "longitude": origin.longitude}}},
            "destination": {"location": {"latLng": {"latitude": destination.latitude, "longitude": destination.longitude}}},
            "travelMode": "TRANSIT", "departureTime": departure_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        request = Request(self.endpoint, data=json.dumps(payload).encode(), method="POST", headers={
            "X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": self.field_mask,
            "Content-Type": "application/json", "Accept": "application/json",
        })
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode())
        except TimeoutError:
            return self._unavailable(origin, destination, RouteStatus.TIMEOUT, "provider request timed out")
        except HTTPError as exc:
            status = RouteStatus.RATE_LIMITED if exc.code == 429 else RouteStatus.ERROR
            try:
                return self._unavailable(origin, destination, status, f"provider HTTP {exc.code}")
            finally:
                exc.close()
        except URLError as exc:
            status = RouteStatus.TIMEOUT if "timed out" in str(exc.reason).lower() else RouteStatus.ERROR
            return self._unavailable(origin, destination, status, f"provider network error: {exc.reason}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return self._unavailable(origin, destination, RouteStatus.ERROR, f"provider response error: {exc}")
        routes = body.get("routes") if isinstance(body, dict) else None
        if not isinstance(routes, list) or not routes:
            return self._unavailable(origin, destination, RouteStatus.NO_ROUTE,
                                     "provider returned no transit service for the requested departure")
        try:
            data = routes[0]
            leg = data["legs"][0]
            started = _parse_provider_time(leg["startTime"])
            ended = _parse_provider_time(leg["endTime"])
            steps, wait_seconds, transfer_count = _transit_steps(leg.get("steps", []), started)
            if not steps:
                raise ValueError("provider response omitted transit and walking step details")
            duration = _duration_seconds(data["duration"])
            distance = int(data["distanceMeters"])
            return Route(origin, destination, mode, RouteStatus.AVAILABLE, self._provenance(),
                         duration, distance, started, ended, steps, wait_seconds, transfer_count)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            return self._unavailable(origin, destination, RouteStatus.ERROR,
                                     f"provider response omitted usable schedule details: {exc}")

    def _provenance(self, note: str | None = None) -> RouteProvenance:
        return RouteProvenance(self.provider_name, self._now(), source_url=self.endpoint, note=note)

    def _unavailable(self, origin: PlaceRef, destination: PlaceRef, status: RouteStatus, note: str) -> Route:
        return Route(origin, destination, RouteMode.TRANSIT, status, self._provenance(note))


def _parse_provider_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("provider time lacks timezone")
    return parsed


def _duration_seconds(value: str) -> int:
    if not isinstance(value, str) or not value.endswith("s"):
        raise ValueError("provider duration is not in seconds")
    return int(round(float(value[:-1])))


def _transit_steps(data: list, started: datetime) -> tuple[tuple[RouteStep, ...], int, int]:
    result = []
    cursor = started
    wait_seconds = 0
    transit_count = 0
    for entry in data:
        if entry.get("travelMode") != "TRANSIT":
            duration = _duration_seconds(entry["duration"])
            ended = cursor + timedelta(seconds=duration)
            step_mode = "walk" if entry.get("travelMode") == "WALK" else "other"
            result.append(RouteStep(step_mode, cursor, ended))
            cursor = ended
            continue
        detail = entry.get("transitDetails") or {}
        stops = detail.get("stopDetails") or {}
        departure = _parse_provider_time(stops["departureTime"]) if stops.get("departureTime") else cursor
        arrival = _parse_provider_time(stops["arrivalTime"]) if stops.get("arrivalTime") else None
        if arrival is None or departure < cursor or arrival < departure:
            raise ValueError("transit step has missing or non-monotonic scheduled times")
        wait_seconds += max(0, int((departure - cursor).total_seconds()))
        transit_count += 1
        result.append(_transit_step(entry, departure, arrival))
        cursor = arrival
    return tuple(result), wait_seconds, max(0, transit_count - 1)


def _transit_step(data: dict, departure: datetime, arrival: datetime) -> RouteStep:
    detail = data.get("transitDetails") or {}
    stops = detail.get("stopDetails") or {}
    line = detail.get("transitLine") or {}
    vehicle = line.get("vehicle") or {}
    vehicle_type = str(vehicle.get("type", "OTHER")).lower()
    mode = "train" if vehicle_type in {"train", "subway", "heavy_rail", "commuter_train", "light_rail"} else "bus" if vehicle_type == "bus" else "ferry" if vehicle_type == "ferry" else "other"
    return RouteStep(mode, departure, arrival,
                     (stops.get("departureStop") or {}).get("name"),
                     (stops.get("arrivalStop") or {}).get("name"),
                     line.get("nameShort") or line.get("name"), detail.get("headsign"))
