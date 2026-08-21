from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import build_all, build_trip, init_site, load_config
from src.schemas.validate_trip import validate_trip


def main() -> None:
    parser = argparse.ArgumentParser(prog="python3 -m src.web_publisher")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--trip", type=Path, required=True)
    validate.add_argument("--site-config", type=Path, required=True)
    build = commands.add_parser("build")
    build.add_argument("--trip", type=Path, required=True)
    build.add_argument("--site-config", type=Path, required=True)
    build.add_argument("--output", type=Path, default=Path("site"))
    build_all_command = commands.add_parser("build-all")
    build_all_command.add_argument("--configs", type=Path, default=Path("site-configs"))
    build_all_command.add_argument("--output", type=Path, default=Path("site"))
    preview = commands.add_parser("preview")
    preview.add_argument("--trip", type=Path, required=True)
    preview.add_argument("--site-config", type=Path, required=True)
    preview.add_argument("--output", type=Path, default=Path("site"))
    init = commands.add_parser("init")
    init.add_argument("--trip-id", required=True)
    init.add_argument("--slug", required=True)
    init.add_argument("--theme", required=True)
    init.add_argument("--output", type=Path, default=Path("site-configs"))
    args = parser.parse_args()
    if args.command == "validate":
        config = load_config(args.site_config)
        trip = json.loads(args.trip.read_text(encoding="utf-8"))
        validate_trip(trip)
        print(json.dumps({"status": "valid", "trip_id": config["trip_id"]}, ensure_ascii=False))
    elif args.command in {"build", "preview"}:
        result = build_trip(args.trip, args.site_config, args.output)
        print(json.dumps({"status": result.readiness, "trip_id": result.trip_id, "output": str(result.output_dir)}, ensure_ascii=False))
    elif args.command == "build-all":
        results = build_all(args.configs, args.output)
        print(json.dumps({"status": "complete", "trips": [result.slug for result in results]}, ensure_ascii=False))
    else:
        config, media = init_site(args.trip_id, args.slug, args.theme, args.output / args.trip_id)
        print(json.dumps({"status": "scaffolded", "config": str(config), "media": str(media)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
