"""MCP server exposing the existing travel planning boundaries."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from src.application.production import (
    ProductionConfigurationError,
    ProductionIncompleteError,
    create_production_orchestrator,
    missing_required_configuration,
)
from src.intent import parse_trip_request
from src.renderer.build_site import build_site
from src.schemas.validate_trip import TripValidationError, validate_trip
from src.validator import ValidationContext, validate_itinerary

_TRIP_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_TRIPS_DIR = Path(os.environ.get("TRAVEL_PLANNER_TRIPS_DIR", "trips")).resolve()
_SITE_DIR = Path(os.environ.get("TRAVEL_PLANNER_SITE_DIR", "site")).resolve()
_HTTP_REQUEST_LIMIT = 120
_HTTP_WINDOW_SECONDS = 60
_HTTP_MAX_BODY_BYTES = 4 * 1024 * 1024

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
    return {
        "schema_version": trip.get("schema_version"),
        "id": trip.get("id"),
        "title": trip.get("title"),
        "local_timezone": trip.get("local_timezone"),
        "date_range": date_range,
        "days": days,
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
    """Run production planning; writes Canonical Trip and site files only when confirm_write is true."""
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
    if intent.missing_fields or intent.ambiguous_fields or intent.constraint_issues:
        return {
            "status": "needs_clarification",
            "intent": intent_data,
            "missing_fields": intent_data["missing_fields"],
            "ambiguous_fields": intent_data["ambiguous_fields"],
            "constraint_issues": intent_data["constraint_issues"],
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
    return {
        "status": "complete" if result.succeeded else "incomplete",
        "trip_id": trip_id,
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
    """Guide a travel planning conversation while preserving explicit facts and uncertainty."""
    return (
        "Plan a trip from this request. Preserve only facts the traveler stated; "
        "ask about missing or ambiguous dates, travelers, budget, origin, and transport. "
        "Use parse_trip_request before plan_trip. Never claim research, availability, "
        "opening hours, prices, routes, or validation succeeded without tool evidence. "
        "Before any tool writes local files, explain the exact side effect and obtain confirmation, "
        "then call plan_trip with confirm_write=true.\n\n"
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
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse, PlainTextResponse

    request_windows: dict[str, tuple[int, float]] = {}

    token = os.environ.get("MCP_BACKEND_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("MCP_BACKEND_TOKEN must contain at least 32 characters")

    class InternalBearerAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path == "/health":
                return await call_next(request)
            value = request.headers.get("authorization", "")
            supplied = value[7:] if value.startswith("Bearer ") else ""
            if not hmac.compare_digest(supplied, token):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            user_id = request.headers.get("oai-authenticated-user-id", "")
            if not user_id.strip():
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > _HTTP_MAX_BODY_BYTES:
                        return JSONResponse({"error": "request_too_large"}, status_code=413)
                except ValueError:
                    return JSONResponse({"error": "invalid_content_length"}, status_code=400)
            now = time.monotonic()
            if not _consume_remote_request(user_id, now, request_windows):
                return JSONResponse({"error": "rate_limited"}, status_code=429)
            return await call_next(request)

    app = mcp.streamable_http_app(
        streamable_http_path="/mcp", json_response=True, stateless_http=True
    )

    async def health(_request):
        return PlainTextResponse("ok")

    app.add_route("/health", health, methods=["GET"])
    app.user_middleware.insert(0, Middleware(InternalBearerAuth))
    app.middleware_stack = app.build_middleware_stack()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), access_log=False)


if __name__ == "__main__":
    main()
