#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from media.pipeline import MediaValidationError, validate_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate trip media attribution and source policy.")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        errors = validate_manifest(manifest, args.manifest.parent)
    except (OSError, json.JSONDecodeError, MediaValidationError) as error:
        parser.error(str(error))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"validated {len(manifest['assets'])} media assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
