# Routing and optimizer V1

`src.sources.routing` is the provider-neutral boundary for travel time. The planner, optimizer and validator receive one `RouteMatrix`; they do not import a provider SDK. A provider supplies a `Route` for a pair of canonical `PlaceRef` IDs (with optional coordinates) and one of `driving`, `transit` or `walking` modes.

Each route retains `duration_seconds`, `distance_meters`, `RouteStatus`, and `RouteProvenance` (`provider`, `retrieved_at`, source metadata). An unavailable lookup is `RouteStatus.UNKNOWN` and has neither duration nor distance. It must not be converted to a guessed or zero-cost route.

## Cache behaviour

`RouteMatrix` caches both available and unknown provider results using `(mode, origin_place_id, destination_place_id)`. It may receive a TTL for live providers; without one, an instance is stable for the pipeline run. Passing that same instance to validation guarantees validation sees the same result that informed the ordering.

`FixtureRoutingProvider` is a deterministic provider stub. `fixtures/routes/fukuoka-routing-fixture.json` documents the portable fixture shape; test fixtures can be instantiated directly as `Route` objects to avoid an I/O dependency.

## Live provider: OpenRouteService

`OpenRouteServiceProvider` is the production adapter for the official OpenRouteService Matrix API. It supports `driving` (`driving-car`) and `walking` (`foot-walking`); `transit` returns the machine-readable `unsupported` status and is never silently approximated. Set `OPENROUTESERVICE_API_KEY` in the execution environment (for example, `export OPENROUTESERVICE_API_KEY=...`); do not put a key in a source file, fixture, or CI secret-free test.

The provider sends multi-POI route lookups as one matrix request (up to the service's documented 50-location request limit). It needs latitude and longitude in every `PlaceRef`. OpenRouteService does not consume departure timestamps or timezone, so this adapter does not claim time-dependent routing; callers must keep their own timezone-aware itinerary context.

`RouteMatrix.routes(places, mode)` warms a directed shared snapshot, and `RouteMatrix.invalidate()` removes either an individual cache key or the complete snapshot. A finite matrix TTL refreshes stale entries; without a TTL the snapshot remains stable for the entire pipeline and can be passed unchanged to optimizer and validator. Provider results retain the API timestamp, provider name and documentation URL. `no_route`, `timeout`, `rate_limited`, `unsupported`, and `error` are explicit statuses with no invented duration or distance.

OpenRouteService credentials, quota, pricing and rate limits are account-dependent; consult its current dashboard and API terms before enabling a production key. Configure a short timeout and use an explicit fallback policy at the application boundary (for example, retain `unknown`/unavailable and ask the user to choose another mode), rather than converting provider failures to travel-time estimates. CI uses recorded/mock response fixtures only and must not contact the service.

## Optimizer boundary

`RouteOptimizer` brute-forces flexible POI order within each segment bounded by fixed-time anchors. It scores available route duration (with distance emitted in its result), keeping anchors in their original sequence and retaining their exact timestamps. The optimizer never creates, shifts, or relaxes schedule times.

If any selected consecutive route is unknown, `OptimizationResult.travel_seconds` and `travel_meters` are `None` and it exposes `unknown_route_keys`. `validate_route_availability` turns those into machine-readable `route_unknown` warnings for the trip validator / repair loop.
