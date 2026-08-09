"""Production HTTP adapters for Japan-first place and travel research.

Only documented provider APIs are used here.  Provider payloads stop at this
module; callers receive the existing candidate-store contract or evidence
records.  ``http_client`` injection keeps CI fully offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any, Iterable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .adapters import SourceAdapter, SourceQuery


class ProviderConfigurationError(RuntimeError):
    """A required credential or provider configuration is absent."""


class ProviderRequestError(RuntimeError):
    """A documented provider API could not complete a request."""


class JsonHttpClient(Protocol):
    def request_json(
        self, method: str, url: str, *, headers: Mapping[str, str], body: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]: ...


class UrllibJsonHttpClient:
    """Small dependency-free JSON client with bounded request timeouts."""

    def __init__(self, timeout_seconds: float = 10) -> None:
        self.timeout_seconds = timeout_seconds

    def request_json(self, method: str, url: str, *, headers: Mapping[str, str], body: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(url, data=data, method=method, headers={**headers, "Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderRequestError(str(exc)) from exc
        if not isinstance(decoded, dict):
            raise ProviderRequestError("provider response must be a JSON object")
        return decoded


@dataclass(frozen=True)
class ResearchEvidence:
    """Non-decisive travel evidence; it cannot overwrite operational facts."""

    subject: str
    summary: str
    provenance: dict[str, Any]
    signals: tuple[str, ...] = ()


def authority_rank(provenance: Mapping[str, Any]) -> int:
    """Rank evidence without silently merging or overwriting independent facts."""

    return {"official": 0, "provider": 1, "community": 2, "derived": 3, "user_input": 4}.get(
        str(provenance.get("source_type")), 99
    )


def prioritize_by_authority(candidates: Iterable[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    """Return stable authority order; all source records remain present."""

    return sorted(candidates, key=lambda item: authority_rank(_provenance(item[1])))


class GooglePlacesAdapter(SourceAdapter):
    """Google Places API (New) text search adapter for POI and restaurants.

    The adapter requests only normalized discovery and restaurant-operational
    facts; Google raw payloads never leave this boundary.
    """

    name = "google-places"
    endpoint = "https://places.googleapis.com/v1/places:searchText"

    def __init__(
        self, api_key: str | None = None, *, http_client: JsonHttpClient | None = None, now: datetime | None = None
    ) -> None:
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY")
        self.http_client = http_client or UrllibJsonHttpClient()
        self.now = now

    def fetch(self, query: SourceQuery) -> Iterable[tuple[str, dict[str, Any]]]:
        if not self.api_key:
            raise ProviderConfigurationError("GOOGLE_MAPS_API_KEY is required for Google Places")
        result: list[tuple[str, dict[str, Any]]] = []
        for category, text in (("pois", "tourist attractions"), ("restaurants", "restaurants")):
            if category not in query.categories:
                continue
            payload = self.http_client.request_json(
                "POST", self.endpoint,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.googleMapsUri,places.regularOpeningHours,places.websiteUri,places.rating,places.userRatingCount,places.primaryType",
                },
                body={"textQuery": f"{text} in {query.destination}", "languageCode": "ja"},
            )
            for place in result_or_empty(payload, "places"):
                candidate = self._candidate(place, restaurant=(category == "restaurants"))
                if candidate is not None:
                    result.append(("restaurants" if category == "restaurants" else "places", candidate))
        return result

    def _candidate(self, raw: Mapping[str, Any], *, restaurant: bool) -> dict[str, Any] | None:
        place_id = raw.get("id")
        display_name = raw.get("displayName")
        if not isinstance(place_id, str) or not isinstance(display_name, Mapping) or not isinstance(display_name.get("text"), str):
            return None
        retrieved_at = (self.now or datetime.now(timezone.utc)).isoformat()
        provenance = {
            "source_type": "provider", "provider": "Google Places API (New)",
            "source_url": raw.get("googleMapsUri") or raw.get("websiteUri") or f"https://www.google.com/maps/place/?q=place_id:{place_id}",
            "retrieved_at": retrieved_at, "status": "confirmed", "confidence": 0.85,
        }
        candidate: dict[str, Any] = {"id": f"google-{place_id}", "name": display_name["text"], "kind": "restaurant" if restaurant else "poi", "provenance": provenance}
        if isinstance(raw.get("formattedAddress"), str):
            candidate["address"] = raw["formattedAddress"]
        location = raw.get("location")
        if isinstance(location, Mapping) and isinstance(location.get("latitude"), (int, float)) and isinstance(location.get("longitude"), (int, float)):
            candidate["coordinates"] = {"latitude": location["latitude"], "longitude": location["longitude"]}
        hours = raw.get("regularOpeningHours")
        if isinstance(hours, Mapping) and isinstance(hours.get("weekdayDescriptions"), list):
            candidate["opening_hours_note"] = "; ".join(value for value in hours["weekdayDescriptions"] if isinstance(value, str))
        if not restaurant:
            return candidate
        restaurant_candidate = {"place": candidate, "provenance": provenance, "wait_risk": "unknown"}
        if isinstance(raw.get("rating"), (int, float)):
            restaurant_candidate["rating"] = float(raw["rating"])
            restaurant_candidate["rating_source"] = "Google Places"
        if isinstance(raw.get("userRatingCount"), int):
            restaurant_candidate["review_count"] = raw["userRatingCount"]
        if isinstance(raw.get("primaryType"), str):
            restaurant_candidate["cuisine"] = raw["primaryType"]
        restaurant_candidate["opening_hours"] = _google_opening_hours(hours)
        return restaurant_candidate


class YouTubeEvidenceAdapter:
    """YouTube Data API search adapter for community/practical travel evidence.

    It returns evidence only, never a confirmed place or operating-hours fact.
    """

    name = "youtube-data"
    endpoint = "https://www.googleapis.com/youtube/v3/search"

    def __init__(self, api_key: str | None = None, *, http_client: JsonHttpClient | None = None, now: datetime | None = None) -> None:
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        self.http_client = http_client or UrllibJsonHttpClient()
        self.now = now

    def fetch_evidence(self, query: SourceQuery) -> list[ResearchEvidence]:
        if not self.api_key:
            raise ProviderConfigurationError("YOUTUBE_API_KEY is required for YouTube research")
        encoded_query = f"{query.destination} travel parking queue stroller"
        from urllib.parse import urlencode
        payload = self.http_client.request_json("GET", f"{self.endpoint}?{urlencode({'part': 'snippet', 'type': 'video', 'maxResults': 10, 'q': encoded_query, 'key': self.api_key})}", headers={})
        evidence: list[ResearchEvidence] = []
        for item in result_or_empty(payload, "items"):
            video_id = item.get("id", {}).get("videoId") if isinstance(item.get("id"), Mapping) else None
            snippet = item.get("snippet")
            if not isinstance(video_id, str) or not isinstance(snippet, Mapping):
                continue
            title, description = snippet.get("title"), snippet.get("description", "")
            if not isinstance(title, str) or not isinstance(description, str):
                continue
            text = f"{title}\n{description}".lower()
            signals = tuple(signal for signal in ("queue", "parking", "stroller", "crowding") if signal in text)
            if "child" in text or "親子" in text:
                signals += ("child",)
            evidence.append(ResearchEvidence(
                subject=title, summary=description[:500], signals=signals,
                provenance={"source_type": "community", "provider": "YouTube Data API", "source_url": f"https://www.youtube.com/watch?v={video_id}", "retrieved_at": (self.now or datetime.now(timezone.utc)).isoformat(), "status": "reported", "confidence": 0.45, "note": "Community evidence only; verify operational facts with an official source."},
            ))
        return evidence


def result_or_empty(payload: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = payload.get(key, [])
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _google_opening_hours(hours: object) -> dict[str, object]:
    if not isinstance(hours, Mapping):
        return {"status": "unverified", "intervals": []}
    intervals = []
    for period in result_or_empty(hours, "periods"):
        opening, closing = period.get("open"), period.get("close")
        if not isinstance(opening, Mapping) or not isinstance(closing, Mapping):
            continue
        try:
            if int(opening["day"]) != int(closing["day"]):
                continue
            intervals.append({"weekday": (int(opening["day"]) - 1) % 7, "opens_at": f"{int(opening.get('hour', 0)):02}:{int(opening.get('minute', 0)):02}", "closes_at": f"{int(closing.get('hour', 0)):02}:{int(closing.get('minute', 0)):02}"})
        except (KeyError, TypeError, ValueError):
            continue
    return {"status": "fresh" if intervals else "unverified", "intervals": intervals}


def _provenance(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    return candidate.get("provenance") or candidate.get("place", {}).get("provenance", {})
