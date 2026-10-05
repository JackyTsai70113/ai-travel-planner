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
    AdapterFailure, AmadeusClient, AmadeusHotelAdapter,
    GooglePlacesAdapter, HotPepperGourmetAdapter, HotelSearchQuery, Occupancy, SourceAdapter, SourceQuery,
    YouTubeEvidenceAdapter, collect_from_adapters,
)
from src.sources.routing import OpenRouteServiceProvider, PlaceRef, RouteMatrix, RouteMode, RouteStatus
from src.validator import OpeningInterval, ValidationContext


REQUIRED_ENVIRONMENT = (
    "GOOGLE_MAPS_API_KEY",
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

    def __init__(self, intent: TravelIntent, google: SourceAdapter, youtube: YouTubeEvidenceAdapter | None,
                 hotel_client: AmadeusClient | None, optional_restaurants: Sequence[SourceAdapter] = ()) -> None:
        self.intent, self.google, self.youtube = intent, google, youtube
        self.optional_restaurants = tuple(optional_restaurants)
        self.hotel_search = AmadeusHotelAdapter(hotel_client) if hotel_client else None
        self.evidence: list[object] = []
        self.failures: list[AdapterFailure] = []
        self.optional_failures: list[AdapterFailure] = []

    def fetch(self, query: SourceQuery):
        self.failures = []
        self.optional_failures = []
        query = replace(query, destination=_research_destination(self.intent))
        # Evidence is deliberately not converted into an operational candidate.
        self.evidence = []
        if self.youtube is not None:
            try:
                self.evidence = list(self.youtube.fetch_evidence(query))
            except Exception as exc:
                failure = AdapterFailure(
                    adapter=str(getattr(self.youtube, "name", type(self.youtube).__name__)),
                    message=str(exc),
                    optional=True,
                )
                self.optional_failures.append(failure)
        else:
            self.optional_failures.append(AdapterFailure(
                adapter="youtube-data",
                message="YOUTUBE_API_KEY is not configured; optional community evidence is unavailable",
                optional=True,
            ))
        candidates, failures = collect_from_adapters((self.google, *self.optional_restaurants), query)
        self.failures.extend(failures)
        start, end = _travel_dates(self.intent)
        occupancy = Occupancy(_adults(self.intent), self.intent.travelers.child_ages)
        currency = self.intent.currency or _default_currency(self.intent)
        if self.hotel_search is not None:
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
        else:
            self.failures.append(AdapterFailure("hotel-search", "hotel search is unavailable: Amadeus Self-Service was retired; no replacement provider is configured"))
        restaurants = reconcile_restaurant_candidates(candidate for collection, candidate in candidates if collection == "restaurants")
        candidates = [(collection, candidate) for collection, candidate in candidates if collection != "restaurants"]
        candidates.extend(("restaurants", candidate) for candidate in restaurants)
        return candidates

    def drain_failures(self) -> tuple[AdapterFailure, ...]:
        failures = tuple(self.failures)
        optional_failures = tuple(self.optional_failures)
        self.failures.clear()
        self.optional_failures.clear()
        return (*failures, *optional_failures)


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
    youtube = dependencies.youtube
    if youtube is None and environment.get("YOUTUBE_API_KEY"):
        youtube = YouTubeEvidenceAdapter(api_key=environment["YOUTUBE_API_KEY"])
    hotel_client = dependencies.amadeus_client
    if hotel_client is None and environment.get("AMADEUS_CLIENT_ID") and environment.get("AMADEUS_CLIENT_SECRET"):
        hotel_client = AmadeusClient(environment=dict(environment))
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
        google=google, youtube=youtube, hotel_client=hotel_client, routing_provider=routing_provider,
        optional_restaurants=tuple(optional_restaurants),
        progress_callback=progress_callback,
    )
    return runner


class _IntentBoundRunner(ProductionPlanningRunner):
    def __init__(self, *, trip_id: str, trips_directory: Path, site_directory: Path,
                 google: SourceAdapter, youtube: YouTubeEvidenceAdapter | None, hotel_client: AmadeusClient | None,
                 routing_provider: object, progress_callback: Callable[[str], None] | None,
                 optional_restaurants: Sequence[SourceAdapter] = ()) -> None:
        self.trip_id, self.trips_directory, self.site_directory = _safe_trip_id(trip_id), trips_directory, site_directory
        self.google, self.youtube, self.hotel_client = google, youtube, hotel_client
        self.optional_restaurants = tuple(optional_restaurants)
        self.routing_provider, self.progress_callback = routing_provider, progress_callback

    def run(self, intent: TravelIntent) -> OrchestrationResult:
        _require_plannable_intent(intent)
        research = _ProductionResearchAdapter(intent, self.google, self.youtube, self.hotel_client, self.optional_restaurants)
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
    if len(places) < days_count:
        raise ProductionIncompleteError("live provider results are insufficient for a complete trip (need POIs)")
    selected_hotel = _select_hotel_candidate(hotels, intent, start, end, flights, collections["places"])
    hotel_id = selected_hotel["place"]["id"] if selected_hotel else None
    _assign_route_aware_poi_schedule(
        places, days_count, start, _local_timezone(intent), hotel_id, routing,
        low_fatigue=intent.pace == "relaxed" or any(preference.kind == "low_fatigue" for preference in intent.soft_preferences),
    )
    restaurants = _restaurant_candidates(restaurants, intent, start, end, routing, places, hotel_id)

    all_places = [*collections["places"], *(hotel["place"] for hotel in hotels), *(restaurant["place"] for restaurant in restaurants)]
    seen: set[str] = set()
    canonical_places = []
    for place in all_places:
        if place["id"] not in seen:
            seen.add(place["id"]); canonical_places.append(place)
    _record_unknown_night_view_evidence(canonical_places, intent)

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
        "flight_search_url": _google_flights_search_url(intent, start, end),
        "flight_search_summary": _google_flights_search_summary(intent, start, end),
        "local_timezone": _local_timezone(intent), "date_range": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "traveler_profile": {"adults": _adults(intent), "children": [{"age": age} for age in intent.travelers.child_ages]},
        "preferences": {"hard_constraints": _canonical_hard_constraints(intent), "soft_preferences": []},
        "candidate_sets": {**collections, "places": canonical_places},
        "selected": {"hotel_place_ids": [selected_hotel["place"]["id"]] if selected_hotel else [], "flight_ids": [flight["id"] for flight in flights[:1]]},
        "days": [],
        "budget": _canonical_budget(intent, currency, categories, flight_cost + hotel_cost),
        "validation": [],
        "provenance": {"source_type": "derived", "provider": "production composition", "retrieved_at": datetime.now(timezone.utc).isoformat(), "status": "estimated", "note": _lodging_note(selected_hotel)},
    }
    shell["candidate_sets"]["restaurants"] = restaurants
    schedule_output = schedule(SchedulingInput(shell, routing, daily_start="07:00"))
    scheduled = schedule_output.best_trip
    if scheduled is None:
        reasons = [violation.message for candidate in schedule_output.candidates for violation in candidate.violations]
        detail = "; ".join(dict.fromkeys(reasons))
        raise ProductionIncompleteError(
            "no feasible route-aware schedule from normalized candidates; "
            + (detail or "verified opening hours, visit durations, and directed routes are required")
        )
    if scheduled.state.value != "ready":
        raise ProductionIncompleteError("route-aware schedule is partial because required hotel or route facts are unavailable")
    scheduled.trip["validation"].extend(
        {"code": finding.code, "severity": finding.severity, "message": finding.message, "path": finding.path}
        for finding in scheduled.violations
        if finding.severity != "error"
    )
    _add_unselected_poi_warnings(scheduled.trip, places)
    _add_unfilled_meal_warnings(scheduled.trip)
    return [scheduled.trip]


def _assign_route_aware_poi_schedule(
    places: Sequence[dict], days_count: int, start: date, timezone_name: str,
    hotel_id: str | None, routing: ValidationContext, *, low_fatigue: bool = False,
) -> None:
    """Assign two POIs per day only when verified hours and directed routes fit.

    Visit lengths are explicit planning estimates, never provider or opening-hour
    facts. A missing provider schedule receives a labeled estimate; missing
    hours or routes remain unavailable and can make the result incomplete.
    """
    if hotel_id is None:
        raise ProductionIncompleteError("route-aware daily scheduling requires a selected lodging candidate to verify each day's outbound and return routes")
    eligible: list[dict] = []
    unavailable: list[str] = []
    selected_ids: set[str] = set()
    anchored_days: set[int] = set()
    anchor_counts: dict[int, int] = {}
    for place in places:
        details = place.get("schedule")
        if not isinstance(details, dict):
            details = {}
        if not isinstance(details.get("duration_minutes"), int) or details["duration_minutes"] <= 0:
            details.update({
                "duration_minutes": _estimated_visit_duration(place),
                "duration_basis": "planning_estimate",
            })
        else:
            details.setdefault("duration_basis", "planning_estimate")
        place["schedule"] = details
        anchor_fields = {"day", "fixed_start_at", "fixed_end_at"} & details.keys()
        if anchor_fields:
            if not {"day", "fixed_start_at", "fixed_end_at"} <= details.keys():
                raise ProductionIncompleteError(f"fixed visit anchor for {place.get('name', place['id'])} requires day, start, and end values")
            if not isinstance(details["day"], int) or not 1 <= details["day"] <= days_count:
                raise ProductionIncompleteError(f"fixed visit anchor for {place.get('name', place['id'])} has a day outside this trip")
            details.update({"selected": True, "required": True})
            selected_ids.add(place["id"])
            anchored_days.add(details["day"])
            anchor_counts[details["day"]] = anchor_counts.get(details["day"], 0) + 1
        else:
            details["selected"] = False
        hours = routing.opening_hours.get(place["id"])
        if not hours:
            unavailable.append(f"{place.get('name', place['id'])}: missing verified opening hours")
            continue
        eligible.append(place)

    zone = ZoneInfo(timezone_name)
    failures = [
        (start + timedelta(days=day_number - 1)).isoformat()
        for day_number, count in anchor_counts.items() if count < 2
    ]
    free_days = [day for day in range(1, days_count + 1) if day not in anchored_days]
    available_ids = {place["id"] for place in eligible} - selected_ids
    if len(available_ids) < len(free_days) * 2:
        failures.extend((start + timedelta(days=day - 1)).isoformat() for day in free_days)
    options_by_day: dict[int, list[tuple[int, float, int, int, datetime, datetime]]] = {}
    for day_number in range(1, days_count + 1):
        if day_number in anchored_days:
            continue
        current = start + timedelta(days=day_number - 1)
        options: list[tuple[int, float, int, int, datetime, datetime]] = []
        day_start = datetime.combine(current, time(9, 0), zone)
        day_end = datetime.combine(current, time(20, 0), zone)
        for first_index, first in enumerate(eligible):
            if first["id"] in selected_ids:
                continue
            out_minutes = routing.travel_minutes.get((hotel_id, first["id"]))
            if out_minutes is None or routing.travel_minutes.get((first["id"], hotel_id)) is None:
                continue
            first_details = first["schedule"]
            first_duration = first_details["duration_minutes"]
            first_buffer = first_details.get("parking_buffer_minutes", 0) + first_details.get("walking_buffer_minutes", 0)
            for first_interval in routing.opening_hours.get(first["id"], ()):
                if (type(first_interval.weekday) is not int or first_interval.weekday not in range(7)
                        or type(first_interval.closes_day_offset) is not int or first_interval.closes_day_offset not in (0, 1)
                        or not isinstance(first_interval.opens_at, time) or not isinstance(first_interval.closes_at, time)
                        or first_interval.weekday != current.weekday()):
                    continue
                first_open = datetime.combine(current, first_interval.opens_at, zone)
                first_close = datetime.combine(current + timedelta(days=first_interval.closes_day_offset), first_interval.closes_at, zone)
                first_start = max(day_start + timedelta(minutes=out_minutes + first_buffer), first_open)
                first_end = first_start + timedelta(minutes=first_duration)
                if first_end > first_close:
                    continue
                for second_index, second in enumerate(eligible):
                    if second["id"] in selected_ids or second_index == first_index:
                        continue
                    between = routing.travel_minutes.get((first["id"], second["id"]))
                    return_second = routing.travel_minutes.get((second["id"], hotel_id))
                    if between is None or return_second is None:
                        continue
                    second_details = second["schedule"]
                    second_duration = second_details["duration_minutes"]
                    second_buffer = second_details.get("parking_buffer_minutes", 0) + second_details.get("walking_buffer_minutes", 0)
                    for second_interval in routing.opening_hours.get(second["id"], ()):
                        if (type(second_interval.weekday) is not int or second_interval.weekday not in range(7)
                                or type(second_interval.closes_day_offset) is not int or second_interval.closes_day_offset not in (0, 1)
                                or not isinstance(second_interval.opens_at, time) or not isinstance(second_interval.closes_at, time)
                                or second_interval.weekday != current.weekday()):
                            continue
                        second_open = datetime.combine(current, second_interval.opens_at, zone)
                        second_close = datetime.combine(current + timedelta(days=second_interval.closes_day_offset), second_interval.closes_at, zone)
                        # Keep a protected midday break so the shared scheduler can
                        # place a verified lunch candidate without overlapping visits.
                        second_start = max(first_end + timedelta(minutes=between + second_buffer), second_open,
                                           datetime.combine(current, time(14, 0), zone))
                        second_end = second_start + timedelta(minutes=second_duration)
                        if second_end <= second_close and second_end + timedelta(minutes=return_second) <= day_end:
                            route_minutes = out_minutes + between + return_second
                            fatigue = float(first_details.get("fatigue", 0)) + float(second_details.get("fatigue", 0))
                            options.append((route_minutes, fatigue, first_index, second_index, first_start, second_start))
        if not options:
            failures.append((start + timedelta(days=day_number - 1)).isoformat())
        options_by_day[day_number] = sorted(
            options, key=lambda item: (item[1] if low_fatigue else 0, item[0], item[2], item[3])
        )

    # Schedule the most constrained dates first, with backtracking so a common
    # POI cannot consume the only candidates that fit a later weekday.
    ordered_days = sorted(options_by_day, key=lambda day: (len(options_by_day[day]), day))
    assignment: dict[int, tuple[int, float, int, int, datetime, datetime]] = {}
    searched_states: set[tuple[int, frozenset[str]]] = set()

    def assign_day(index: int, used_ids: set[str]) -> bool:
        state = (index, frozenset(used_ids))
        if state in searched_states:
            return False
        searched_states.add(state)
        if index == len(ordered_days):
            return True
        day_number = ordered_days[index]
        for option in options_by_day[day_number]:
            first_id = eligible[option[2]]["id"]
            second_id = eligible[option[3]]["id"]
            if first_id in used_ids or second_id in used_ids:
                continue
            assignment[day_number] = option
            if assign_day(index + 1, used_ids | {first_id, second_id}):
                return True
            assignment.pop(day_number, None)
        return False

    if not failures and not assign_day(0, set(selected_ids)):
        failures.extend((start + timedelta(days=day_number - 1)).isoformat() for day_number in ordered_days)

    if not failures:
        for day_number, option in assignment.items():
            _, _, first_index, second_index, first_start, second_start = option
            for place, slot in ((eligible[first_index], first_start), (eligible[second_index], second_start)):
                place["schedule"].update({
                    "day": day_number, "selected": True, "required": True,
                    "fixed_start_at": slot.isoformat(),
                    "fixed_end_at": (slot + timedelta(minutes=place["schedule"]["duration_minutes"])).isoformat(),
                })
                selected_ids.add(place["id"])

    if failures:
        missing = "; ".join(unavailable[:5]) or "verified outbound, inter-POI, return routes and opening intervals"
        raise ProductionIncompleteError(
            f"route-aware scheduling requires two feasible POIs per day; no feasible assignment for {', '.join(failures)}. Missing facts include: {missing}"
        )


def _estimated_visit_duration(place: Mapping[str, object]) -> int:
    """Return a labeled planning estimate, not a claim about actual dwell time."""
    primary_type = str(place.get("primary_type", "")).casefold()
    if any(term in primary_type for term in ("amusement_park", "theme_park", "zoo", "aquarium")):
        return 150
    if any(term in primary_type for term in ("museum", "art_gallery", "botanical_garden")):
        return 120
    return 90


def _add_unselected_poi_warnings(trip: dict, places: Sequence[dict]) -> None:
    for place in places:
        if place.get("schedule", {}).get("selected") is True:
            continue
        if not any(item.get("place_id") == place.get("id") for day in trip.get("days", []) for item in day.get("items", [])):
            trip.setdefault("validation", []).append({
                "code": "schedule.poi_candidate_unselected", "severity": "warning",
                "message": f"候選景點「{place.get('name', place.get('id', ''))}」未排入：未能驗證所需的營業時間或路線。",
                "path": f"/candidate_sets/places/{place.get('id', '')}/schedule",
            })


def _restaurant_candidates(candidates: Sequence[dict], intent: TravelIntent, start: date, end: date,
                           routing: ValidationContext | None = None, places: Sequence[dict] = (), hotel_id: str | None = None) -> list[dict]:
    """Select distinct evidence-backed candidates for each feasible meal period."""
    timezone_name = _local_timezone(intent)
    zone = ZoneInfo(timezone_name)
    windows = {"breakfast": time(8, 0), "lunch": time(12, 30), "dinner": time(18, 30)}
    selected: dict[str, dict] = {}
    used: set[str] = set()
    meal_slots: list[tuple[str, list[dict], str, int, datetime]] = []
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
                "alternatives": [],
            }
            selected[place_id] = candidate
            used.add(place_id)
            meal_slots.append((place_id, eligible, period, day_number, meal_start))
    reserved_alternatives: set[str] = set()
    for place_id, eligible, period, day_number, meal_start in meal_slots:
        backup = next((item for item in eligible
                       if item.get("place", {}).get("id") not in used | reserved_alternatives), None)
        if backup is None:
            continue
        backup_id = backup["place"]["id"]
        selected[place_id]["schedule"]["alternatives"] = [{
            "place_id": backup_id, "meal_period": period, "day": day_number,
            "hours_verified": True, "route_verified": True,
        }]
        reserved_alternatives.add(backup_id)
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
    if routing is None or hotel_id is None:
        return False
    place_id = candidate.get("place", {}).get("id")
    if not isinstance(place_id, str):
        return False

    scheduled: list[tuple[datetime, datetime, str, dict]] = []
    for place in places:
        details = place.get("schedule")
        if not isinstance(details, Mapping) or details.get("day") != day_number or details.get("selected") is not True:
            continue
        try:
            visit_start = datetime.fromisoformat(details["fixed_start_at"])
            visit_end = datetime.fromisoformat(details["fixed_end_at"])
        except (KeyError, TypeError, ValueError):
            return False
        scheduled.append((visit_start, visit_end, place["id"], details))

    if scheduled:
        scheduled.sort(key=lambda item: item[0])
        before = [item for item in scheduled if item[1] <= starts]
        after = [item for item in scheduled if item[0] >= ends]
        if before:
            _, previous_end, previous_id, _ = before[-1]
        else:
            previous_id, previous_end = hotel_id, datetime.combine(starts.date(), time(7), starts.tzinfo)
        if after:
            next_start, _, next_id, next_details = after[0]
            next_buffer = next_details.get("parking_buffer_minutes", 0) + next_details.get("walking_buffer_minutes", 0)
        else:
            next_id, next_start, next_buffer = hotel_id, datetime.combine(starts.date(), time(20), starts.tzinfo), 0
        incoming = routing.travel_minutes.get((previous_id, place_id))
        outgoing = routing.travel_minutes.get((place_id, next_id))
        if incoming is None or outgoing is None:
            return False
        if starts - timedelta(minutes=incoming) < previous_end:
            return False
        return ends + timedelta(minutes=outgoing + next_buffer) <= next_start

    # Compatibility for callers that evaluate meal candidates before assigning
    # POI dates; production passes a route-aware scheduled POI set above.
    if day_number > len(places):
        return False
    poi_id = places[day_number - 1].get("id")
    if not isinstance(poi_id, str):
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


def _canonical_budget(intent: TravelIntent, currency: str, categories: Mapping[str, object], known_total: float) -> dict:
    """Keep user ceiling intent separate from how much trip cost is priced."""
    status = intent.budget_status if intent.budget_status in {"unspecified", "unlimited", "limited"} else "unspecified"
    budget = {
        "currency": currency,
        "categories": dict(categories),
        "total": {"amount": known_total, "currency": currency},
        "total_status": "incomplete",
        "limit_status": status,
    }
    if status == "limited" and intent.budget_amount is not None:
        budget["limit"] = {"amount": intent.budget_amount, "currency": intent.currency or currency}
    return budget


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
    poi_places = []
    hotel_places = []
    restaurants = []
    hotel_candidates = []
    destination_candidates = []
    flight_candidates = []
    opening_hours = {}
    for record in records:
        candidate = record.candidate
        if record.collection == "restaurants":
            restaurants.append(candidate); place = candidate["place"]
        elif record.collection == "places":
            destination_candidates.append(candidate)
            place = candidate
            if place.get("kind") == "poi":
                poi_places.append(place)
        elif record.collection == "hotels":
            hotel_candidates.append(candidate)
            place = candidate["place"]
            hotel_places.append(place)
        elif record.collection == "flights":
            flight_candidates.append(candidate)
            continue
        else:
            continue
        coordinates = place.get("coordinates", {})
        if isinstance(coordinates, Mapping) and isinstance(coordinates.get("latitude"), (int, float)) and isinstance(coordinates.get("longitude"), (int, float)):
            ref = PlaceRef(place["id"], coordinates["latitude"], coordinates["longitude"])
            if record.collection == "hotels":
                hotel_places[-1] = {**place, "_route_ref": ref}
            elif record.collection == "places" and place.get("kind") == "poi":
                poi_places[-1] = {**place, "_route_ref": ref}
            elif record.collection == "restaurants":
                restaurants[-1] = {**candidate, "_route_ref": ref}
        hours = candidate.get("opening_hours")
        if record.collection in {"places", "restaurants"} and isinstance(hours, Mapping) and hours.get("status") == "fresh":
            try:
                parsed = []
                for entry in hours["intervals"]:
                    weekday = entry["weekday"]
                    close_offset = entry.get("closes_day_offset", 0)
                    if (type(weekday) is not int or weekday not in range(7)
                            or type(close_offset) is not int or close_offset not in (0, 1)):
                        raise ValueError("opening interval weekday or close offset is invalid")
                    parsed.append(OpeningInterval(
                        weekday, time.fromisoformat(entry["opens_at"]),
                        time.fromisoformat(entry["closes_at"]), close_offset,
                    ))
                opening_hours[place["id"]] = tuple(parsed)
            except (KeyError, TypeError, ValueError):
                pass
    start, end = _travel_dates(intent)
    selected_hotel = _select_hotel_candidate(
        hotel_candidates, intent, start, end, flight_candidates, destination_candidates
    ) if hotel_candidates else None
    selected_hotel_id = selected_hotel.get("place", {}).get("id") if selected_hotel else None
    selected_hotel_ref = next((place.get("_route_ref") for place in hotel_places if place.get("id") == selected_hotel_id), None)
    poi_limit = min(40, max(2, ((end - start).days + 1) * 4))
    ordered_refs = ([selected_hotel_ref] if selected_hotel_ref is not None else [])
    ordered_refs.extend(place["_route_ref"] for place in poi_places if "_route_ref" in place and place.get("_route_ref") is not None)
    ordered_refs = ordered_refs[:1] + ordered_refs[1:1 + poi_limit]
    ordered_refs.extend(
        candidate["_route_ref"] for candidate in restaurants
        if "_route_ref" in candidate and candidate.get("_route_ref") is not None
    )
    unique = list({place.place_id: place for place in ordered_refs[:50]}.values())
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


def _google_flights_search_url(intent: TravelIntent, start: date, end: date) -> str:
    del intent, start, end
    return "https://www.google.com/travel/flights?hl=zh-TW"


def _google_flights_search_summary(intent: TravelIntent, start: date, end: date) -> str:
    origin = intent.origin or "出發地未指定"
    destination = "、".join(intent.destinations) or "目的地未指定"
    return f"{origin} → {destination}；{start.isoformat()} 至 {end.isoformat()}"

_TAIWAN_DESTINATIONS = {"台灣", "台北", "臺北", "萬華", "西門町", "西門"}
_JAPAN_DESTINATIONS = {
    "東京", "大阪", "京都", "神戶", "德島", "福岡", "札幌", "沖繩", "名古屋", "奈良",
    "熊本", "由布院", "北海道", "淡路島", "東京迪士尼", "環球影城", "倉敷", "岡山", "岡山縣",
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


def _research_categories(intent: TravelIntent) -> tuple[str, ...]:
    return ("pois", "restaurants", "hotels", "transport")


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


_MAX_HOTEL_DISTANCE_TO_DESTINATION_KM = 10.0

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
