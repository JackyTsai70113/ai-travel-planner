"""Build one validated Canonical Trip into a public trip-site artifact."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.web_publisher import build_trip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trip", type=Path, required=True)
    parser.add_argument("--site-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("site"))
    args = parser.parse_args()
    result = build_trip(args.trip, args.site_config, args.output)
    print(f"built {result.trip_id} at {result.output_dir} ({result.readiness})")


if __name__ == "__main__":
    main()
