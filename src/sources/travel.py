"""Provider-neutral flight and hotel search boundary.

The adapters in this module use Amadeus Self-Service's documented search APIs,
but expose only canonical candidate data.  Credentials are read at request time
from the environment and raw provider payloads never leave this module.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .adapters import AdapterFailure


Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, dict[str, Any]]]


class ProviderError(RuntimeError):
    """An expected provider/authentication/response failure."""


@dataclass(frozen=True)
class Occupancy:
    adults: int
    child_ages: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.adults < 1:
            raise ValueError("occupancy requires at least one adult")
        if any(age < 0 or age > 17 for age in self.child_ages):
            raise ValueError("child ages must be between 0 and 17")

    @property
    def travelers(self) -> int:
        return self.adults + len(self.child_ages)


@dataclass(frozen=True)
class FlightSearchQuery:
    origin: str
    destination: str
    departure_date: date
    occupancy: Occupancy
    return_date: date | None = None
    non_stop: bool = False
    currency: str | None = None
    airport_timezones: dict[str, str] | None = None


@dataclass(frozen=True)
class HotelSearchQuery:
    city_code: str
    check_in_date: date
    check_out_date: date
    occupancy: Occupancy
    currency: str | None = None
    hotel_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.check_out_date <= self.check_in_date:
            raise ValueError("check_out_date must be after check_in_date")


@dataclass(frozen=True)
class SearchResult:
    candidates: tuple[tuple[str, dict[str, Any]], ...]
    failures: tuple[AdapterFailure, ...] = ()


class AmadeusClient:
    """Small injected-transport client; tests never use a live network."""

    BASE_URL = "https://test.api.amadeus.com"

    def __init__(self, transport: Transport | None = None, environment: dict[str, str] | None = None) -> None:
        self.transport = transport or _urllib_transport
        self.environment = environment if environment is not None else os.environ
        self._token: str | None = None

    def get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        token = self._access_token()
        status, payload = self.transport("GET", f"{self.BASE_URL}{path}?{urlencode(params)}", {"Authorization": f"Bearer {token}"}, None)
        if status >= 400:
            raise ProviderError(_provider_message(payload, status))
        return payload

    def _access_token(self) -> str:
        if self._token:
            return self._token
        client_id = self.environment.get("AMADEUS_CLIENT_ID")
        client_secret = self.environment.get("AMADEUS_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ProviderError("missing AMADEUS_CLIENT_ID or AMADEUS_CLIENT_SECRET")
        body = urlencode({"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}).encode()
        status, payload = self.transport("POST", f"{self.BASE_URL}/v1/security/oauth2/token", {"Content-Type": "application/x-www-form-urlencoded"}, body)
        if status >= 400 or not payload.get("access_token"):
            raise ProviderError(_provider_message(payload, status))
        self._token = str(payload["access_token"])
        return self._token


class AmadeusFlightAdapter:
    name = "amadeus-flight-offers"

    def __init__(self, client: AmadeusClient, retrieved_at: datetime | None = None) -> None:
        self.client, self.retrieved_at = client, retrieved_at

    def search(self, query: FlightSearchQuery) -> SearchResult:
        params = {"originLocationCode": query.origin, "destinationLocationCode": query.destination,
                  "departureDate": query.departure_date.isoformat(), "adults": str(query.occupancy.adults),
                  "max": "20", "nonStop": str(query.non_stop).lower()}
        if query.return_date: params["returnDate"] = query.return_date.isoformat()
        if query.currency: params["currencyCode"] = query.currency
        payload = self.client.get("/v2/shopping/flight-offers", params)
        now = self.retrieved_at or datetime.now(timezone.utc)
        candidates = tuple(("flights", _normalise_flight(offer, now, query)) for offer in payload.get("data", []))
        return SearchResult(candidates)


class AmadeusHotelAdapter:
    name = "amadeus-hotel-offers"

    def __init__(self, client: AmadeusClient, retrieved_at: datetime | None = None) -> None:
        self.client, self.retrieved_at = client, retrieved_at

    def search(self, query: HotelSearchQuery) -> SearchResult:
        hotel_ids = query.hotel_ids or tuple(str(item["hotelId"]) for item in self.client.get("/v1/reference-data/locations/hotels/by-city", {"cityCode": query.city_code}).get("data", []))
        if not hotel_ids:
            return SearchResult(())
        params = {"hotelIds": ",".join(hotel_ids), "checkInDate": query.check_in_date.isoformat(),
                  "checkOutDate": query.check_out_date.isoformat(), "adults": str(query.occupancy.adults),
                  "roomQuantity": "1"}
        if query.occupancy.child_ages: params["childAges"] = ",".join(map(str, query.occupancy.child_ages))
        if query.currency: params["currency"] = query.currency
        payload = self.client.get("/v3/shopping/hotel-offers", params)
        now = self.retrieved_at or datetime.now(timezone.utc)
        candidates = []
        for item in payload.get("data", []):
            for offer in item.get("offers", []):
                candidates.append(("hotels", _normalise_hotel(item.get("hotel", {}), offer, now, query)))
        return SearchResult(tuple(candidates))


def collect_travel_searches(searches: Iterable[Callable[[], SearchResult]]) -> SearchResult:
    """Run independent searches without losing candidates from a failed provider."""
    candidates: list[tuple[str, dict[str, Any]]] = []
    failures: list[AdapterFailure] = []
    for search in searches:
        try:
            result = search()
            candidates.extend(result.candidates)
            failures.extend(result.failures)
        except Exception as exc:
            failures.append(AdapterFailure(adapter=getattr(search, "__qualname__", "travel-provider"), message=str(exc)))
    return SearchResult(tuple(candidates), tuple(failures))


def _normalise_flight(offer: dict[str, Any], retrieved_at: datetime, query: FlightSearchQuery) -> dict[str, Any]:
    itinerary = offer["itineraries"][0]
    segments = itinerary["segments"]
    first, last = segments[0], segments[-1]
    departure = _timestamp(first["departure"]["at"], first["departure"]["iataCode"], query.airport_timezones)
    arrival = _timestamp(last["arrival"]["at"], last["arrival"]["iataCode"], query.airport_timezones)
    price = offer["price"]
    fare = (offer.get("travelerPricings") or [{}])[0].get("fareDetailsBySegment", [{}])[0]
    ident = str(offer.get("id", f"{first['carrierCode']}{first['number']}-{departure}"))
    candidate = {"id": f"amadeus-flight-{ident}", "carrier": first["carrierCode"], "flight_number": f"{first['carrierCode']}{first['number']}",
            "departure": {"place_id": first["departure"]["iataCode"].lower(), "at": departure}, "arrival": {"place_id": last["arrival"]["iataCode"].lower(), "at": arrival},
            "cost": _money(price["grandTotal"], price["currency"]), "direct": len(segments) == 1, "transfer_count": len(segments) - 1,
            "fare_family": fare.get("brandedFare"), "baggage": fare.get("includedCheckedBags"), "provider_reference": str(offer.get("id", "")),
            "search_url": "https://www.amadeus.com/en/booking", "price_status": "unverified", "provenance": _provenance(retrieved_at)}
    return {key: value for key, value in candidate.items() if value is not None}


def _normalise_hotel(hotel: dict[str, Any], offer: dict[str, Any], retrieved_at: datetime, query: HotelSearchQuery) -> dict[str, Any]:
    price = offer["price"]
    total = _money(price["total"], price["currency"])
    taxes = sum(float(item.get("amount", 0)) for item in price.get("taxes", []))
    policy = offer.get("policies", {})
    hid = str(hotel.get("hotelId", offer.get("id")))
    place: dict[str, Any] = {"id": f"amadeus-hotel-{hid}", "name": hotel.get("name", hid), "kind": "hotel"}
    if hotel.get("latitude") is not None and hotel.get("longitude") is not None:
        place["coordinates"] = {"latitude": float(hotel["latitude"]), "longitude": float(hotel["longitude"])}
    candidate = {"place": place, "nightly_cost": _money(float(total["amount"]) / (query.check_out_date - query.check_in_date).days, total["currency"]),
            "total_cost": total, "taxes_fees": _money(taxes, total["currency"]), "check_in": query.check_in_date.isoformat(), "check_out": query.check_out_date.isoformat(),
            "occupancy": {"adults": query.occupancy.adults, "child_ages": list(query.occupancy.child_ages)}, "room_type": offer.get("room", {}).get("typeEstimated", {}).get("category"),
            "cancellation_policy": policy.get("cancellations", [{}])[0].get("description", {}).get("text"), "parking_available": None,
            "child_policy": None, "provider_reference": str(offer.get("id", "")), "search_url": "https://www.amadeus.com/en/booking", "price_status": "unverified", "provenance": _provenance(retrieved_at)}
    return {key: value for key, value in candidate.items() if value is not None}


def _money(amount: Any, currency: str) -> dict[str, Any]: return {"amount": float(amount), "currency": currency.upper()}
def _provenance(retrieved_at: datetime) -> dict[str, Any]: return {"source_type": "provider", "provider": "Amadeus Self-Service API", "source_url": "https://developers.amadeus.com/", "retrieved_at": retrieved_at.isoformat(), "status": "unverified", "note": "Search price only; availability and final price require provider confirmation."}
def _timestamp(value: str, airport: str, zones: dict[str, str] | None) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        zone = (zones or {}).get(airport)
        if not zone: raise ProviderError(f"missing timezone for airport {airport}")
        parsed = parsed.replace(tzinfo=ZoneInfo(zone))
    return parsed.isoformat()
def _provider_message(payload: dict[str, Any], status: int) -> str: return str(payload.get("errors", payload.get("error_description", f"provider HTTP {status}")))
def _urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, dict[str, Any]]:
    try:
        with urlopen(Request(url, data=body, headers=headers, method=method), timeout=20) as response:
            return response.status, json.loads(response.read())
    except Exception as exc: raise ProviderError(str(exc)) from exc
