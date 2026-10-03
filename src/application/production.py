"""The single production composition root for CLI and local web entrypoints.

This module is intentionally the only place that joins provider adapters to
the existing orchestrator.  It has no fixture imports.  Tests can pass recorded
adapters/providers through ``dependencies`` without changing production code.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
import os
import re
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from src.intent import TravelIntent
from src.orchestrator import OrchestrationResult, TravelOrchestrator, TravelOrchestratorConfig
from src.planner import SchedulingInput, schedule
from src.restaurant_intelligence import eligible_restaurants, meal_eligibility, reconcile_restaurant_candidates, validation_opening_hours
from src.sources import (
    AdapterFailure, AmadeusClient, AmadeusFlightAdapter, AmadeusHotelAdapter, FlightSearchQuery,
    GooglePlacesAdapter, HotPepperGourmetAdapter, HotelSearchQuery, Occupancy, SourceAdapter, SourceQuery,
    YouTubeEvidenceAdapter, collect_from_adapters,
)
from src.sources.routing import OpenRouteServiceProvider, PlaceRef, RouteMatrix, RouteMode, RouteStatus
from src.validator import OpeningInterval, ValidationContext


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
        self.failures: list[AdapterFailure] = []

    def fetch(self, query: SourceQuery):
        self.failures = []
        query = replace(query, destination=_research_destination(self.intent))
        # Evidence is deliberately not converted into an operational candidate.
        try:
            self.evidence = list(self.youtube.fetch_evidence(query))
        except Exception as exc:
            self.failures.append(AdapterFailure(
                adapter=str(getattr(self.youtube, "name", type(self.youtube).__name__)),
                message=str(exc),
            ))
            self.evidence = []
        candidates, failures = collect_from_adapters((self.google, *self.optional_restaurants), query)
        self.failures.extend(failures)
        start, end = _travel_dates(self.intent)
        occupancy = Occupancy(_adults(self.intent), self.intent.travelers.child_ages)
        currency = self.intent.currency or _default_currency(self.intent)
        if "flights" in query.categories:
            try:
                origin, destination = _airport_codes(self.intent)
                result = self.flight_search.search(FlightSearchQuery(
                    origin, destination, start, occupancy, return_date=end, currency=currency,
                    airport_timezones={code: _airport_timezone(code) for code in _SUPPORTED_AIRPORT_CODES},
                ))
                candidates.extend(result.candidates)
                self.failures.extend(result.failures)
            except Exception as exc:
                self.failures.append(AdapterFailure(self.flight_search.name, str(exc)))
        try:
            result = self.hotel_search.search(HotelSearchQuery(
                _hotel_city_code(self.intent), start, end, occupancy, currency=currency,
                room_quantity=self.intent.room_count or 1,
                room_quantity_explicit=self.intent.room_count is not None,
            ))
            candidates.extend(result.candidates)
            self.failures.extend(result.failures)
        except Exception as exc:
            self.failures.append(AdapterFailure(self.hotel_search.name, str(exc)))
        restaurants = reconcile_restaurant_candidates(candidate for collection, candidate in candidates if collection == "restaurants")
        candidates = [(collection, candidate) for collection, candidate in candidates if collection != "restaurants"]
        candidates.extend(("restaurants", candidate) for candidate in restaurants)
        return candidates

    def drain_failures(self) -> tuple[AdapterFailure, ...]:
        failures = tuple(self.failures)
        self.failures.clear()
        return failures


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
            candidate_trip_factory=lambda current, store: _candidate_trips(self.trip_id, current, store.records(), _routing_context(store.records(), self.routing_provider, current)),
            routing_context_factory=lambda current, store: _routing_context(store.records(), self.routing_provider, current),
            optimizer=lambda candidates, context: tuple(candidates),
            output_directory=self.site_directory,
            trip_output_directory=self.trips_directory,
            research_categories=_research_categories(intent),
        )
        orchestrator = TravelOrchestrator(config)
        if self.progress_callback:
            self.progress_callback("research")
        result = orchestrator.run(intent)
        if self.progress_callback:
            self.progress_callback("completed" if result.succeeded else "failed")
        return result


def _candidate_trips(trip_id: str, intent: TravelIntent, records: Iterable[object], routing: ValidationContext) -> Sequence[dict]:
    collections: dict[str, list[dict]] = {name: [] for name in ("places", "restaurants", "hotels", "flights", "transport_legs")}
    for record in records:
        collection, candidate = record.collection, record.candidate  # CandidateRecord protocol; no raw payload crosses here.
        collections[collection].append(candidate)
    start, end = _travel_dates(intent)
    days_count = (end - start).days + 1
    places = [place for place in collections["places"] if place.get("kind") == "poi"]
    restaurants = collections["restaurants"]
    hotels, flights = collections["hotels"], collections["flights"]
    requires_flights = _requires_flight_search(intent)
    if len(places) < days_count or (requires_flights and not flights):
        required = "POIs and flight" if requires_flights else "POIs"
        raise ProductionIncompleteError(f"live provider results are insufficient for a complete trip (need {required})")
    selected_hotel = _select_hotel_candidate(hotels, intent, start, end, flights, collections["places"])
    restaurants = _restaurant_candidates(restaurants, intent, start, end, routing, places,
                                         selected_hotel["place"]["id"] if selected_hotel else None)

    all_places = [*collections["places"], *(hotel["place"] for hotel in hotels), *(restaurant["place"] for restaurant in restaurants)]
    seen: set[str] = set()
    canonical_places = []
    for place in all_places:
        if place["id"] not in seen:
            seen.add(place["id"]); canonical_places.append(place)
    _record_unknown_night_view_evidence(canonical_places, intent)

    if any(not candidate.get("schedule") for candidate in places):
        # Backward-compatible path for normalized providers that predate the
        # scheduler metadata contract.  New production candidates take the
        # route-aware branch below; this path remains only until those source
        # adapters publish explicit visit-duration facts.
        tz = ZoneInfo(_local_timezone(intent))
        itinerary_days = []
        for index in range(days_count):
            current_date = start + timedelta(days=index)
            visit_start = datetime.combine(current_date, time(10), tz)
            visit_end = datetime.combine(current_date, time(12), tz)
            poi = places[index]
            itinerary_days.append({"date": current_date.isoformat(), "summary": poi["name"], "items": [
                {"id": f"day{index + 1}-visit", "kind": "visit", "place_id": poi["id"], "start_at": visit_start.isoformat(), "end_at": visit_end.isoformat(), "selection_status": "selected"},
            ]})
        trip = _legacy_trip(trip_id, intent, collections, canonical_places, start, end, selected_hotel, flights, itinerary_days)
        trip["candidate_sets"]["restaurants"] = restaurants
        _schedule_legacy_meals(trip, restaurants, routing)
        _add_unfilled_meal_warnings(trip)
        return [trip]

    currency = _budget_currency(intent, flights[0] if flights else None, selected_hotel)
    flight_cost = _money_amount(flights[0].get("cost"), currency) if flights else 0.0
    hotel_cost = _money_amount(selected_hotel.get("total_cost"), currency) if selected_hotel else 0.0
    categories = {"hotel": {"amount": hotel_cost, "currency": currency}}
    if selected_hotel is None:
        categories.pop("hotel")
    if flights:
        categories["flights"] = {"amount": flight_cost, "currency": currency}
    shell = {
        "schema_version": "trip-v1", "id": trip_id, "title": " + ".join(intent.destinations) + " 行程",
        "local_timezone": _local_timezone(intent), "date_range": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "traveler_profile": {"adults": _adults(intent), "children": [{"age": age} for age in intent.travelers.child_ages]},
        "preferences": {"hard_constraints": _canonical_hard_constraints(intent), "soft_preferences": []},
        "candidate_sets": {**collections, "places": canonical_places},
        "selected": {"hotel_place_ids": [selected_hotel["place"]["id"]] if selected_hotel else [], "flight_ids": [flight["id"] for flight in flights[:1]]},
        "days": [],
        "budget": {"currency": currency, "categories": categories, "total": {"amount": flight_cost + hotel_cost, "currency": currency}, "total_status": "incomplete"},
        "validation": [],
        "provenance": {"source_type": "derived", "provider": "production composition", "retrieved_at": datetime.now(timezone.utc).isoformat(), "status": "estimated", "note": _lodging_note(selected_hotel)},
    }
    shell["candidate_sets"]["restaurants"] = restaurants
    shell["budget"]["total_status"] = "incomplete"
    scheduled = schedule(SchedulingInput(shell, routing, daily_start="07:00")).best_trip
    if scheduled is None:
        raise ProductionIncompleteError("no feasible route-aware schedule from normalized candidates")
    _add_unfilled_meal_warnings(scheduled.trip)
    return [scheduled.trip]


def _restaurant_candidates(candidates: Sequence[dict], intent: TravelIntent, start: date, end: date,
                           routing: ValidationContext | None = None, places: Sequence[dict] = (), hotel_id: str | None = None) -> list[dict]:
    """Select distinct evidence-backed candidates for each feasible meal period."""
    timezone_name = _local_timezone(intent)
    zone = ZoneInfo(timezone_name)
    windows = {"breakfast": time(8, 0), "lunch": time(12, 30), "dinner": time(18, 30)}
    selected: dict[str, dict] = {}
    used: set[str] = set()
    for day_number in range(1, (end - start).days + 2):
        current_date = start + timedelta(days=day_number - 1)
        for period, start_time in windows.items():
            meal_start = datetime.combine(current_date, start_time, zone)
            meal_end = meal_start + timedelta(minutes=60)
            eligible = [candidate for candidate in eligible_restaurants(candidates, meal_start, meal_end)
                        if candidate.get("place", {}).get("id") not in used
                        and candidate.get("schedule", {}).get("duration_minutes", 60) > 0
                        and _meal_route_feasible(candidate, period, meal_start, meal_end, day_number, routing, places, hotel_id)]
            if not eligible:
                continue
            candidate = dict(eligible[(day_number + len(selected)) % len(eligible)])
            place_id = candidate.get("place", {}).get("id")
            if not isinstance(place_id, str):
                continue
            candidate["schedule"] = {
                "duration_minutes": 60, "day": day_number, "meal_period": period, "required": False,
                "fixed_start_at": meal_start.isoformat(), "fixed_end_at": meal_end.isoformat(),
                "selected": True,
                "alternatives": [{"place_id": item["place"]["id"], "meal_period": period, "day": day_number,
                                  "hours_verified": True, "route_verified": True}
                                 for item in eligible if item["place"]["id"] != place_id],
            }
            selected[place_id] = candidate
            used.add(place_id)
    result = []
    for candidate in candidates:
        place_id = candidate.get("place", {}).get("id")
        copied = dict(candidate)
        if place_id in selected:
            copied["schedule"] = selected[place_id]["schedule"]
        elif copied.get("schedule"):
            copied["schedule"] = {**copied["schedule"], "selected": False}
        result.append(copied)
    return result


def _meal_route_feasible(candidate: Mapping[str, object], period: str, starts: datetime, ends: datetime,
                         day_number: int, routing: ValidationContext | None, places: Sequence[dict], hotel_id: str | None) -> bool:
    if routing is None or hotel_id is None or day_number > len(places):
        return False
    place_id = candidate.get("place", {}).get("id")
    poi_id = places[day_number - 1].get("id")
    if not isinstance(place_id, str) or not isinstance(poi_id, str):
        return False
    if period == "breakfast":
        outbound = routing.travel_minutes.get((hotel_id, place_id))
        onward = routing.travel_minutes.get((place_id, poi_id))
        return outbound is not None and onward is not None and starts - timedelta(minutes=outbound) >= datetime.combine(starts.date(), time(7), starts.tzinfo) and ends + timedelta(minutes=onward) <= datetime.combine(starts.date(), time(10), starts.tzinfo)
    outbound = routing.travel_minutes.get((poi_id, place_id))
    returning = routing.travel_minutes.get((place_id, hotel_id))
    return outbound is not None and returning is not None and starts >= datetime.combine(starts.date(), time(12) if period == "lunch" else time(18), starts.tzinfo) and ends + timedelta(minutes=returning) <= datetime.combine(starts.date(), time(20), starts.tzinfo)


def _add_unfilled_meal_warnings(trip: dict) -> None:
    for day_number, day in enumerate(trip.get("days", []), start=1):
        day_meals = [item for item in day.get("items", []) if item.get("kind") == "meal"]
        if len(day_meals) < 3:
            trip.setdefault("validation", []).append({"code": "meal.period_unselected", "severity": "warning",
                "message": f"{day.get('date')} 有 {3-len(day_meals)} 個餐段未找到營業時間已驗證且路線可行的獨立餐廳；請選擇餐廳後再安排。", "path": f"/days/{day_number-1}"})


def _schedule_legacy_meals(trip: dict, candidates: Sequence[dict], routing: ValidationContext) -> None:
    """Append meals only where time, opening hours, and outbound/return routes are known."""
    by_id = {candidate.get("place", {}).get("id"): candidate for candidate in candidates}
    hotel_ids = trip.get("selected", {}).get("hotel_place_ids", [])
    hotel_id = hotel_ids[0] if len(hotel_ids) == 1 else None
    used: set[str] = set()
    for day_number, day in enumerate(trip.get("days", []), start=1):
        visit = next((item for item in day.get("items", []) if item.get("kind") == "visit"), None)
        if visit is None:
            continue
        visit_end = datetime.fromisoformat(visit["end_at"])
        zone = ZoneInfo(trip["local_timezone"])
        windows = (("breakfast", time(8, 0)), ("lunch", time(12, 30)), ("dinner", time(18, 30)))
        for period, target_time in windows:
            candidates_here = [candidate for candidate in candidates if candidate.get("place", {}).get("id") not in used
                               and candidate.get("opening_hours", {}).get("status") == "fresh"]
            candidates_here.sort(key=lambda candidate: (candidate.get("rating", 0), candidate.get("place", {}).get("id", "")), reverse=True)
            for candidate in candidates_here:
                place_id = candidate["place"]["id"]
                if period == "breakfast":
                    route_out = routing.travel_minutes.get((hotel_id, place_id)) if hotel_id else None
                    route_back = routing.travel_minutes.get((place_id, visit["place_id"]))
                else:
                    route_out = routing.travel_minutes.get((visit["place_id"], place_id))
                    route_back = routing.travel_minutes.get((place_id, hotel_id)) if hotel_id else None
                if route_out is None or route_back is None:
                    continue
                earliest = datetime.combine(date.fromisoformat(day["date"]), target_time, zone)
                if period == "breakfast":
                    earliest += timedelta(minutes=route_out)
                else:
                    earliest = max(earliest, visit_end + timedelta(minutes=route_out))
                if period == "breakfast" and earliest + timedelta(minutes=60 + route_back) > datetime.fromisoformat(visit["start_at"]):
                    continue
                meal_start = earliest
                meal_end = meal_start + timedelta(minutes=60)
                if meal_end.time() > time(20, 0) or meal_end + timedelta(minutes=route_back) > datetime.combine(date.fromisoformat(day["date"]), time(23, 0), zone):
                    continue
                if meal_eligibility(candidate, meal_start, meal_end).value != "eligible":
                    continue
                day["items"].append({"id": f"day{day_number}-{period}-{place_id}", "kind": "meal", "place_id": place_id, "start_at": meal_start.isoformat(), "end_at": meal_end.isoformat(), "selection_status": "selected"})
                candidate["schedule"] = {"duration_minutes": 60, "day": day_number, "meal_period": period, "required": False,
                                          "fixed_start_at": meal_start.isoformat(), "fixed_end_at": meal_end.isoformat()}
                used.add(place_id)
                break
        day["items"].sort(key=lambda item: item["start_at"])


def _legacy_trip(trip_id, intent, collections, canonical_places, start, end, selected_hotel, flights, days):
    currency = _budget_currency(intent, flights[0] if flights else None, selected_hotel)
    flight_cost = _money_amount(flights[0].get("cost"), currency) if flights else 0.0
    hotel_cost = _money_amount(selected_hotel.get("total_cost"), currency) if selected_hotel else 0.0
    categories = {"hotel": {"amount": hotel_cost, "currency": currency}}
    if selected_hotel is None:
        categories.pop("hotel")
    if flights:
        categories["flights"] = {"amount": flight_cost, "currency": currency}
    return {"schema_version": "trip-v1", "id": trip_id, "title": " + ".join(intent.destinations) + " 行程", "local_timezone": _local_timezone(intent), "date_range": {"start_date": start.isoformat(), "end_date": end.isoformat()}, "traveler_profile": {"adults": _adults(intent), "children": [{"age": age} for age in intent.travelers.child_ages]}, "preferences": {"hard_constraints": _canonical_hard_constraints(intent), "soft_preferences": []}, "candidate_sets": {**collections, "places": canonical_places}, "selected": {"hotel_place_ids": [selected_hotel["place"]["id"]] if selected_hotel else [], "flight_ids": [flight["id"] for flight in flights[:1]]}, "days": days, "budget": {"currency": currency, "categories": categories, "total": {"amount": flight_cost + hotel_cost, "currency": currency}, "total_status": "incomplete"}, "validation": [], "provenance": {"source_type": "derived", "provider": "production composition", "retrieved_at": datetime.now(timezone.utc).isoformat(), "status": "estimated", "note": _lodging_note(selected_hotel)}}


def _canonical_hard_constraints(intent: TravelIntent) -> list[dict]:
    constraints = []
    source = next(iter(intent.provenance.get("hard_constraints", ())), None)
    for constraint in intent.hard_constraints:
        if constraint.kind == "night_river_view":
            constraints.append({"id": constraint.id, "kind": constraint.kind,
                                "description": source.text if source else "晚上看得到河流與夜景",
                                "value": constraint.value})
    return constraints


def _lodging_note(selected_hotel: Mapping[str, object] | None) -> str:
    if selected_hotel is None:
        return "No lodging candidate meets the verified stay dates, party, total-budget, destination proximity (within 10 km of a researched destination place), and explicit lodging preferences; lodging remains unselected. No booking is created. The overall trip budget is incomplete because lodging, dining, or local transport costs remain unpriced."
    return "Selected hotel is a preferred search candidate only; candidates were compared by distance to researched destination places (within 10 km) and total price. No booking is created. Price and availability require provider confirmation. The overall trip budget is incomplete because dining and local transport costs are not priced."


def _select_hotel_candidate(hotels: Sequence[dict], intent: TravelIntent, check_in: date, check_out: date,
                            flights: Sequence[dict], destination_places: Sequence[dict]) -> dict | None:
    """Choose a documented lodging search candidate; never imply a booking."""
    expected_currency = intent.currency or _default_currency(intent)
    adults = _adults(intent)
    child_ages = list(intent.travelers.child_ages)
    preferences = tuple(intent.accommodation_preferences)
    flight_amount = 0.0
    if flights:
        flight_cost = flights[0].get("cost")
        if isinstance(flight_cost, Mapping) and flight_cost.get("currency") == expected_currency:
            amount = flight_cost.get("amount")
            if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                flight_amount = float(amount)
    remaining_budget = intent.budget_amount - flight_amount if intent.budget_amount is not None else None
    target_coordinates = [place.get("coordinates") for place in destination_places
                          if isinstance(place, Mapping) and isinstance(place.get("coordinates"), Mapping)]
    eligible = []
    for hotel in hotels:
        if hotel.get("check_in") != check_in.isoformat() or hotel.get("check_out") != check_out.isoformat():
            continue
        occupancy = hotel.get("occupancy")
        if not isinstance(occupancy, Mapping) or (
            occupancy.get("adults") != adults or occupancy.get("child_ages") != child_ages
            or occupancy.get("rooms") != (intent.room_count or 1)
        ):
            continue
        total = hotel.get("total_cost")
        if not isinstance(total, Mapping) or total.get("currency") != expected_currency:
            continue
        amount = total.get("amount")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 0:
            continue
        if remaining_budget is not None and amount > remaining_budget:
            continue
        place = hotel.get("place") if isinstance(hotel.get("place"), Mapping) else {}
        evidence = " ".join(str(value) for value in (
            place.get("name", ""),
            hotel.get("child_policy", ""), hotel.get("location_note", ""),
        )).casefold()
        preference_terms = {
            "ryokan": ("ryokan", "旅館", "溫泉"),
            "business_hotel": ("business", "商務"),
            "family_hotel": ("family", "親子"),
            "central": ("central", "downtown", "市中心"),
        }
        if any(not any(term.casefold() in evidence for term in preference_terms.get(preference, (preference.casefold(),))) for preference in preferences):
            continue
        requested_room_types = {
            "雙床房": ("twin", "雙床"), "單人房": ("single", "單人"),
            "雙人房": ("double", "雙人"), "家庭房": ("family", "家庭"), "套房": ("suite", "套房"),
        }
        requested_room = next((terms for label, terms in requested_room_types.items() if label in intent.raw_text), None)
        room_evidence = str(hotel.get("room_type", "")).casefold()
        if requested_room and not any(term.casefold() in room_evidence for term in requested_room):
            continue
        distance = _nearest_destination_distance_km(place.get("coordinates"), target_coordinates)
        if distance is None or distance > _MAX_HOTEL_DISTANCE_TO_DESTINATION_KM:
            continue
        eligible.append((distance, float(amount), hotel.get("cancellation_policy") in (None, ""), str(place.get("id", "")), hotel))
    return min(eligible, key=lambda item: item[:4])[4] if eligible else None


def _nearest_destination_distance_km(hotel_coordinates: object, target_coordinates: Sequence[object]) -> float | None:
    if not isinstance(hotel_coordinates, Mapping) or not target_coordinates:
        return None
    try:
        from math import asin, cos, radians, sin, sqrt
        latitude = float(hotel_coordinates["latitude"])
        longitude = float(hotel_coordinates["longitude"])
        distances = []
        for target in target_coordinates:
            if not isinstance(target, Mapping):
                continue
            target_latitude = float(target["latitude"])
            target_longitude = float(target["longitude"])
            delta_lat = radians(target_latitude - latitude)
            delta_lon = radians(target_longitude - longitude)
            a = sin(delta_lat / 2) ** 2 + cos(radians(latitude)) * cos(radians(target_latitude)) * sin(delta_lon / 2) ** 2
            distances.append(6371 * 2 * asin(sqrt(a)))
        return min(distances) if distances else None
    except (KeyError, TypeError, ValueError):
        return None


def _record_unknown_night_view_evidence(places: Sequence[dict], intent: TravelIntent) -> None:
    if not any(constraint.kind == "night_river_view" for constraint in intent.hard_constraints):
        return
    retrieved_at = datetime.now(ZoneInfo(_local_timezone(intent))).isoformat()
    provenance = {"source_type": "derived", "provider": "production composition",
                  "retrieved_at": retrieved_at, "status": "unverified",
                  "note": "Current place sources do not include viewpoint-specific night visibility evidence."}
    descriptions = {
        "observation_point": "觀景位置尚未由來源確認。",
        "river_visibility": "夜間河面可見性尚未由來源確認。",
        "obstructions": "觀景方向的樹木或其他遮蔽物尚未由來源確認。",
        "night_scene": "夜間照明或景觀尚未由來源確認。",
    }
    for place in places:
        if place.get("kind") != "poi" or "night_view_evidence" in place:
            continue
        place["night_view_evidence"] = {
            **{field: {"status": "unknown", "description": description, "provenance": provenance}
               for field, description in descriptions.items()},
            "access_point": {"status": "unknown", "description": "抵達入口尚未由來源確認。", "provenance": provenance},
            "retrieved_at": retrieved_at,
        }


def _routing_context(records: Iterable[object], routing_provider: object, intent: TravelIntent) -> ValidationContext:
    places = []
    restaurants = []
    opening_hours = {}
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
        hours = candidate.get("opening_hours")
        if record.collection == "places" and isinstance(hours, Mapping) and hours.get("status") == "fresh":
            try:
                opening_hours[place["id"]] = tuple(OpeningInterval(int(entry["weekday"]), time.fromisoformat(entry["opens_at"]), time.fromisoformat(entry["closes_at"])) for entry in hours["intervals"])
            except (KeyError, TypeError, ValueError):
                pass
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
    return ValidationContext(travel_minutes=minutes, opening_hours={**validation_opening_hours(restaurants), **opening_hours})


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
    origin = {"台灣": "TPE", "臺灣": "TPE", "台北": "TPE", "臺北": "TPE", "桃園": "TPE", "高雄": "KHH", "香港": "HKG", "東京": "NRT", "大阪": "KIX"}.get(intent.origin or "")
    destination = {"台灣": "TPE", "台北": "TPE", "臺北": "TPE", "萬華": "TPE", "西門町": "TPE", "德島": "TKS", "神戶": "UKB", "東京": "TYO", "大阪": "OSA", "京都": "OSA", "福岡": "FUK", "札幌": "SPK", "沖繩": "OKA", "名古屋": "NGO"}.get(intent.destinations[0] if intent.destinations else "")
    if not origin or not destination:
        raise ProductionIncompleteError("origin/destination lacks an explicit Amadeus airport/city-code mapping")
    return origin, destination


_TAIWAN_DESTINATIONS = {"台灣", "台北", "臺北", "萬華", "西門町", "西門"}
_JAPAN_DESTINATIONS = {
    "東京", "大阪", "京都", "神戶", "德島", "福岡", "札幌", "沖繩", "名古屋", "奈良",
    "熊本", "由布院", "北海道", "淡路島", "東京迪士尼", "環球影城",
    "關西", "關東", "九州", "四國",
}


def _destination_country(intent: TravelIntent) -> str:
    destinations = set(intent.destinations) | set(intent.regions)
    if destinations & _TAIWAN_DESTINATIONS:
        if destinations & _JAPAN_DESTINATIONS:
            raise ProductionIncompleteError("a trip spanning Taiwan and Japan needs an explicit destination split")
        return "TW"
    if destinations & _JAPAN_DESTINATIONS:
        return "JP"
    raise ProductionIncompleteError("destination is outside the supported Taiwan and Japan provider coverage")


def _origin_country(intent: TravelIntent) -> str | None:
    origin = intent.origin
    if origin in {"台灣", "臺灣", "台北", "臺北", "桃園", "高雄"}:
        return "TW"
    if origin == "香港":
        return "HK"
    if origin in {"東京", "大阪"}:
        return "JP"
    return None


def _requires_flight_search(intent: TravelIntent) -> bool:
    destination_country = _destination_country(intent)
    origin_country = _origin_country(intent)
    if origin_country is None:
        if intent.origin is not None:
            raise ProductionIncompleteError(f"flight search is not available for origin {intent.origin!r}")
        return destination_country == "JP"
    return origin_country != destination_country


def _research_categories(intent: TravelIntent) -> tuple[str, ...]:
    categories = ("pois", "restaurants", "hotels", "flights", "transport")
    if _requires_flight_search(intent):
        return categories
    return tuple(category for category in categories if category != "flights")


def _research_destination(intent: TravelIntent) -> str:
    destinations = tuple(intent.destinations)
    if _destination_country(intent) == "TW":
        specific = tuple(place for place in destinations if place not in {"台灣"})
        if specific:
            return "、".join(specific)
    return destinations[0] if destinations else (intent.regions[0] if intent.regions else "")


def _hotel_city_code(intent: TravelIntent) -> str:
    destination_country = _destination_country(intent)
    if destination_country == "TW":
        return "TPE"
    city_codes = {
        "德島": "TKS", "神戶": "UKB", "東京": "TYO", "大阪": "OSA", "京都": "OSA",
        "福岡": "FUK", "札幌": "SPK", "沖繩": "OKA", "名古屋": "NGO",
    }
    for place in intent.destinations:
        if place in city_codes:
            return city_codes[place]
    raise ProductionIncompleteError("hotel search is not available for this destination")


def _local_timezone(intent: TravelIntent) -> str:
    return "Asia/Taipei" if _destination_country(intent) == "TW" else "Asia/Tokyo"


def _default_currency(intent: TravelIntent) -> str:
    return "TWD" if _destination_country(intent) == "TW" else "JPY"


_SUPPORTED_AIRPORT_CODES = (
    "TPE", "KHH", "HKG", "NRT", "HND", "KIX", "ITM", "TYO", "OSA", "TKS", "UKB",
    "FUK", "SPK", "CTS", "OKA", "NGO",
)
_MAX_HOTEL_DISTANCE_TO_DESTINATION_KM = 10.0


def _airport_timezone(code: str) -> str:
    zones = {code: "Asia/Taipei" for code in ("TPE", "KHH")}
    zones["HKG"] = "Asia/Hong_Kong"
    zones.update({code: "Asia/Tokyo" for code in _SUPPORTED_AIRPORT_CODES if code not in zones and code != "HKG"})
    if code not in zones:
        raise ProductionIncompleteError(f"flight search returned an airport without a timezone mapping: {code}")
    return zones[code]


def _safe_trip_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")
    if not cleaned or not re.fullmatch(r"[a-z][a-z0-9_-]*", cleaned):
        raise ValueError("trip_id must start with a letter and use lowercase letters, digits, _ or -")
    return cleaned


def _budget_currency(intent: TravelIntent, flight: Mapping[str, object] | None, hotel: Mapping[str, object] | None) -> str:
    values = [flight.get("cost", {}) if flight else {}]
    if hotel:
        values.append(hotel.get("total_cost", {}))
    currencies = [value.get("currency") for value in values if isinstance(value, Mapping) and value.get("currency")]
    if len(set(currencies)) > 1:
        raise ProductionIncompleteError("flight and hotel provider currencies differ; no conversion rate was invented")
    currency = str(currencies[0]) if currencies else (intent.currency or _default_currency(intent))
    expected = intent.currency or _default_currency(intent)
    if currency != expected:
        raise ProductionIncompleteError("provider currency differs from the explicitly requested or destination currency")
    return currency


def _money_amount(value: object, currency: str) -> float:
    if not isinstance(value, Mapping) or value.get("currency") != currency or not isinstance(value.get("amount"), (int, float)):
        raise ProductionIncompleteError("provider price is missing or cannot be reconciled to the selected currency")
    return float(value["amount"])
