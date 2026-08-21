"""Build every site config and emit one deterministic multi-trip registry."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.web_publisher import build_all


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", type=Path, default=Path("site-configs"))
    parser.add_argument("--output", type=Path, default=Path("site"))
    args = parser.parse_args()
    results = build_all(args.configs, args.output)
    print(f"built {len(results)} trip sites at {args.output}")


if __name__ == "__main__":
    main()
