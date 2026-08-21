#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from media.pipeline import MediaValidationError, build


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic trip media manifest and hashed fallback variants.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build(args.manifest, args.output)
    except (OSError, json.JSONDecodeError, MediaValidationError) as error:
        parser.error(str(error))
    print(f"built {len(result['assets'])} media assets for {result['tripId']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
