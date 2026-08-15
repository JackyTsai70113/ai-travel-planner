"""The single production composition root for CLI and local web entrypoints.

This module is intentionally the only place that joins provider adapters to
the existing orchestrator.  It has no fixture imports.  Tests can pass recorded
adapters/providers through ``dependencies`` without changing production code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import os
import re
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from src.intent import TravelIntent
from src.orchestrator import OrchestrationResult, TravelOrchestrator, TravelOrchestratorConfig
from src.restaurant_intelligence import eligible_restaurants, reconcile_restaurant_candidates, validation_opening_hours
from src.sources import (
    AmadeusClient, AmadeusFlightAdapter, AmadeusHotelAdapter, FlightSearchQuery,
    GooglePlacesAdapter, HotPepperGourmetAdapter, HotelSearchQuery, Occupancy, SourceAdapter, SourceQuery,
    YouTubeEvidenceAdapter, collect_from_adapters,
)
from src.sources.routing import OpenRouteServiceProvider, PlaceRef, RouteMatrix, RouteMode, RouteStatus
from src.validator import ValidationContext


REQUIRED_ENVIRONMENT = (
    "GOOGLE_MAPS_API_KEY",
    "YOUTUBE_API_KEY",
    "AMADEUS_CLIENT_ID",
    "AMADEUS_CLIENT_SECRET",
    "OPENROUTESERVICE_API_KEY",
)


class ProductionConfigurationError(RuntimeError):
    """Raised before a run when production infrastructure is not configured."""


class ProductionIncompleteError(RuntimeError):
    """Raised when real normalized data cannot support a truthful Trip."""


def missing_required_configuration(environment: Mapping[str, str] | None = None) -> list[str]:
    environment = environment if environment is not None else os.environ
    return [key for key in REQUIRED_ENVIRONMENT if not environment.get(key)]


@dataclass(frozen=True)
class ProductionDependencies:
    """Replaceable infrastructure seams used by recorded-provider tests only."""

    google: SourceAdapter | None = None
    youtube: YouTubeEvidenceAdapter | None = None
    amadeus_client: AmadeusClient | None = None
    routing_provider: object | None = None
    hotpepper: SourceAdapter | None = None
    official_restaurants: SourceAdapter | None = None


class _ProductionResearchAdapter(SourceAdapter):
    """Runs real provider searches and emits only normalized candidate records."""

    name = "production-research"

    def __init__(self, intent: TravelIntent, google: SourceAdapter, youtube: YouTubeEvidenceAdapter,
                 amadeus_client: AmadeusClient, optional_restaurants: Sequence[SourceAdapter] = ()) -> None:
        self.intent, self.google, self.youtube = intent, google, youtube
        self.optional_restaurants = tuple(optional_restaurants)
        self.flight_search = AmadeusFlightAdapter(amadeus_client)
        self.hotel_search = AmadeusHotelAdapter(amadeus_client)
        self.evidence: list[object] = []
        self.failures: list[object] = []

    def fetch(self, query: SourceQuery):
        # Evidence is deliberately not converted into an operational candidate.
        try:
            self.evidence = list(self.youtube.fetch_evidence(query))
        except Exception as exc:
            self.failures.append(exc)
            self.evidence = []
        candidates, failures = collect_from_adapters((self.google, *self.optional_restaurants), query)
        self.failures.extend(failures)
        origin, destination = _airport_codes(self.intent)
        start, end = _travel_dates(self.intent)
        occupancy = Occupancy(_adults(self.intent), self.intent.travelers.child_ages)
        currency = self.intent.currency or "JPY"
        try:
            candidates.extend(self.flight_search.search(FlightSearchQuery(
                origin, destination, start, occupancy, return_date=end, currency=currency,
                airport_timezones={origin: "Asia/Taipei", destination: "Asia/Tokyo"},
            )).candidates)
        except Exception as exc:
            self.failures.append(exc)
        try:
            candidates.extend(self.hotel_search.search(HotelSearchQuery(
                destination, start, end + timedelta(days=1), occupancy, currency=currency,
            )).candidates)
        except Exception as exc:
            self.failures.append(exc)
        restaurants = reconcile_restaurant_candidates(candidate for collection, candidate in candidates if collection == "restaurants")
        candidates = [(collection, candidate) for collection, candidate in candidates if collection != "restaurants"]
        candidates.extend(("restaurants", candidate) for candidate in restaurants)
        return candidates


class ProductionPlanningRunner:
    """A small facade that preserves one ``run(intent)`` entrypoint for CLI/Web."""

    def __init__(self, orchestrator: TravelOrchestrator, progress_callback: Callable[[str], None] | None = None) -> None:
        self.orchestrator = orchestrator
        self.progress_callback = progress_callback

    def run(self, intent: TravelIntent) -> OrchestrationResult:
        if self.progress_callback:
            self.progress_callback("research")
        result = self.orchestrator.run(intent)
        if self.progress_callback:
            self.progress_callback("completed" if result.succeeded else "failed")
        return result


def create_production_orchestrator(*, trip_id: str, trips_directory: Path = Path("trips"),
                                   site_directory: Path = Path("site"),
                                   progress_callback: Callable[[str], None] | None = None,
                                   environment: Mapping[str, str] | None = None,
                                   dependencies: ProductionDependencies | None = None) -> ProductionPlanningRunner:
    """Build the only live-provider pipeline used by end-user entrypoints.

    No fixture adapter is constructed here. Missing keys fail explicitly before
    a network request. ``dependencies`` exists exclusively to make recorded
    provider scenarios deterministic in CI.
    """
    environment = environment if environment is not None else os.environ
    missing = missing_required_configuration(environment)
    if missing:
        raise ProductionConfigurationError("missing required environment: " + ", ".join(missing))
    dependencies = dependencies or ProductionDependencies()
    google = dependencies.google or GooglePlacesAdapter(api_key=environment["GOOGLE_MAPS_API_KEY"])
    youtube = dependencies.youtube or YouTubeEvidenceAdapter(api_key=environment["YOUTUBE_API_KEY"])
    amadeus = dependencies.amadeus_client or AmadeusClient(environment=dict(environment))
    routing_provider = dependencies.routing_provider or OpenRouteServiceProvider(api_key=environment["OPENROUTESERVICE_API_KEY"])
    optional_restaurants: list[SourceAdapter] = []
    if dependencies.hotpepper is not None:
        optional_restaurants.append(dependencies.hotpepper)
    elif environment.get("HOTPEPPER_API_KEY"):
        optional_restaurants.append(HotPepperGourmetAdapter(api_key=environment["HOTPEPPER_API_KEY"]))
    if dependencies.official_restaurants is not None:
        optional_restaurants.append(dependencies.official_restaurants)

    # Intent is supplied at run time, so this adapter factory is installed by
    # the facade just before invoking the existing orchestrator.
    runner = _IntentBoundRunner(
        trip_id=trip_id, trips_directory=trips_directory, site_directory=site_directory,
        google=google, youtube=youtube, amadeus=amadeus, routing_provider=routing_provider,
        optional_restaurants=tuple(optional_restaurants),
        progress_callback=progress_callback,
    )
    return runner


class _IntentBoundRunner(ProductionPlanningRunner):
    def __init__(self, *, trip_id: str, trips_directory: Path, site_directory: Path,
                 google: SourceAdapter, youtube: YouTubeEvidenceAdapter, amadeus: AmadeusClient,
                 routing_provider: object, progress_callback: Callable[[str], None] | None,
                 optional_restaurants: Sequence[SourceAdapter] = ()) -> None:
        self.trip_id, self.trips_directory, self.site_directory = _safe_trip_id(trip_id), trips_directory, site_directory
        self.google, self.youtube, self.amadeus = google, youtube, amadeus
        self.optional_restaurants = tuple(optional_restaurants)
        self.routing_provider, self.progress_callback = routing_provider, progress_callback

    def run(self, intent: TravelIntent) -> OrchestrationResult:
        _require_plannable_intent(intent)
        research = _ProductionResearchAdapter(intent, self.google, self.youtube, self.amadeus, self.optional_restaurants)
        config = TravelOrchestratorConfig(
            adapters=(research,),
            candidate_trip_factory=lambda current, store: _candidate_trips(self.trip_id, current, store.records()),
            routing_context_factory=lambda current, store: _routing_context(store.records(), self.routing_provider, current),
            optimizer=lambda candidates, context: tuple(candidates),
            output_directory=self.site_directory,
            trip_output_directory=self.trips_directory,
        )
        orchestrator = TravelOrchestrator(config)
        if self.progress_callback:
            self.progress_callback("research")
        result = orchestrator.run(intent)
        if self.progress_callback:
            self.progress_callback("completed" if result.succeeded else "failed")
        return result


def _candidate_trips(trip_id: str, intent: TravelIntent, records: Iterable[object]) -> Sequence[dict]:
    collections: dict[str, list[dict]] = {name: [] for name in ("places", "restaurants", "hotels", "flights", "transport_legs")}
    for record in records:
        collection, candidate = record.collection, record.candidate  # CandidateRecord protocol; no raw payload crosses here.
        collections[collection].append(candidate)
    start, end = _travel_dates(intent)
    days_count = (end - start).days + 1
    places = [place for place in collections["places"] if place.get("kind") == "poi"]
    restaurants = collections["restaurants"]
    hotels, flights = collections["hotels"], collections["flights"]
    if len(places) < days_count or not restaurants or not hotels or not flights:
        raise ProductionIncompleteError("live provider results are insufficient for a complete trip (need POIs, restaurants, hotel, and flight)")

    tz = ZoneInfo("Asia/Tokyo")
    itinerary_days = []
    selected_meals: list[dict] = []
    for index in range(days_count):
        current_date = start + timedelta(days=index)
        visit_start = datetime.combine(current_date, time(10), tz)
        visit_end = datetime.combine(current_date, time(12), tz)
        meal_start = datetime.combine(current_date, time(12, 30), tz)
        meal_end = datetime.combine(current_date, time(13, 30), tz)
        eligible = eligible_restaurants(restaurants, meal_start, meal_end)
        if not eligible:
            raise ProductionIncompleteError(f"no restaurant has fresh verified opening hours for {current_date.isoformat()} lunch")
        poi, restaurant = places[index], eligible[index % len(eligible)]
        selected_meals.append(restaurant)
        itinerary_days.append({"date": current_date.isoformat(), "summary": poi["name"], "items": [
            {"id": f"day{index + 1}-visit", "kind": "visit", "place_id": poi["id"], "start_at": visit_start.isoformat(), "end_at": visit_end.isoformat(), "selection_status": "selected"},
            {"id": f"day{index + 1}-meal", "kind": "meal", "place_id": restaurant["place"]["id"], "start_at": meal_start.isoformat(), "end_at": meal_end.isoformat(), "selection_status": "selected"},
        ]})

    all_places = [*collections["places"], *(hotel["place"] for hotel in hotels)]
    # De-duplicate the restaurant place if Google returned it in both collections.
    seen: set[str] = set()
    canonical_places = []
    for place in [*all_places, *(restaurant["place"] for restaurant in restaurants)]:
        if place["id"] not in seen:
            seen.add(place["id"]); canonical_places.append(place)
    currency = _budget_currency(intent, flights[0], hotels[0])
    flight_cost = _money_amount(flights[0].get("cost"), currency)
    hotel_cost = _money_amount(hotels[0].get("total_cost"), currency)
    categories = {"flights": {"amount": flight_cost, "currency": currency}, "hotel": {"amount": hotel_cost, "currency": currency}}
    return [{
        "schema_version": "trip-v1", "id": trip_id, "title": " + ".join(intent.destinations) + " 行程",
        "local_timezone": "Asia/Tokyo", "date_range": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "traveler_profile": {"adults": _adults(intent), "children": [{"age": age} for age in intent.travelers.child_ages]},
        "preferences": {"hard_constraints": [], "soft_preferences": []},
        "candidate_sets": {**collections, "places": canonical_places},
        "selected": {"hotel_place_ids": [hotels[0]["place"]["id"]], "flight_ids": [flights[0]["id"]]},
        "days": itinerary_days,
        "budget": {"currency": currency, "categories": categories, "total": {"amount": flight_cost + hotel_cost, "currency": currency}},
        "validation": [],
        "provenance": {"source_type": "derived", "provider": "production composition", "retrieved_at": datetime.now(timezone.utc).isoformat(), "status": "estimated", "note": "Built only from normalized provider candidates; availability requires provider confirmation."},
    }]


def _routing_context(records: Iterable[object], routing_provider: object, intent: TravelIntent) -> ValidationContext:
    places = []
    restaurants = []
    for record in records:
        candidate = record.candidate
        if record.collection == "restaurants":
            restaurants.append(candidate); place = candidate["place"]
        elif record.collection in {"places", "hotels"}:
            place = candidate if record.collection == "places" else candidate["place"]
        else:
            continue
        coordinates = place.get("coordinates", {})
        if isinstance(coordinates, Mapping) and isinstance(coordinates.get("latitude"), (int, float)) and isinstance(coordinates.get("longitude"), (int, float)):
            places.append(PlaceRef(place["id"], coordinates["latitude"], coordinates["longitude"]))
    # ORS has a 50-location request limit; a bounded planning snapshot avoids
    # hidden batching/guessing and makes omitted routes unverified downstream.
    unique = list({place.place_id: place for place in places}.values())[:50]
    minutes: dict[tuple[str, str], int] = {}
    if len(unique) > 1:
        matrix = RouteMatrix(routing_provider, ttl=timedelta(minutes=15))
        mode = RouteMode.DRIVING if "drive" in intent.transport else RouteMode.WALKING
        for route in matrix.routes(unique, mode):
            if route.status is RouteStatus.AVAILABLE and route.duration_seconds is not None:
                minutes[(route.origin.place_id, route.destination.place_id)] = max(1, round(route.duration_seconds / 60))
    return ValidationContext(travel_minutes=minutes, opening_hours=validation_opening_hours(restaurants))


def _require_plannable_intent(intent: TravelIntent) -> None:
    if not intent.destinations or not intent.start_date or not intent.end_date:
        raise ProductionIncompleteError("production planning requires destination and explicit start/end dates; no dates were invented")
    if intent.travelers.adults is None:
        raise ProductionIncompleteError("production planning requires an explicit adult traveler count")


def _travel_dates(intent: TravelIntent) -> tuple[date, date]:
    return date.fromisoformat(intent.start_date or ""), date.fromisoformat(intent.end_date or "")


def _adults(intent: TravelIntent) -> int:
    if intent.travelers.adults is None:
        raise ProductionIncompleteError("adult traveler count is required")
    return intent.travelers.adults


def _airport_codes(intent: TravelIntent) -> tuple[str, str]:
    origin = {"台北": "TPE", "桃園": "TPE", "高雄": "KHH", "香港": "HKG", "東京": "NRT", "大阪": "KIX"}.get(intent.origin or "")
    destination = {"德島": "TKS", "神戶": "UKB", "東京": "TYO", "大阪": "OSA", "京都": "OSA", "福岡": "FUK", "札幌": "SPK", "沖繩": "OKA", "名古屋": "NGO"}.get(intent.destinations[0] if intent.destinations else "")
    if not origin or not destination:
        raise ProductionIncompleteError("origin/destination lacks an explicit Amadeus airport/city-code mapping")
    return origin, destination


def _safe_trip_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")
    if not cleaned or not re.fullmatch(r"[a-z][a-z0-9_-]*", cleaned):
        raise ValueError("trip_id must start with a letter and use lowercase letters, digits, _ or -")
    return cleaned


def _budget_currency(intent: TravelIntent, flight: Mapping[str, object], hotel: Mapping[str, object]) -> str:
    currencies = [value.get("currency") for value in (flight.get("cost", {}), hotel.get("total_cost", {})) if isinstance(value, Mapping)]
    if len(set(currencies)) != 1 or not currencies[0]:
        raise ProductionIncompleteError("flight and hotel provider currencies differ; no conversion rate was invented")
    return str(currencies[0])


def _money_amount(value: object, currency: str) -> float:
    if not isinstance(value, Mapping) or value.get("currency") != currency or not isinstance(value.get("amount"), (int, float)):
        raise ProductionIncompleteError("provider price is missing or cannot be reconciled to the selected currency")
    return float(value["amount"])
