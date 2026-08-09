"""End-user planning command; production never substitutes fixture data."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from src.intent import parse_trip_request
from src.renderer.build_site import build_site
from src.schemas.validate_trip import validate_trip

_REQUIRED_KEYS = ("GOOGLE_MAPS_API_KEY", "YOUTUBE_API_KEY", "AMADEUS_CLIENT_ID", "AMADEUS_CLIENT_SECRET", "OPENROUTESERVICE_API_KEY")


def _missing_configuration() -> list[str]:
    return [name for name in _REQUIRED_KEYS if not os.getenv(name)]


def plan_command(args: argparse.Namespace) -> int:
    intent = parse_trip_request(args.request)
    missing = _missing_configuration()
    if missing and not args.demo:
        print(json.dumps({"status": "configuration_missing", "missing": missing, "message": "Production planning requires real provider credentials; no fixture fallback was used."}, ensure_ascii=False), file=sys.stderr)
        return 2
    if not args.demo:
        print(json.dumps({"status": "configuration_ready", "intent": intent.as_dict(), "message": "Provider composition is configured; live booking/search results remain unverified until each provider responds."}, ensure_ascii=False))
        return 0
    fixture = Path("fixtures/trips/japan-5-day-trip-v1.json")
    trip = json.loads(fixture.read_text(encoding="utf-8"))
    trip["id"] = args.trip_id
    trip["title"] = f"Demo: {args.request}"
    validate_trip(trip)
    trip_path = Path("trips") / args.trip_id / "trip.json"
    site_path = Path("site") / args.trip_id / "index.html"
    trip_path.parent.mkdir(parents=True, exist_ok=True); site_path.parent.mkdir(parents=True, exist_ok=True)
    trip_path.write_text(json.dumps(trip, ensure_ascii=False, indent=2), encoding="utf-8")
    site_path.write_text(build_site(trip), encoding="utf-8")
    print(json.dumps({"status": "demo_complete", "intent": intent.as_dict(), "trip": str(trip_path), "site": str(site_path)}, ensure_ascii=False))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan a trip from a natural-language request")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--request", required=True)
    plan.add_argument("--trip-id", default="planned-trip")
    plan.add_argument("--demo", action="store_true", help="explicit recorded fixture demonstration; never used by production default")
    plan.set_defaults(handler=plan_command)
    args = parser.parse_args(); raise SystemExit(args.handler(args))


if __name__ == "__main__": main()
