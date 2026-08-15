"""Production HTTP adapters for Japan-first place and travel research.

Only documented provider APIs are used here.  Provider payloads stop at this
module; callers receive the existing candidate-store contract or evidence
records.  ``http_client`` injection keeps CI fully offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import json
import os
import re
from typing import Any, Iterable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .adapters import SourceAdapter, SourceQuery
from src.opening_hours import HoursStatus, OpeningHoursSnapshot, OpeningInterval, SpecialHours, snapshot_to_mapping


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
                    "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.googleMapsUri,places.websiteUri,places.rating,places.userRatingCount,places.primaryType,places.types,places.priceLevel,places.regularOpeningHours,places.currentOpeningHours,places.timeZone,places.businessStatus",
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
        candidate: dict[str, Any] = {"id": canonical_provider_id("google", place_id), "name": display_name["text"], "kind": "restaurant" if restaurant else "poi", "provenance": provenance}
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
            rating = {
                "value": float(raw["rating"]), "scale_min": 1.0, "scale_max": 5.0,
                "provenance": provenance,
            }
            if isinstance(raw.get("userRatingCount"), int):
                rating["review_count"] = raw["userRatingCount"]
            restaurant_candidate["ratings"] = [rating]
        if isinstance(raw.get("userRatingCount"), int):
            restaurant_candidate["review_count"] = raw["userRatingCount"]
        cuisine = raw.get("primaryType")
        if not isinstance(cuisine, str):
            cuisine = next((value for value in raw.get("types", []) if isinstance(value, str) and "restaurant" in value), None)
        if isinstance(cuisine, str):
            restaurant_candidate["cuisine"] = cuisine
        if isinstance(raw.get("priceLevel"), str):
            restaurant_candidate["meal_price_signals"] = [{"meal": "unspecified", "label": raw["priceLevel"], "provenance": provenance}]
        if isinstance(raw.get("businessStatus"), str):
            restaurant_candidate["business_status"] = raw["businessStatus"].lower()
        timezone_value = raw.get("timeZone")
        timezone_name = timezone_value.get("id") if isinstance(timezone_value, Mapping) else None
        restaurant_candidate["opening_hours"] = _google_opening_hours(
            hours, current=raw.get("currentOpeningHours"), timezone_name=timezone_name, provenance=provenance
        )
        return restaurant_candidate


class HotPepperGourmetAdapter(SourceAdapter):
    """Recruit Hot Pepper Gourmet Web Service adapter (official API only).

    The API's ``open`` field is free text, so it remains an unverified note and
    is never promoted to structured opening intervals.  The consuming UI must
    display the required Japanese Web Service credit documented in the project
    source guide.
    """

    name = "hotpepper-gourmet"
    endpoint = "https://webservice.recruit.co.jp/hotpepper/gourmet/v1/"

    def __init__(
        self, api_key: str | None = None, *, http_client: JsonHttpClient | None = None, now: datetime | None = None
    ) -> None:
        self.api_key = api_key or os.getenv("HOTPEPPER_API_KEY")
        self.http_client = http_client or UrllibJsonHttpClient()
        self.now = now

    def fetch(self, query: SourceQuery) -> Iterable[tuple[str, dict[str, Any]]]:
        if "restaurants" not in query.categories:
            return []
        if not self.api_key:
            raise ProviderConfigurationError("HOTPEPPER_API_KEY is required for Hot Pepper Gourmet")
        from urllib.parse import urlencode

        url = f"{self.endpoint}?{urlencode({'key': self.api_key, 'keyword': query.destination, 'format': 'json', 'count': 100})}"
        payload = self.http_client.request_json("GET", url, headers={})
        results = payload.get("results")
        if not isinstance(results, Mapping):
            raise ProviderRequestError("Hot Pepper response is missing results")
        errors = results.get("error")
        if isinstance(errors, list) and errors:
            raise ProviderRequestError("Hot Pepper returned an API error")
        shops = results.get("shop", [])
        return [
            ("restaurants", candidate)
            for shop in shops if isinstance(shop, Mapping)
            for candidate in [self._candidate(shop)] if candidate is not None
        ]

    def _candidate(self, raw: Mapping[str, Any]) -> dict[str, Any] | None:
        provider_id, name = raw.get("id"), raw.get("name")
        if not isinstance(provider_id, str) or not isinstance(name, str) or not name.strip():
            return None
        retrieved_at = (self.now or datetime.now(timezone.utc)).isoformat()
        urls = raw.get("urls")
        source_url = urls.get("pc") if isinstance(urls, Mapping) and isinstance(urls.get("pc"), str) else self.endpoint
        provenance = {
            "source_type": "provider", "provider": "Hot Pepper Gourmet Web Service",
            "source_url": source_url, "retrieved_at": retrieved_at, "status": "reported", "confidence": 0.75,
            "note": "Powered by ホットペッパーグルメ Webサービス. Free-text hours require official confirmation before scheduling.",
        }
        place: dict[str, Any] = {
            "id": canonical_provider_id("hotpepper", provider_id), "name": name.strip(), "kind": "restaurant",
            "provenance": provenance,
        }
        if isinstance(raw.get("address"), str) and raw["address"].strip():
            place["address"] = raw["address"].strip()
        if isinstance(raw.get("lat"), (int, float)) and isinstance(raw.get("lng"), (int, float)):
            place["coordinates"] = {"latitude": float(raw["lat"]), "longitude": float(raw["lng"])}
        genre = raw.get("genre")
        cuisine = genre.get("name") if isinstance(genre, Mapping) else None
        budget = raw.get("budget")
        average = budget.get("average") if isinstance(budget, Mapping) else None
        budget_name = budget.get("name") if isinstance(budget, Mapping) else None
        hours_note = raw.get("open") if isinstance(raw.get("open"), str) else None
        close_note = raw.get("close") if isinstance(raw.get("close"), str) else None
        note = " / ".join(value for value in (hours_note, close_note) if value)
        hours = {
            "status": "unverified", "timezone": "Asia/Tokyo", "intervals": [], "closed_weekdays": [],
            "regular_holidays": [close_note] if close_note else [], "special_hours": [], "provenance": provenance,
            "note": note or "No structured opening hours supplied by Hot Pepper",
        }
        result: dict[str, Any] = {
            "place": place, "opening_hours": hours, "wait_risk": "unknown", "provenance": provenance,
            "attributions": ["Powered by ホットペッパーグルメ Webサービス"],
        }
        if isinstance(cuisine, str) and cuisine:
            result["cuisine"] = cuisine
        if isinstance(average, str) and average:
            result["price_range"] = average
            result["meal_price_signals"] = [{"meal": "dinner", "label": average, "provenance": provenance}]
        elif isinstance(budget_name, str) and budget_name:
            result["meal_price_signals"] = [{"meal": "dinner", "label": budget_name, "provenance": provenance}]
        child = _japanese_boolean(raw.get("child"))
        parking = _japanese_boolean(raw.get("parking"))
        if child is not None:
            result["child_friendly"] = child
        if parking is not None:
            result["parking_available"] = parking
        smoking = raw.get("non_smoking")
        if isinstance(smoking, str) and smoking:
            result["smoking_policy"] = _smoking_policy(smoking)
        return result


class OfficialRestaurantFeedAdapter(SourceAdapter):
    """Normalized official-feed seam; records must declare an exact place ID.

    This adapter intentionally performs no name matching and no web scraping.
    A deployment may populate it from an operator-maintained JSON feed or CMS.
    """

    name = "official-restaurant-feed"

    def __init__(self, records: Iterable[Mapping[str, Any]], *, now: datetime | None = None) -> None:
        self.records = tuple(records)
        self.now = now

    def fetch(self, query: SourceQuery) -> Iterable[tuple[str, dict[str, Any]]]:
        if "restaurants" not in query.categories:
            return []
        return [("restaurants", candidate) for record in self.records for candidate in [self._candidate(record)] if candidate is not None]

    def _candidate(self, record: Mapping[str, Any]) -> dict[str, Any] | None:
        place_id, name, source_url = record.get("place_id"), record.get("name"), record.get("source_url")
        if not isinstance(place_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", place_id):
            return None
        if not isinstance(name, str) or not name or not isinstance(source_url, str):
            return None
        provenance = {
            "source_type": "official", "provider": str(record.get("provider") or name),
            "source_url": source_url, "retrieved_at": (self.now or datetime.now(timezone.utc)).isoformat(),
            "status": "confirmed", "confidence": 1.0,
        }
        candidate: dict[str, Any] = {
            "place": {"id": place_id, "name": name, "kind": "restaurant", "provenance": provenance},
            "provenance": provenance,
        }
        hours = record.get("opening_hours")
        if isinstance(hours, Mapping):
            candidate["opening_hours"] = {**hours, "provenance": provenance}
        for field in (
            "reservation_required", "reservation_url", "child_friendly", "smoking_policy",
            "parking_available", "business_status", "cuisine", "price_range",
        ):
            if field in record:
                candidate[field] = record[field]
        return candidate


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


def _google_opening_hours(
    hours: object, *, current: object = None, timezone_name: object = None, provenance: Mapping[str, Any] | None = None
) -> dict[str, object]:
    """Normalize Places API (New) regular and current opening-hours fields."""

    intervals: list[OpeningInterval] = []
    if isinstance(hours, Mapping):
        for period in result_or_empty(hours, "periods"):
            intervals.extend(_google_period(period))
    special_hours = _google_special_hours(current)
    open_weekdays = {interval.weekday for interval in intervals}
    open_weekdays.update((interval.weekday + 1) % 7 for interval in intervals if interval.closes_day_offset == 1)
    if not isinstance(timezone_name, str) or not timezone_name:
        snapshot = OpeningHoursSnapshot(
            HoursStatus.UNVERIFIED,
            "UTC",
            tuple(intervals),
            tuple(day for day in range(7) if day not in open_weekdays),
            (),
            tuple(special_hours),
            provenance,
            note="Google Places did not return an IANA restaurant timezone",
        )
        result = snapshot_to_mapping(snapshot)
        result.pop("timezone", None)
        return result

    snapshot = OpeningHoursSnapshot(
        HoursStatus.FRESH if intervals or special_hours else HoursStatus.UNVERIFIED,
        timezone_name,
        tuple(intervals),
        tuple(day for day in range(7) if day not in open_weekdays),
        (),
        tuple(special_hours),
        provenance,
    )
    return snapshot_to_mapping(snapshot)


def _google_period(period: Mapping[str, Any], *, weekday: int | None = None) -> list[OpeningInterval]:
    opening, closing = period.get("open"), period.get("close")
    if not isinstance(opening, Mapping):
        return []
    if not isinstance(closing, Mapping):
        try:
            opens = _clock(opening)
            open_day = int(opening.get("day", 0))
        except (TypeError, ValueError):
            return []
        if opens != time(0):
            return []
        if weekday is not None:
            return [OpeningInterval(weekday, time(0), time(0), 1)]
        return [OpeningInterval(day, time(0), time(0), 1) for day in range(7)] if open_day == 0 else []
    try:
        opens = _clock(opening)
        closes = _clock(closing)
        open_day = int(opening.get("day", 0))
        close_day = int(closing.get("day", open_day))
        py_weekday = weekday if weekday is not None else (open_day - 1) % 7
    except (TypeError, ValueError):
        return []
    difference = (close_day - open_day) % 7
    if difference == 0 and closes == opens:
        # Places represents an always-open period as equal endpoints. Expand it
        # into seven explicit 24-hour intervals without non-standard 24:00.
        if weekday is not None:
            return [OpeningInterval(weekday, opens, closes, 1)]
        return [OpeningInterval(day, time(0), time(0), 1) for day in range(7)]
    if difference > 1:
        return []
    offset = 1 if difference == 1 or closes <= opens else 0
    return [OpeningInterval(py_weekday, opens, closes, offset)]


def _google_special_hours(current: object) -> list[SpecialHours]:
    if not isinstance(current, Mapping):
        return []
    periods_by_date: dict[date, list[OpeningInterval]] = {}
    for period in result_or_empty(current, "periods"):
        opening = period.get("open")
        special_date = _google_date(opening.get("date")) if isinstance(opening, Mapping) else None
        if special_date is None:
            continue
        periods_by_date.setdefault(special_date, []).extend(_google_period(period, weekday=special_date.weekday()))
    special: list[SpecialHours] = []
    seen: set[date] = set()
    for value in result_or_empty(current, "specialDays"):
        special_date = _google_date(value.get("date"))
        if special_date is None:
            continue
        seen.add(special_date)
        if periods_by_date.get(special_date):
            special.append(SpecialHours(special_date, "open", tuple(periods_by_date[special_date])))
        else:
            special.append(SpecialHours(special_date, "closed"))
    # Dated current periods are stronger than regular weekly hours even if the
    # response did not include a specialDays marker.
    for special_date, periods in periods_by_date.items():
        if special_date not in seen:
            special.append(SpecialHours(special_date, "open", tuple(periods)))
    return sorted(special, key=lambda item: item.date)


def _google_date(value: object):
    if not isinstance(value, Mapping):
        return None
    try:
        return date(int(value["year"]), int(value["month"]), int(value["day"]))
    except (KeyError, TypeError, ValueError):
        return None


def _clock(value: Mapping[str, Any]):
    hour, minute = int(value.get("hour", 0)), int(value.get("minute", 0))
    return time(hour, minute)


def canonical_provider_id(provider: str, provider_id: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", provider_id.lower()).strip("-_")
    if not normalized:
        import hashlib
        normalized = hashlib.sha256(provider_id.encode("utf-8")).hexdigest()[:20]
    return f"{provider}-{normalized}"


def _japanese_boolean(value: object) -> bool | None:
    if not isinstance(value, str):
        return None
    compact = value.strip().lower()
    if not compact:
        return None
    if any(token in compact for token in ("なし", "無し", "不可", "ng", "no")):
        return False
    if any(token in compact for token in ("あり", "有", "ok", "歓迎", "可")):
        return True
    return None


def _smoking_policy(value: str) -> str:
    if "全面禁煙" in value:
        return "non_smoking"
    if "一部禁煙" in value or "分煙" in value:
        return "partially_smoking"
    if "禁煙席なし" in value or "喫煙可" in value:
        return "smoking_allowed"
    return value


def _provenance(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    return candidate.get("provenance") or candidate.get("place", {}).get("provenance", {})
