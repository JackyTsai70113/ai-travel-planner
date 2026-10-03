from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import unittest
from urllib.error import HTTPError

from src.sources.routing import OpenRouteServiceProvider, PlaceRef, RouteMatrix, RouteMode, RouteStatus
from src.sources.routing.provider import GoogleTransitProvider
from src.optimizer import RouteOptimizer, Stop


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class OpenRouteServiceProviderTests(unittest.TestCase):
    def setUp(self):
        self.places = (PlaceRef("a", 35.0, 139.0), PlaceRef("b", 35.1, 139.1), PlaceRef("c", 35.2, 139.2))

    def test_batched_matrix_maps_duration_distance_and_provenance(self):
        calls = []
        def opener(request, timeout):
            calls.append((request, timeout))
            return _Response({"durations": [[0, 61.2, None], [60, 0, 120], [None, 121, 0]], "distances": [[0, 501.5, None], [500, 0, 900], [None, 901, 0]]})
        provider = OpenRouteServiceProvider(api_key="test-key", opener=opener, now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
        matrix = RouteMatrix(provider)
        routes = matrix.routes(self.places, RouteMode.DRIVING)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(routes), 6)
        ab = matrix.route(self.places[0], self.places[1], RouteMode.DRIVING)
        self.assertEqual((ab.duration_seconds, ab.distance_meters, ab.status.value), (61, 502, "available"))
        self.assertEqual(ab.provenance.provider, "openrouteservice")
        self.assertEqual(matrix.route(self.places[0], self.places[2], RouteMode.DRIVING).status, RouteStatus.NO_ROUTE)

    def test_transit_is_explicitly_unsupported_without_network(self):
        provider = OpenRouteServiceProvider(api_key="test-key", opener=lambda *_args, **_kwargs: self.fail("network called"))
        route = provider.fetch(*self.places[:2], RouteMode.TRANSIT)
        self.assertEqual(route.status, RouteStatus.UNSUPPORTED)

    def test_rate_limit_and_timeout_have_machine_readable_status(self):
        limited = OpenRouteServiceProvider(api_key="test-key", opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(HTTPError("x", 429, "limited", {}, BytesIO())))
        self.assertEqual(limited.fetch(*self.places[:2], RouteMode.WALKING).status, RouteStatus.RATE_LIMITED)
        timeout = OpenRouteServiceProvider(api_key="test-key", opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(timeout.fetch(*self.places[:2], RouteMode.WALKING).status, RouteStatus.TIMEOUT)

    def test_invalidation_causes_new_provider_snapshot(self):
        count = [0]
        def opener(*_args, **_kwargs):
            count[0] += 1
            return _Response({"durations": [[0, 1], [1, 0]], "distances": [[0, 1], [1, 0]]})
        matrix = RouteMatrix(OpenRouteServiceProvider(api_key="test-key", opener=opener))
        matrix.route(*self.places[:2], RouteMode.DRIVING)
        matrix.invalidate(("driving", "a", "b"))
        matrix.route(*self.places[:2], RouteMode.DRIVING)
        self.assertEqual(count[0], 2)

    def test_optimizer_does_not_turn_no_route_into_zero_cost(self):
        provider = OpenRouteServiceProvider(api_key="test-key", opener=lambda *_args, **_kwargs: _Response({"durations": [[0, None], [None, 0]], "distances": [[0, None], [None, 0]]}))
        result = RouteOptimizer(RouteMatrix(provider), RouteMode.DRIVING).optimize([Stop(self.places[0]), Stop(self.places[1])])
        self.assertTrue(result.has_unknown_routes)
        self.assertIsNone(result.travel_seconds)

    def test_google_transit_route_keeps_departure_steps_wait_and_transfers(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return _Response({"routes": [{"duration": "1800s", "distanceMeters": 5000, "legs": [{
                "startTime": "2026-04-10T09:00:00Z", "endTime": "2026-04-10T09:30:00Z", "steps": [
                    {"travelMode": "WALK", "duration": "300s"},
                    {"travelMode": "TRANSIT", "transitDetails": {"stopDetails": {
                        "departureTime": "2026-04-10T09:06:00Z", "arrivalTime": "2026-04-10T09:15:00Z",
                        "departureStop": {"name": "A"}, "arrivalStop": {"name": "B"}},
                        "transitLine": {"nameShort": "R1", "vehicle": {"type": "SUBWAY"}}, "headsign": "Central"}},
                    {"travelMode": "WALK", "duration": "300s"},
                    {"travelMode": "TRANSIT", "transitDetails": {"stopDetails": {
                        "departureTime": "2026-04-10T09:23:00Z", "arrivalTime": "2026-04-10T09:26:00Z",
                        "departureStop": {"name": "B"}, "arrivalStop": {"name": "C"}},
                        "transitLine": {"name": "Bus 2", "vehicle": {"type": "BUS"}}}},
                    {"travelMode": "WALK", "duration": "240s"},
                ]}]}]})

        provider = GoogleTransitProvider(api_key="test-key", opener=opener,
                                         now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
        departure = datetime(2026, 4, 10, 9, tzinfo=timezone.utc)
        route = provider.fetch_at(self.places[0], self.places[1], RouteMode.TRANSIT, departure)

        self.assertEqual(route.status, RouteStatus.AVAILABLE)
        self.assertEqual((route.wait_seconds, route.transfer_count), (60 + 180, 1))
        self.assertEqual([step.mode for step in route.steps], ["walk", "train", "walk", "bus", "walk"])
        self.assertEqual((route.departure_at.isoformat(), route.arrival_at.isoformat()),
                         ("2026-04-10T09:00:00+00:00", "2026-04-10T09:30:00+00:00"))
        self.assertIn('"travelMode": "TRANSIT"', calls[0][0].data.decode())
        self.assertEqual(calls[0][0].headers["X-goog-api-key"], "test-key")
        self.assertIn("routes.legs.steps.transitDetails", calls[0][0].headers["X-goog-fieldmask"])

    def test_google_transit_no_service_and_out_of_window_are_unverified(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        provider = GoogleTransitProvider(api_key="test-key", opener=lambda *_args, **_kwargs: _Response({"routes": []}), now=lambda: now)
        absent = provider.fetch_at(self.places[0], self.places[1], RouteMode.TRANSIT,
                                   datetime(2026, 4, 10, 22, tzinfo=timezone.utc))
        expired = provider.fetch_at(self.places[0], self.places[1], RouteMode.TRANSIT,
                                    datetime(2026, 5, 1, 22, tzinfo=timezone.utc))
        too_old = provider.fetch_at(self.places[0], self.places[1], RouteMode.TRANSIT,
                                    datetime(2025, 12, 20, 22, tzinfo=timezone.utc))
        self.assertEqual(absent.status, RouteStatus.NO_ROUTE)
        self.assertEqual(expired.status, RouteStatus.UNSUPPORTED)
        self.assertEqual(too_old.status, RouteStatus.UNSUPPORTED)

    def test_route_matrix_separates_transit_cache_by_departure_time(self):
        calls = []
        provider = GoogleTransitProvider(api_key="test-key",
                                         opener=lambda *_args, **_kwargs: (calls.append(1) or _Response({"routes": []})),
                                         now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
        matrix = RouteMatrix(provider)
        morning = datetime(2026, 4, 10, 8, tzinfo=timezone.utc)
        evening = datetime(2026, 4, 10, 20, tzinfo=timezone.utc)

        self.assertEqual(matrix.route_at(*self.places[:2], RouteMode.TRANSIT, morning).status, RouteStatus.NO_ROUTE)
        self.assertEqual(matrix.route_at(*self.places[:2], RouteMode.TRANSIT, morning).status, RouteStatus.NO_ROUTE)
        self.assertEqual(matrix.route_at(*self.places[:2], RouteMode.TRANSIT, evening).status, RouteStatus.NO_ROUTE)

        self.assertEqual(len(calls), 2)

    def test_route_matrix_refreshes_expired_timed_snapshot(self):
        calls = []
        now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        provider = GoogleTransitProvider(api_key="test-key",
                                         opener=lambda *_args, **_kwargs: (calls.append(1) or _Response({"routes": []})),
                                         now=lambda: now[0])
        matrix = RouteMatrix(provider, ttl=timedelta(minutes=15), now=lambda: now[0])
        departure = datetime(2026, 4, 10, 8, tzinfo=timezone.utc)
        matrix.route_at(*self.places[:2], RouteMode.TRANSIT, departure)
        now[0] += timedelta(minutes=15)
        matrix.route_at(*self.places[:2], RouteMode.TRANSIT, departure)
        self.assertEqual(len(calls), 2)
