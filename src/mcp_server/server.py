"""MCP server exposing the existing travel planning boundaries."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from src.budget import format_budget_summary
from src.application.production import (
    ProductionConfigurationError,
    ProductionIncompleteError,
    create_production_orchestrator,
    missing_required_configuration,
)
from src.intent import parse_trip_request
from src.orchestrator import StageStatus
from src.renderer.build_site import build_site
from src.schemas.validate_trip import TripValidationError, validate_trip
from src.validator import ValidationContext, validate_itinerary

_TRIP_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_TRIPS_DIR = Path(os.environ.get("TRAVEL_PLANNER_TRIPS_DIR", "trips")).resolve()
_SITE_DIR = Path(os.environ.get("TRAVEL_PLANNER_SITE_DIR", "site")).resolve()
_HTTP_REQUEST_LIMIT = 120
_HTTP_WINDOW_SECONDS = 60
_HTTP_MAX_BODY_BYTES = 4 * 1024 * 1024
_MCP_LOCAL_ALLOWED_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")

mcp = MCPServer(
    "ai-travel-planner",
    instructions="Use Canonical Trip V1 as the sole trip record. Preserve unknown facts. Ask for confirmation before tools write local files.",
)


def _consume_remote_request(
    user_id: str,
    now: float,
    windows: dict[str, tuple[int, float]],
) -> bool:
    """Apply a per-user fixed-window limit; state is held only in process memory."""
    count, window_started = windows.get(user_id, (0, now))
    if now - window_started >= _HTTP_WINDOW_SECONDS:
        count, window_started = 0, now
    if count >= _HTTP_REQUEST_LIMIT:
        return False
    if user_id not in windows and len(windows) >= 10_000:
        expired = [key for key, (_, started) in windows.items() if now - started >= _HTTP_WINDOW_SECONDS]
        for key in expired:
            windows.pop(key, None)
        if len(windows) >= 10_000:
            return False
    windows[user_id] = (count + 1, window_started)
    return True


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
        place["id"]: {key: place[key] for key in ("id", "name", "kind") if key in place}
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
    """Parse an explicit natural-language travel request without researching or inventing missing facts."""
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
    """Read a bounded public summary of an existing Canonical Trip by safe trip ID."""
    try:
        path = _trip_path(trip_id)
        trip = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"status": "not_found", "trip_id": trip_id}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"status": "error", "message": str(exc)}
    try:
        summary = _public_trip_summary(trip)
    except (AttributeError, KeyError, TypeError) as exc:
        return {
            "status": "invalid",
            "message": f"trip summary cannot be projected: {exc}",
        }
    return {"status": "ok", "trip": summary}


@mcp.tool(
    name="plan_trip",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
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
) -> dict[str, Any]:
    """Research and plan a trip after the user has answered clarifications and confirmed local file writes."""
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
        return {
            "status": "confirmation_required",
            "message": "Call again with confirm_write=true to create trip and site files.",
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
    except (ProductionIncompleteError, ValueError):
        return {
            "status": "incomplete",
            "message": "Planning could not complete; check local configuration and trip feasibility.",
        }
    canonical_trip = getattr(result, "trip", None)
    trip_budget = canonical_trip.get("budget") if isinstance(canonical_trip, dict) else None
    return {
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
                )
                if value
            }
            for warning in result.warnings
        ],
    }


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
        trip = json.loads(path.read_text(encoding="utf-8"))
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
                "get_trip": "read-only; returns allowlisted public fields",
                "plan_trip": "requires confirm_write=true; performs live provider research and writes local trip/site files",
                "build_trip_site": "requires confirm_write=true; writes a local static site; never deploys",
            },
        },
        ensure_ascii=False,
    )


@mcp.prompt()
def plan_a_trip(request: str) -> str:
    """Guide a one-question-at-a-time travel planning conversation."""
    return (
        "Help the traveler plan through a deliberate question-and-answer conversation. "
        "Preserve only facts the traveler stated; never fill gaps with assumptions. "
        "Use parse_trip_request before plan_trip on the accumulated request. If information is missing, "
        "ambiguous, or contradictory, ask exactly ONE concise, specific question in this turn, "
        "then wait for the answer. Choose the most important unresolved item first (destination, "
        "exact dates, party size and child ages, budget or explicit no-limit preference, origin, "
        "transport, then useful preferences). If children are included but their ages were not stated, "
        "ask for the ages in a separate later turn. Do not present a checklist of questions. "
        "If plan_trip returns needs_clarification, ask only the returned next_question. "
        "After each answer, add it to the accumulated request and parse again; do not discard "
        "previous answers or ask the same resolved question again. If the user cannot answer, "
        "explain briefly why that detail is needed and offer clear choices where possible. "
        "Do not call plan_trip while required fields remain unresolved. Once the request is "
        "complete, show a concise summary of the understood trip and ask the traveler to confirm "
        "that summary and the planning action. Only after explicit confirmation, explain that "
        "plan_trip performs live research and writes/overwrites the named Canonical Trip and "
        "static site files on the MCP service; then call plan_trip with confirm_write=true. "
        "Never claim research, availability, opening hours, prices, routes, or validation succeeded "
        "without tool evidence. Planning does not book, pay, or publish the site.\n\n"
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
    from starlette.responses import PlainTextResponse

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

    app.add_route("/health", health, methods=["GET"])
    app.add_middleware(InternalBearerAuth)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), access_log=False)


if __name__ == "__main__":
    main()
