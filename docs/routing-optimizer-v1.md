# Routing and optimizer V1

`src.sources.routing` is the provider-neutral boundary for travel time. The planner, optimizer and validator receive one `RouteMatrix`; they do not import a provider SDK. A provider supplies a `Route` for a pair of canonical `PlaceRef` IDs (with optional coordinates) and one of `driving`, `transit` or `walking` modes.

Each route retains `duration_seconds`, `distance_meters`, `RouteStatus`, and `RouteProvenance` (`provider`, `retrieved_at`, source metadata). An unavailable lookup is `RouteStatus.UNKNOWN` and has neither duration nor distance. It must not be converted to a guessed or zero-cost route.

## Cache behaviour

`RouteMatrix` caches both available and unknown provider results using `(mode, origin_place_id, destination_place_id)`. It may receive a TTL for live providers; without one, an instance is stable for the pipeline run. Passing that same instance to validation guarantees validation sees the same result that informed the ordering.

`FixtureRoutingProvider` is a deterministic provider stub. `fixtures/routes/fukuoka-routing-fixture.json` documents the portable fixture shape; test fixtures can be instantiated directly as `Route` objects to avoid an I/O dependency.

## Optimizer boundary

`RouteOptimizer` brute-forces flexible POI order within each segment bounded by fixed-time anchors. It scores available route duration (with distance emitted in its result), keeping anchors in their original sequence and retaining their exact timestamps. The optimizer never creates, shifts, or relaxes schedule times.

If any selected consecutive route is unknown, `OptimizationResult.travel_seconds` and `travel_meters` are `None` and it exposes `unknown_route_keys`. `validate_route_availability` turns those into machine-readable `route_unknown` warnings for the trip validator / repair loop.
