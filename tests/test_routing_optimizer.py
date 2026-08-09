from datetime import datetime, timedelta, timezone
import unittest

from src.optimizer import RouteOptimizer, Stop
from src.sources.routing import (
    FixtureRoutingProvider,
    PlaceRef,
    Route,
    RouteMatrix,
    RouteMode,
    RouteProvenance,
    RouteStatus,
)
from src.validator import validate_route_availability


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def route(origin: str, destination: str, seconds: int, meters: int | None = None) -> Route:
    return Route(
        PlaceRef(origin), PlaceRef(destination), RouteMode.DRIVING, RouteStatus.AVAILABLE,
        RouteProvenance("fixture-routing", NOW), seconds, meters if meters is not None else seconds * 10,
    )


class RoutingAndOptimizerTests(unittest.TestCase):
    def test_matrix_caches_provider_result_including_unknown(self):
        provider = FixtureRoutingProvider([route("a", "b", 120)])
        matrix = RouteMatrix(provider)
        self.assertEqual(matrix.route(PlaceRef("a"), PlaceRef("b"), RouteMode.DRIVING).duration_seconds, 120)
        self.assertEqual(matrix.route(PlaceRef("a"), PlaceRef("b"), RouteMode.DRIVING).duration_seconds, 120)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(matrix.route(PlaceRef("b"), PlaceRef("missing"), RouteMode.DRIVING).status, RouteStatus.UNKNOWN)
        self.assertEqual(matrix.route(PlaceRef("b"), PlaceRef("missing"), RouteMode.DRIVING).status, RouteStatus.UNKNOWN)
        self.assertEqual(provider.calls, 2)

    def test_matrix_refreshes_after_ttl(self):
        clock = [NOW]
        provider = FixtureRoutingProvider([route("a", "b", 120)])
        matrix = RouteMatrix(provider, ttl=timedelta(minutes=5), now=lambda: clock[0])
        matrix.route(PlaceRef("a"), PlaceRef("b"), RouteMode.DRIVING)
        clock[0] += timedelta(minutes=5)
        matrix.route(PlaceRef("a"), PlaceRef("b"), RouteMode.DRIVING)
        self.assertEqual(provider.calls, 2)

    def test_four_poi_ordering_clusters_low_travel_route(self):
        # a -> c -> b -> d is 3 minutes total; the input deliberately is scrambled.
        routes = [
            route("a", "c", 60), route("c", "b", 60), route("b", "d", 60),
            route("a", "b", 600), route("a", "d", 900), route("b", "c", 600),
            route("c", "d", 600), route("d", "b", 900), route("d", "c", 900),
        ]
        optimizer = RouteOptimizer(RouteMatrix(FixtureRoutingProvider(routes)), RouteMode.DRIVING)
        result = optimizer.optimize([Stop(PlaceRef("a")), Stop(PlaceRef("d")), Stop(PlaceRef("b")), Stop(PlaceRef("c"))])
        self.assertEqual([stop.place.place_id for stop in result.stops], ["a", "c", "b", "d"])
        self.assertEqual(result.travel_seconds, 180)
        self.assertEqual(result.travel_meters, 1800)

    def test_fixed_time_anchor_is_not_moved_or_rescheduled(self):
        fixed_start = datetime(2026, 4, 10, 12, tzinfo=timezone.utc)
        fixed_end = datetime(2026, 4, 10, 13, tzinfo=timezone.utc)
        anchor = Stop(PlaceRef("reservation"), fixed_start, fixed_end)
        routes = [
            route("a", "b", 60), route("b", "reservation", 60), route("a", "reservation", 500),
            route("reservation", "c", 60), route("reservation", "d", 500), route("c", "d", 60),
        ]
        optimizer = RouteOptimizer(RouteMatrix(FixtureRoutingProvider(routes)), RouteMode.DRIVING)
        result = optimizer.optimize([Stop(PlaceRef("b")), Stop(PlaceRef("a")), anchor, Stop(PlaceRef("d")), Stop(PlaceRef("c"))])
        self.assertEqual([stop.place.place_id for stop in result.stops], ["a", "b", "reservation", "c", "d"])
        optimized_anchor = result.stops[2]
        self.assertEqual((optimized_anchor.fixed_start_at, optimized_anchor.fixed_end_at), (fixed_start, fixed_end))

    def test_unknown_route_reaches_validator_without_zero_cost(self):
        optimizer = RouteOptimizer(RouteMatrix(FixtureRoutingProvider([])), RouteMode.WALKING)
        result = optimizer.optimize([Stop(PlaceRef("a")), Stop(PlaceRef("b"))])
        self.assertTrue(result.has_unknown_routes)
        self.assertIsNone(result.travel_seconds)
        self.assertIsNone(result.travel_meters)
        violations = validate_route_availability(result, "/days/0/items")
        self.assertEqual(violations[0].code, "route_unknown")
        self.assertEqual(violations[0].path, "/days/0/items")


if __name__ == "__main__":
    unittest.main()
