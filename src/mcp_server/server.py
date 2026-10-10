"""MCP server exposing the existing travel planning boundaries."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Annotated, Any
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from src.application.production import (
    ProductionConfigurationError,
    ProductionIncompleteError,
    create_production_orchestrator,
    missing_required_configuration,
)
from src.budget import format_budget_summary
from src.google_places_storage import durable_trip
from src.intent import parse_trip_request
from src.mcp_server.github_pages import GitHubPagesPublisher, GitHubPublishError
from src.orchestrator import StageStatus
from src.renderer.build_site import build_site
from src.schemas.validate_trip import TripValidationError, validate_trip
from src.sources import GooglePlacesAdapter, ProviderConfigurationError, ProviderRequestError
from src.sources.providers import ProviderHttpError
from src.validator import ValidationContext, validate_itinerary

_TRIP_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_TRIPS_DIR = Path(os.environ.get("TRAVEL_PLANNER_TRIPS_DIR", "trips")).resolve()
_SITE_DIR = Path(os.environ.get("TRAVEL_PLANNER_SITE_DIR", "site")).resolve()
_HTTP_REQUEST_LIMIT = 120
_HTTP_WINDOW_SECONDS = 60
_HTTP_MAX_BODY_BYTES = 4 * 1024 * 1024
_PUBLIC_PLACE_REQUEST_LIMIT = 60
_GOOGLE_PLACES_MONTHLY_LIMIT = 1_000
_GOOGLE_PLACE_ID = re.compile(r"^[A-Za-z0-9_-]{5,255}$")
_GOOGLE_PLACES_USAGE_PATH = Path(os.environ.get(
    # Keep the existing env name and file path to preserve current Railway data.
    "PUBLIC_PLACE_DETAILS_USAGE_FILE", str(_TRIPS_DIR.parent / ".public-place-details-usage.json")
))
_GOOGLE_PLACES_USAGE_LOCK = threading.Lock()
_MCP_LOCAL_ALLOWED_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")

mcp = MCPServer(
    "ai-travel-planner",
    instructions=(
        "Use Canonical Trip V1 as the sole trip record and answer in Traditional Chinese. "
        "When using parse_trip_request, preserve intent.origin exactly as returned: repeat a non-null value verbatim, and if it is null say that no origin was parsed. Never infer, omit, or change this field. "
        "Never present raw tool JSON, schemas, or opaque provider IDs as the final answer unless the traveler explicitly asks for them. "
        "Summarize tool results in natural, concise Traditional Chinese. For a saved itinerary, organize scheduled items by local date and trip timezone; show each item's start–end time, identify visits and meals by their current names when available, and state material validation warnings and incomplete fields. "
        "If a day has an unknown arrival/start or lodging/return route, explicitly say the displayed activity window excludes that unverified transfer; do not imply the day is fully connected. Clearly distinguish planned items from verified facts; never describe unknown routes, opening hours, availability, or prices as verified. Omit absent lodging when the traveler chose to leave it blank; do not invent a hotel. "
        "For trip planning, ask one focused clarification question at a time only for information required to proceed safely or produce a valid plan; preserve prior answers and never invent missing facts. Do not turn planning into a long optional-preference questionnaire: once required information is sufficient, summarize and wait for confirmation. "
        "Lodging is not an active search feature. Unless the traveler voluntarily supplies lodging details, do not ask lodging preference, room, location, or hotel questions, do not search or recommend lodging, and keep lodging fields empty. A displayed or preselected UI option is not a user answer; record a preference only after the traveler explicitly selects or states it. If the traveler has not decided, preserve it as unknown instead of choosing a default. "
        "Before plan_trip writes trip/site files, summarize the request and obtain explicit user confirmation; call it with confirm_write=true only after confirmation. If the traveler explicitly asked for the completed trip to be published publicly and its URL returned, include publication in that confirmation summary; after the traveler confirms, call plan_trip with both confirm_write=true and confirm_public_publish=true. That plan_trip call publishes automatically after a successful plan and returns the actual website URL; do not rely on a later optional model tool call to publish. If public publication was not explicitly requested, call plan_trip with confirm_public_publish=false and ask separately after planning. "
        "After a successful plan_trip, call get_trip to read the saved itinerary. When presenting a readable or day-by-day itinerary, treat the request as asking for current names of scheduled places unless the traveler requests ID-only output or declines live lookups. Read get_trip.place_details_needed and call get_place_details once for each listed Place ID; include the returned Google Maps and third-party attribution. Do not stop at opaque Place IDs or query unselected candidates. Each lookup is a live Places request and may incur usage charges. MCP and public-page lookups share a 1,000-request monthly service budget; if a lookup returns monthly_limit_reached, stop further lookups and report remaining names as unavailable this month. "
        "Google Places details are request-scoped and must never be saved; only Place IDs may persist. If a detail lookup fails, say it is unavailable and do not substitute stale saved data or guess. "
        "Preserve unknown facts. When showing a traveler the completed trip, publish completed trip details to GitHub Pages only when the traveler explicitly requested public publication or explicitly approves it. An explicit request to plan the trip, publish its website publicly, and return the URL is public-publishing consent; include it in the pre-planning confirmation summary, then after confirmation call plan_trip with both confirm_write=true and confirm_public_publish=true. The plan_trip result includes the publication result and website URL after successful planning. Planning consent and confirm_write alone do not grant publication consent. If public publication was not explicitly requested, ask separately after planning. If publication returns overwrite_confirmation_required because a different version of this trip is already public, ask separately whether to replace that public page; only after explicit approval call publish_trip_site with both confirm_public_publish=true and confirm_overwrite=true. If publication succeeds or the identical page is already published, return its url as a clickable link and explain deployment_status: pending means the new commit's Pages deployment is still running, and not_required means the identical public page already exists and this call started no deployment. These are the deployment_status values this tool returns; never claim a deployment finished while it is pending or not_required."
    ),
)


def _consume_remote_request(
    user_id: str,
    now: float,
    windows: dict[str, tuple[int, float]],
    *,
    limit: int = _HTTP_REQUEST_LIMIT,
) -> bool:
    """Apply a per-user fixed-window limit; state is held only in process memory."""
    count, window_started = windows.get(user_id, (0, now))
    if now - window_started >= _HTTP_WINDOW_SECONDS:
        count, window_started = 0, now
    if count >= limit:
        return False
    if user_id not in windows and len(windows) >= 10_000:
        expired = [key for key, (_, started) in windows.items() if now - started >= _HTTP_WINDOW_SECONDS]
        for key in expired:
            windows.pop(key, None)
        if len(windows) >= 10_000:
            return False
    windows[user_id] = (count + 1, window_started)
    return True


def _github_pages_origin(pages_base_url: str) -> str:
    parsed = urlsplit(pages_base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("GitHub Pages base URL must be an HTTPS URL")
    return f"https://{parsed.netloc}"


def _published_scheduled_google_place_ids(slug: str, pages_base_url: str) -> set[str]:
    """Read the public bundle and allow only Google places actually on its schedule."""
    if not _TRIP_ID.fullmatch(slug):
        return set()
    base = pages_base_url.rstrip("/")
    headers = {"Accept": "application/json", "User-Agent": "ai-travel-planner-place-details/1.0"}
    try:
        registry_request = Request(f"{base}/trip-registry.json", headers=headers)
        with urlopen(registry_request, timeout=5) as response:
            registry_raw = response.read(_HTTP_MAX_BODY_BYTES + 1)
        if len(registry_raw) > _HTTP_MAX_BODY_BYTES:
            return set()
        registry = json.loads(registry_raw)
        if not isinstance(registry, list) or not any(
            isinstance(entry, dict)
            and entry.get("slug") == slug
            and entry.get("canonical_url", "").rstrip("/") == f"trips/{slug}"
            for entry in registry
        ):
            return set()
        bundle_request = Request(f"{base}/trips/{slug}/public-bundle.json", headers=headers)
        with urlopen(bundle_request, timeout=5) as response:
            bundle_raw = response.read(_HTTP_MAX_BODY_BYTES + 1)
        if len(bundle_raw) > _HTTP_MAX_BODY_BYTES:
            return set()
        bundle = json.loads(bundle_raw)
    except Exception:
        return set()
    trip_id = bundle.get("trip_id") if isinstance(bundle, dict) else None
    if not isinstance(bundle, dict) or not isinstance(trip_id, str) or not _TRIP_ID.fullmatch(trip_id):
        return set()
    scheduled: set[str] = set()
    days = bundle.get("days", [])
    if not isinstance(days, list):
        return set()
    for day in days:
        if not isinstance(day, dict) or not isinstance(day.get("items", []), list):
            continue
        for item in day.get("items", []):
            if isinstance(item, dict) and isinstance(item.get("place_id"), str):
                scheduled.add(item["place_id"])
    places = bundle.get("places", [])
    if not isinstance(places, list):
        return set()
    return {
        place["google_place_id"]
        for place in places
        if isinstance(place, dict)
        and place.get("id") in scheduled
        and isinstance(place.get("google_place_id"), str)
        and _GOOGLE_PLACE_ID.fullmatch(place["google_place_id"])
    }


def _consume_google_places_monthly_budget(
    path: Path | None = None,
    *,
    month: str | None = None,
    limit: int | None = None,
) -> bool:
    """Count Google Places requests across MCP and public lookup paths; fail closed."""
    path = path or _GOOGLE_PLACES_USAGE_PATH
    limit = _GOOGLE_PLACES_MONTHLY_LIMIT if limit is None else limit
    month = month or time.strftime("%Y-%m", time.gmtime())
    with _GOOGLE_PLACES_USAGE_LOCK:
        try:
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            count = current.get("count", 0) if current.get("month") == month else 0
            if not isinstance(count, int) or isinstance(count, bool) or count < 0 or count >= limit:
                return False
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f"{path.name}.tmp")
            temporary.write_text(json.dumps({"month": month, "count": count + 1}), encoding="utf-8")
            os.replace(temporary, path)
            return True
        except (OSError, ValueError, TypeError, AttributeError):
            return False


async def _read_limited_asgi_body(receive, limit: int) -> list[dict[str, Any]] | None:
    """Buffer an HTTP request body, returning None once its actual bytes exceed limit."""
    messages: list[dict[str, Any]] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return messages
        if message["type"] != "http.request":
            continue
        size += len(message.get("body", b""))
        if size > limit:
            return None
        messages.append(message)
        if not message.get("more_body", False):
            return messages


def _is_complete_plan_result(result: Any) -> bool:
    """A produced trip is complete only when every reported stage succeeded."""
    stages = tuple(result.stages)
    return bool(
        result.succeeded
        and stages
        and all(stage.status is StageStatus.SUCCEEDED for stage in stages)
    )


def _trip_path(trip_id: str) -> Path:
    if not _TRIP_ID.fullmatch(trip_id):
        raise ValueError("trip_id must contain lowercase letters, digits, and hyphens")
    path = (_TRIPS_DIR / trip_id / "trip.json").resolve()
    if not path.is_relative_to(_TRIPS_DIR):
        raise ValueError("trip_id resolves outside the configured trips directory")
    return path


def _public_trip_summary(trip: dict[str, Any]) -> dict[str, Any]:
    """Project a small public summary; never return the raw canonical record."""
    places = {
        place["id"]: {key: place[key] for key in ("id", "google_place_id", "name", "kind") if key in place}
        for place in trip.get("candidate_sets", {}).get("places", [])
        if isinstance(place, dict) and isinstance(place.get("id"), str)
    }
    days = []
    for day in trip.get("days", []):
        items = []
        for item in day.get("items", []):
            place = places.get(item.get("place_id"), {})
            items.append(
                {
                    key: item[key]
                    for key in ("id", "kind", "start_at", "end_at", "status")
                    if key in item
                }
            )
            if place:
                items[-1]["place"] = place
        days.append(
            {key: day[key] for key in ("date",) if key in day} | {"items": items}
        )
    raw_dates = trip.get("date_range")
    date_range = (
        {key: raw_dates[key] for key in ("start_date", "end_date") if key in raw_dates}
        if isinstance(raw_dates, dict)
        else None
    )
    findings = [
        {key: entry[key] for key in ("code", "severity", "path") if key in entry}
        for entry in trip.get("validation", [])
        if isinstance(entry, dict)
    ]
    raw_budget = trip.get("budget")
    budget = None
    if isinstance(raw_budget, dict):
        budget = {
            key: raw_budget[key]
            for key in ("currency", "categories", "total", "total_status", "limit_status", "limit")
            if key in raw_budget
        }
        budget["summary"] = format_budget_summary(raw_budget)
    return {
        "schema_version": trip.get("schema_version"),
        "id": trip.get("id"),
        "title": trip.get("title"),
        "local_timezone": trip.get("local_timezone"),
        "date_range": date_range,
        "flight_search_url": trip.get("flight_search_url"),
        "flight_search_summary": trip.get("flight_search_summary"),
        "days": days,
        "budget": budget,
        "validation": findings,
    }


def _place_details_needed(summary: dict[str, Any]) -> list[str]:
    """List distinct scheduled Google Place IDs lacking an independently sourced name."""
    needed: list[str] = []
    seen: set[str] = set()
    for day in summary.get("days", []):
        for item in day.get("items", []):
            place = item.get("place")
            name = place.get("name") if isinstance(place, dict) else None
            if not isinstance(place, dict) or (isinstance(name, str) and name.strip()):
                continue
            place_id = place.get("google_place_id")
            if (
                isinstance(place_id, str)
                and _GOOGLE_PLACE_ID.fullmatch(place_id)
                and place_id not in seen
            ):
                seen.add(place_id)
                needed.append(place_id)
    return needed


@mcp.tool(
    name="parse_trip_request",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def parse_trip_request_tool(
    request: Annotated[
        str,
        Field(
            min_length=1,
            max_length=20_000,
            description="Natural-language trip request; only explicit facts are parsed.",
        ),
    ],
) -> dict[str, Any]:
    """Parse explicit travel facts without research or invention. Present the result as a concise Traditional Chinese summary, not raw JSON, unless the traveler asks for the structured payload. Preserve intent.origin exactly: repeat a non-null value verbatim, or state that no origin was parsed when it is null. Never infer or alter origin."""
    if not request.strip():
        return {"status": "invalid_input", "message": "request must not be empty"}
    if len(request) > 20_000:
        return {
            "status": "invalid_input",
            "message": "request must be 20,000 characters or fewer",
        }
    return {"status": "parsed", "intent": parse_trip_request(request).as_dict()}


@mcp.tool(
    name="validate_trip",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def validate_trip_tool(trip: dict[str, Any]) -> dict[str, Any]:
    """Validate a supplied Canonical Trip V1 document and return its deterministic findings."""
    try:
        validate_trip(trip)
    except (TripValidationError, KeyError, TypeError, ValueError) as exc:
        return {"status": "invalid", "stage": "schema", "message": str(exc)}
    result = validate_itinerary(trip, ValidationContext())
    return {
        "status": result.outcome.value,
        "findings": [finding.as_dict() for finding in result.violations],
    }


@mcp.tool(
    name="get_trip",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def get_trip_tool(
    trip_id: Annotated[
        str,
        Field(
            pattern=r"^[a-z0-9][a-z0-9-]{0,79}$",
            description="Lowercase letters, digits, and hyphens; resolves under TRAVEL_PLANNER_TRIPS_DIR.",
        ),
    ],
) -> dict[str, Any]:
    """Read a bounded itinerary summary. Do not present raw JSON as the final answer unless requested; summarize items by local date and trip timezone, show start and end times, and distinguish visits from meals. The response's place_details_needed array is the authoritative list of distinct scheduled Google Place IDs lacking an independently sourced name. When presenting a readable or day-by-day itinerary, call get_place_details once for each listed ID and include attribution; do not stop at opaque IDs or query unselected candidates. Each detail call makes one live Places request and may incur usage charges. MCP and public-page lookups share a persistent 1,000-request monthly service budget; if the limit is reached, stop further lookups. If validation says an arrival/start or lodging/return route is unknown, state that the activity time range excludes that unverified transfer. Report validation warnings and incomplete budget or lodging without implying they are complete."""
    try:
        path = _trip_path(trip_id)
        trip = durable_trip(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return {"status": "not_found", "trip_id": trip_id}
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {"status": "error", "message": str(exc)}
    try:
        summary = _public_trip_summary(trip)
    except (AttributeError, KeyError, TypeError) as exc:
        return {
            "status": "invalid",
            "message": f"trip summary cannot be projected: {exc}",
        }
    return {
        "status": "ok",
        "trip": summary,
        "place_details_needed": _place_details_needed(summary),
    }


@mcp.tool(
    name="get_place_details",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
def get_place_details_tool(
    place_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=256,
            pattern=r"^(?:places/)?[A-Za-z0-9_-]+$",
            description="Raw google_place_id from get_trip (such as ChIJ...); fetch current details for this request only.",
        ),
    ],
) -> dict[str, Any]:
    """Fetch request-scoped details for one scheduled Google Place ID. Calls share the service's persistent 1,000-request monthly Google Places budget with public-page lookups; monthly_limit_reached means no provider request was made and further detail lookups should stop. Each accepted call makes one live Places request and may incur usage charges; include Google Maps and third-party attribution. Never query unselected candidates or store the response."""
    raw_place_id = place_id.removeprefix("places/")
    if not _GOOGLE_PLACE_ID.fullmatch(raw_place_id):
        return {"status": "invalid_input", "message": "place_id must be a Google Place ID"}
    if not os.environ.get("GOOGLE_MAPS_API_KEY"):
        return {"status": "configuration_missing", "missing": ["GOOGLE_MAPS_API_KEY"]}
    if not _consume_google_places_monthly_budget():
        return {"status": "monthly_limit_reached"}
    try:
        return GooglePlacesAdapter(api_key=os.environ["GOOGLE_MAPS_API_KEY"]).get_place_details(place_id)
    except ValueError:
        return {"status": "invalid_input", "message": "place_id must be a Google Place ID"}
    except ProviderConfigurationError:
        return {"status": "configuration_missing", "missing": ["GOOGLE_MAPS_API_KEY"]}
    except ProviderHttpError as exc:
        retryable = exc.status_code == 429 or exc.status_code >= 500
        return {
            "status": "unavailable",
            "reason": "provider_busy" if retryable else "provider_rejected_request",
            "retryable": retryable,
        }
    except ProviderRequestError:
        return {"status": "unavailable", "reason": "network_or_provider_error", "retryable": True}
    except Exception:
        return {"status": "unavailable", "reason": "provider_request_failed", "retryable": True}


@mcp.tool(
    name="plan_trip",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
def plan_trip_tool(
    request: Annotated[
        str,
        Field(
            min_length=1,
            max_length=20_000,
            description="Natural-language travel request.",
        ),
    ],
    trip_id: Annotated[
        str,
        Field(
            pattern=r"^[a-z0-9][a-z0-9-]{0,79}$",
            description="Destination trip folder slug.",
        ),
    ],
    confirm_write: Annotated[
        bool,
        Field(
            description="Must be true to run live planning and write Canonical Trip and site files."
        ),
    ] = False,
    confirm_public_publish: Annotated[
        bool,
        Field(
            description=(
                "Must be true only after the traveler explicitly requested public publication "
                "and confirmed the pre-planning summary that says the completed trip will be public. "
                "When true, publish the successfully planned trip and return its website URL."
            )
        ),
    ] = False,
) -> dict[str, Any]:
    """以繁體中文進行一題一答的規劃，不要把 parser JSON 原樣當成回答。

    先用 parse_trip_request 累積使用者明確提供的內容。若回傳
    needs_clarification，只問 next_question 並等待回答；每輪保留先前答案，
    不重問已解決欄位、不猜測缺漏資訊，也不可在必要欄位未補齊時啟動研究。
    只追問繼續規劃所需的必要資訊；必要欄位齊全後，不要延伸成冗長的選擇題或偏好問卷，應整理摘要並等待確認。住宿不是目前提供的自動搜尋功能；除非旅客主動提供住宿資料，否則不要詢問住宿地點、房型、房間數或住宿偏好，亦不要搜尋、推薦或填寫住宿欄位，所有住宿欄位維持空值。介面預先選取或高亮的選項不代表旅客已確認；只有旅客明確選擇或文字回答的偏好才可記錄，未決定的內容保留未知。
    資料完整後，先摘要需求並取得使用者對私有檔案寫入的明確確認，再以
    confirm_write=true 呼叫本工具。這會建立或覆寫指定 trip_id 的 Canonical
    Trip 與靜態網站檔案。若使用者已明確要求規劃後公開網站並回傳網址，摘要須明確
    說明公開發布；使用者確認後，以 confirm_write=true 與
    confirm_public_publish=true 呼叫本工具。規劃成功時本工具會接續發布，並回傳
    publication.url；不完整或失敗的規劃不會發布。若使用者沒有明確要求公開，使用
    confirm_public_publish=false；規劃完成後再另行詢問。
    """
    try:
        _trip_path(trip_id)
    except ValueError as exc:
        return {"status": "invalid_input", "message": str(exc)}
    if len(request) > 20_000:
        return {
            "status": "invalid_input",
            "message": "request must be 20,000 characters or fewer",
        }
    intent = parse_trip_request(request)
    intent_data = intent.as_dict()
    missing_fields = list(intent_data["missing_fields"])
    # A duration is enough for an initial conversation, but live provider
    # research needs a concrete date range for openings, routing, and lodging.
    if not intent.start_date or not intent.end_date:
        if not any(item["field"] == "dates" for item in missing_fields):
            insertion = 1 if missing_fields and missing_fields[0]["field"] == "destination" else 0
            missing_fields.insert(insertion, {
                "field": "dates",
                "reason": "即時行程研究需要明確的出發與返程日期",
            })
    if missing_fields or intent.ambiguous_fields or intent.constraint_issues:
        return {
            "status": "needs_clarification",
            "intent": intent_data,
            "missing_fields": missing_fields,
            "ambiguous_fields": intent_data["ambiguous_fields"],
            "constraint_issues": intent_data["constraint_issues"],
            "next_question": _next_clarification_question(
                missing_fields, intent_data["ambiguous_fields"], intent_data["constraint_issues"]
            ),
        }
    missing = missing_required_configuration()
    if missing:
        return {"status": "configuration_missing", "missing": missing}
    if not confirm_write:
        message = "Call again with confirm_write=true to create trip and site files."
        if confirm_public_publish:
            message = (
                "The traveler has also confirmed public publication. Call again with "
                "confirm_write=true and confirm_public_publish=true to plan and publish the trip."
            )
        return {
            "status": "confirmation_required",
            "message": message,
        }
    try:
        runner = create_production_orchestrator(
            trip_id=trip_id,
            trips_directory=_TRIPS_DIR,
            site_directory=_SITE_DIR,
        )
        result = runner.run(intent)
    except ProductionConfigurationError:
        return {
            "status": "configuration_missing",
            "missing": missing_required_configuration(),
        }
    except (ProductionIncompleteError, ValueError) as exc:
        response: dict[str, Any] = {
            "status": "incomplete",
            "message": str(exc),
        }
        if confirm_public_publish:
            response["publication"] = {
                "status": "not_attempted",
                "reason": "plan_incomplete",
            }
        return response
    canonical_trip = getattr(result, "trip", None)
    trip_budget = canonical_trip.get("budget") if isinstance(canonical_trip, dict) else None
    response = {
        "status": "complete" if _is_complete_plan_result(result) else "incomplete",
        "trip_id": trip_id,
        "budget": trip_budget,
        "budget_summary": format_budget_summary(trip_budget) if isinstance(trip_budget, dict) else None,
        "stages": [
            {"name": stage.name.value, "status": stage.status.value}
            for stage in result.stages
        ],
        "warnings": [
            {
                key: value
                for key, value in (
                    ("code", warning.code),
                    ("stage", warning.stage.value),
                    ("path", warning.path),
                    ("message", warning.message),
                )
                if value
            }
            for warning in result.warnings
        ],
    }
    if confirm_public_publish:
        if response["status"] == "complete":
            response["publication"] = publish_trip_site_tool(
                trip_id,
                confirm_public_publish=True,
            )
        else:
            response["publication"] = {
                "status": "not_attempted",
                "reason": "plan_incomplete",
            }
    return response


def _next_clarification_question(missing, ambiguous, constraint_issues) -> str:
    """Return one concrete question so the MCP host can conduct a focused QA turn."""
    questions = {
        "destination": "你想去哪些城市或地區？",
        "dates": "請提供確切的出發與返程日期（YYYY/MM/DD）。",
        "dates_or_duration": "這趟旅行預計哪幾天出發與返程，或總共安排幾天？",
        "travelers": "共有幾位成人、幾位兒童？",
        "budget": "你希望設定預算上限，還是明確不設預算限制？",
        "origin": "你會從哪個城市或機場出發？",
        "transport": "你希望主要使用自駕、大眾運輸，還是兩者搭配？",
    }
    for item in missing:
        question = questions.get(item["field"])
        if question:
            return question
    if ambiguous:
        item = ambiguous[0]
        return f"我需要先釐清「{item['field']}」：{item['reason']}。你希望採用哪一種？"
    if constraint_issues:
        item = constraint_issues[0]
        return f"我需要先釐清「{item['field']}」：{item['reason']}。你希望如何調整？"
    return "請補充你最希望優先滿足的行程條件。"


@mcp.tool(
    name="build_trip_site",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
def build_trip_site_tool(
    trip_id: Annotated[
        str,
        Field(
            pattern=r"^[a-z0-9][a-z0-9-]{0,79}$",
            description="Existing trip folder slug.",
        ),
    ],
    confirm_write: Annotated[
        bool,
        Field(
            description="Must be true to write the static site under TRAVEL_PLANNER_SITE_DIR."
        ),
    ] = False,
) -> dict[str, Any]:
    """Build a local static site from a valid Canonical Trip; never deploys or publishes it."""
    try:
        path = _trip_path(trip_id)
        trip = durable_trip(json.loads(path.read_text(encoding="utf-8")))
        validate_trip(trip)
    except FileNotFoundError:
        return {"status": "not_found", "trip_id": trip_id}
    except (
        OSError,
        json.JSONDecodeError,
        TripValidationError,
        ValueError,
        TypeError,
    ) as exc:
        return {"status": "invalid", "message": str(exc)}
    if not confirm_write:
        return {
            "status": "confirmation_required",
            "message": "Call again with confirm_write=true to write the static site.",
        }
    output = (_SITE_DIR / trip_id / "index.html").resolve()
    if not output.is_relative_to(_SITE_DIR):
        return {
            "status": "invalid_input",
            "message": "trip_id resolves outside the configured site directory",
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_site(trip), encoding="utf-8")
    return {"status": "built", "trip_id": trip_id, "site_path": str(output)}


@mcp.tool(
    name="publish_trip_site",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
def publish_trip_site_tool(
    trip_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")],
    site_slug: Annotated[str | None, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")] = None,
    confirm_public_publish: Annotated[
        bool,
        Field(description="Must be true to publish this trip publicly to the repository's GitHub Pages site."),
    ] = False,
    confirm_overwrite: Annotated[
        bool,
        Field(description="Must be true to replace an existing public page for the same trip."),
    ] = False,
) -> dict[str, Any]:
    """Publish a Canonical Trip preview after explicit public approval; blocking validation still refuses publication."""
    if not confirm_public_publish:
        return {
            "status": "confirmation_required",
            "message": "This action makes itinerary details publicly accessible. Call again with confirm_public_publish=true only after the traveler explicitly approves public publication.",
        }
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return {"status": "configuration_missing", "missing": ["GITHUB_TOKEN"]}
    try:
        path = _trip_path(trip_id)
        trip = durable_trip(json.loads(path.read_text(encoding="utf-8")))
        validate_trip(trip)
        if trip.get("id") != trip_id:
            return {"status": "invalid", "message": "trip_id does not match the Canonical Trip id"}
    except FileNotFoundError:
        return {"status": "not_found", "trip_id": trip_id}
    except (OSError, json.JSONDecodeError, TripValidationError, ValueError, TypeError) as exc:
        return {"status": "invalid", "message": str(exc)}
    repository = os.environ.get("GITHUB_REPOSITORY", "JackyTsai70113/ai-travel-planner")
    branch = os.environ.get("GITHUB_PAGES_BRANCH", "main")
    pages_base_url = os.environ.get("GITHUB_PAGES_BASE_URL", "https://jackytsai70113.github.io/ai-travel-planner")
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    public_api_base_url = f"https://{railway_domain}" if re.fullmatch(r"[A-Za-z0-9.-]+", railway_domain) else None
    try:
        result = GitHubPagesPublisher(
            token=token,
            repository=repository,
            branch=branch,
            pages_base_url=pages_base_url,
            public_api_base_url=public_api_base_url,
        ).publish(trip, slug=site_slug or trip_id, confirm_overwrite=confirm_overwrite)
    except ValueError as exc:
        message = str(exc)
        status = (
            "not_ready"
            if "not ready for public publication" in message
            or "Google Places API content cannot be persisted" in message
            else "invalid_input"
        )
        return {"status": status, "message": message}
    except GitHubPublishError as exc:
        if "confirm_overwrite=true" in str(exc):
            status = "overwrite_confirmation_required"
        elif exc.status_code == 409:
            status = "conflict"
        else:
            status = "publish_failed"
        result: dict[str, Any] = {"status": status, "message": str(exc)}
        if exc.status_code is not None:
            result["http_status"] = exc.status_code
        return result
    return {
        "status": result.status,
        "trip_id": trip_id,
        "site_slug": result.slug,
        "url": result.url,
        "repository": result.repository,
        "commit_sha": result.commit_sha,
        "deployment_status": result.deployment_status,
    }


@mcp.resource("travel-planner://capabilities")
def capabilities() -> str:
    """Describe tool side effects and the canonical planning stages."""
    return json.dumps(
        {
            "schema_version": "mcp-capabilities-v1",
            "pipeline": [
                "research",
                "planning",
                "optimization",
                "validation",
                "rendering",
            ],
            "canonical_source_of_truth": "Canonical Trip V1",
            "tools": {
                "parse_trip_request": "read-only; parses only explicit user facts",
                "validate_trip": "read-only; validates supplied JSON",
                "get_trip": "read-only; returns allowlisted trip fields and place_details_needed for scheduled places needing live names",
                "get_place_details": "read-only live Google Places lookup; shares a persistent monthly request budget with public lookups and is never persisted",
                "plan_trip": "requires confirm_write=true; performs live provider research and writes local trip/site files; when confirm_public_publish=true, automatically publishes only after successful planning and returns the website URL",
                "build_trip_site": "requires confirm_write=true; writes a local static site; never deploys",
                "publish_trip_site": "requires explicit confirm_public_publish=true; publishes ready trips as previews and warning-only incomplete trips with incomplete readiness; blocking findings refuse publication; public overwrite requires confirm_overwrite=true",
            },
        },
        ensure_ascii=False,
    )


@mcp.prompt()
def plan_a_trip(request: str) -> str:
    """Guide a one-question-at-a-time travel planning conversation."""
    return (
        "Help the traveler plan through a deliberate question-and-answer conversation. "
        "Never paste raw tool JSON or schemas as the final answer unless explicitly requested; explain results in concise, natural Traditional Chinese. "
        "Preserve only facts the traveler stated; never fill gaps with assumptions. A highlighted or preselected UI option is not a traveler answer; record a choice only after the traveler explicitly selects or states it. Keep undecided information unknown. "
        "Use parse_trip_request before plan_trip on the accumulated request. If information is missing, "
        "ambiguous, or contradictory, ask exactly ONE concise, specific question in this turn, "
        "then wait for the answer. Ask only for information required to proceed safely or produce a valid plan. Choose the most important unresolved item first (destination, "
        "exact dates, party size and child ages, budget or explicit no-limit preference, origin, "
        "transport). Do not turn the conversation into a long optional-preference questionnaire; after required fields are sufficient, summarize and wait for confirmation. Lodging is not an active search feature: unless the traveler voluntarily supplies lodging details, never ask about lodging location, room allocation/type, or lodging preferences; never search or recommend lodging; keep all lodging fields empty. If children are included but their ages were not stated, "
        "ask for the ages in a separate later turn. Do not present a checklist of questions. "
        "If plan_trip returns needs_clarification, ask only the returned next_question. "
        "After each answer, add it to the accumulated request and parse again; do not discard "
        "previous answers or ask the same resolved question again. If the user cannot answer, "
        "explain briefly why that detail is needed and offer clear choices where possible. "
        "Do not call plan_trip while required fields remain unresolved. Once the request is "
        "complete, show a concise summary of the understood trip and ask the traveler to confirm "
        "that summary and the planning action. If the traveler explicitly requested public publication and a returned URL, state in this confirmation that the trip will be public; that request grants publication consent. Only after explicit confirmation, explain that "
        "plan_trip performs live research and writes/overwrites the named Canonical Trip and "
        "static site files on the MCP service; then call plan_trip with confirm_write=true. "
        "When public publication was explicitly requested and included in that summary, also pass "
        "confirm_public_publish=true; plan_trip publishes after successful planning and returns "
        "publication.url in the same tool result. Do not depend on a separate follow-up publish tool "
        "call for this requested flow. Otherwise pass confirm_public_publish=false. "
        "After a successful plan_trip, call get_trip to read the persisted itinerary. When "
        "presenting a readable or day-by-day itinerary, treat that as asking for current names "
        "of scheduled places unless the traveler requests ID-only output or declines live lookups. "
        "Read get_trip.place_details_needed and call get_place_details once for each listed ID; "
        "include the returned Google Maps and third-party attribution. Do not stop at opaque IDs "
        "or query unselected candidates. Each lookup is a live Places request and may incur usage "
        "charges. Public and MCP lookups share a persistent monthly request budget; if the cap is "
        "reached, stop additional detail lookups and report remaining names as unavailable this month. "
        "If lookup fails, state that the detail is unavailable; do not "
        "reuse stale saved details or invent a value. "
        "When presenting the saved trip, list scheduled visits and meals by date and trip timezone, "
        "show every item's start–end time, include returned current place names and attribution, "
        "and state important validation warnings and incomplete budget or lodging. If arrival/start "
        "or lodging/return routing is unknown, explicitly say the shown activity window excludes "
        "that unverified transfer; do not describe the day as fully route-verified. "
        "Never claim research, availability, opening hours, prices, routes, or validation succeeded "
        "without tool evidence. Planning does not book or pay. After a successful plan, "
        "read the saved trip and present a concise preview. If public publication was explicitly "
        "requested and included in the confirmation summary, plan_trip has already attempted publication "
        "and returned its publication result. Otherwise ask separately whether the traveler approves publishing "
        "these trip details publicly to GitHub Pages and call the tool only after an explicit yes. On "
        "publish_accepted or already_published, "
        "return the tool's url as a clickable link and explain deployment_status accurately: pending "
        "means the new commit's Pages deployment is still running, and not_required means the identical "
        "public page already exists and this call started no deployment. These are the values this tool "
        "returns; never claim deployment finished when it is pending or not_required. If the result is "
        "overwrite_confirmation_required because a different version of this trip is already public, "
        "ask separately whether to replace that page. Only after an explicit yes, retry with both "
        "confirm_public_publish=true and confirm_overwrite=true. A pending deployment means the page "
        "may not be live yet. Never infer publication consent from confirm_write alone; an explicit "
        "request to publish the planned site and return its URL is publication consent.\n\n"
        f"Traveler request:\n{request}"
    )


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport == "stdio":
        mcp.run(transport="stdio")
        return
    if transport == "streamable-http":
        run_http_server()
        return
    raise SystemExit("MCP_TRANSPORT must be 'stdio' or 'streamable-http'")


def run_http_server() -> None:
    """Serve the MCP endpoint behind an internal bearer-token gateway."""
    import hmac

    import uvicorn
    from starlette.responses import JSONResponse, PlainTextResponse

    token = os.environ.get("BEARER_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("BEARER_TOKEN must contain at least 32 characters")

    class InternalBearerAuth:
        def __init__(self, app):
            self.app = app
            self.request_windows: dict[str, tuple[int, float]] = {}

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http" or scope.get("path") == "/health":
                await self.app(scope, receive, send)
                return
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            if (
                scope.get("method") == "GET"
                and re.fullmatch(
                    r"/api/public/trips/[a-z0-9][a-z0-9-]{0,79}/places/[A-Za-z0-9_-]{5,255}",
                    scope.get("path", ""),
                )
            ):
                await self.app(scope, receive, send)
                return
            value = headers.get(b"authorization", b"").decode("latin-1")
            supplied = value[7:] if value.startswith("Bearer ") else ""
            if not hmac.compare_digest(supplied, token):
                await self._reject(send, 401, "unauthorized")
                return
            user_id = headers.get(b"oai-authenticated-user-id", b"").decode("latin-1")
            if not user_id.strip():
                await self._reject(send, 401, "unauthorized")
                return
            content_length = headers.get(b"content-length")
            if content_length:
                try:
                    if int(content_length) < 0:
                        await self._reject(send, 400, "invalid_content_length")
                        return
                    if int(content_length) > _HTTP_MAX_BODY_BYTES:
                        await self._reject(send, 413, "request_too_large")
                        return
                except ValueError:
                    await self._reject(send, 400, "invalid_content_length")
                    return
            now = time.monotonic()
            if not _consume_remote_request(user_id, now, self.request_windows):
                await self._reject(send, 429, "rate_limited")
                return
            messages = await _read_limited_asgi_body(receive, _HTTP_MAX_BODY_BYTES)
            if messages is None:
                await self._reject(send, 413, "request_too_large")
                return
            pending = list(messages)

            async def replay_receive():
                if pending:
                    return pending.pop(0)
                return await receive()

            await self.app(scope, replay_receive, send)

        @staticmethod
        async def _reject(send, status: int, error: str):
            body = json.dumps({"error": error}, separators=(",", ":")).encode()
            await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})

    allowed_hosts = list(_MCP_LOCAL_ALLOWED_HOSTS)
    railway_public_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if railway_public_domain:
        allowed_hosts.append(railway_public_domain)
    allowed_hosts.extend(
        host.strip()
        for host in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    )
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(dict.fromkeys(allowed_hosts)),
        ),
    )

    async def health(_request):
        return PlainTextResponse("ok")

    pages_base_url = os.environ.get("GITHUB_PAGES_BASE_URL", "https://jackytsai70113.github.io/ai-travel-planner")
    try:
        allowed_public_origin = _github_pages_origin(pages_base_url)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    public_request_windows: dict[str, tuple[int, float]] = {}
    public_request_lock = threading.Lock()

    def public_place_name(request):
        origin = request.headers.get("origin", "")
        response_headers = {
            "Cache-Control": "no-store, max-age=0",
            "Vary": "Origin",
            "X-Content-Type-Options": "nosniff",
        }
        if origin != allowed_public_origin:
            return JSONResponse({"status": "forbidden"}, status_code=403, headers=response_headers)
        response_headers["Access-Control-Allow-Origin"] = allowed_public_origin
        client = request.scope.get("client")
        remote_id = client[0] if isinstance(client, (tuple, list)) and client else "unknown"
        with public_request_lock:
            if not _consume_remote_request(
                remote_id, time.monotonic(), public_request_windows, limit=_PUBLIC_PLACE_REQUEST_LIMIT
            ):
                return JSONResponse({"status": "rate_limited"}, status_code=429, headers=response_headers)
        slug = request.path_params.get("slug", "")
        place_id = request.path_params.get("place_id", "")
        if not _GOOGLE_PLACE_ID.fullmatch(place_id):
            return JSONResponse({"status": "not_found"}, status_code=404, headers=response_headers)
        scheduled_place_ids = _published_scheduled_google_place_ids(slug, pages_base_url)
        if place_id not in scheduled_place_ids:
            return JSONResponse({"status": "not_found"}, status_code=404, headers=response_headers)
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
        if not api_key:
            return JSONResponse({"status": "unavailable"}, status_code=503, headers=response_headers)
        if not _consume_google_places_monthly_budget():
            return JSONResponse({"status": "monthly_limit_reached"}, status_code=429, headers=response_headers)
        try:
            details = GooglePlacesAdapter(api_key=api_key).get_place_display_name(place_id)
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=502, headers=response_headers)
        return JSONResponse(details, headers=response_headers)

    app.add_route("/health", health, methods=["GET"])
    app.add_route(
        "/api/public/trips/{slug:str}/places/{place_id:str}",
        public_place_name,
        methods=["GET"],
        name="public-place-name",
    )
    app.add_middleware(InternalBearerAuth)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), access_log=False)


if __name__ == "__main__":
    main()
