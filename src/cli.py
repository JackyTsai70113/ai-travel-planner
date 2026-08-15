"""End-user planning command; production never substitutes fixture data."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.intent import parse_trip_request
from src.application.production import (
    ProductionConfigurationError,
    ProductionIncompleteError,
    create_production_orchestrator,
    missing_required_configuration,
)
from src.renderer.build_site import build_site
from src.schemas.validate_trip import validate_trip

def plan_command(args: argparse.Namespace) -> int:
    intent = parse_trip_request(args.request)
    missing = missing_required_configuration()
    if missing and not args.demo:
        print(json.dumps({"status": "configuration_missing", "missing": missing, "message": "Production planning requires real provider credentials; no fixture fallback was used."}, ensure_ascii=False), file=sys.stderr)
        return 2
    if not args.demo:
        try:
            result = create_production_orchestrator(
                trip_id=args.trip_id,
                trips_directory=Path(args.trips_directory),
                site_directory=Path(args.site_directory),
            ).run(intent)
        except (ProductionConfigurationError, ProductionIncompleteError, ValueError) as exc:
            print(json.dumps({"status": "incomplete", "intent": intent.as_dict(), "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        status = "complete" if result.succeeded else "incomplete"
        payload = {
            "status": status,
            "intent": intent.as_dict(),
            "trip": str(result.trip_path) if result.trip_path else None,
            "site": str(result.render_path) if result.render_path else None,
            "stages": [{"name": stage.name.value, "status": stage.status.value} for stage in result.stages],
            "warnings": [warning.as_dict() for warning in result.warnings],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if result.succeeded else 1
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
    plan.add_argument("--trips-directory", default="trips")
    plan.add_argument("--site-directory", default="site")
    plan.add_argument("--demo", action="store_true", help="explicit recorded fixture demonstration; never used by production default")
    plan.set_defaults(handler=plan_command)
    args = parser.parse_args(); raise SystemExit(args.handler(args))


if __name__ == "__main__": main()
