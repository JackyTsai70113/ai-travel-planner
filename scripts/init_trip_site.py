"""Scaffold a site config without inventing itinerary or media facts."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.web_publisher import init_site


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trip-id", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--theme", required=True)
    parser.add_argument("--output", type=Path, default=Path("site-configs"))
    args = parser.parse_args()
    config, media = init_site(args.trip_id, args.slug, args.theme, args.output / args.trip_id)
    print(f"created {config} and {media}; canonical trip data was not generated")


if __name__ == "__main__":
    main()
