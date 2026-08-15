"""Import Google Maps place list share link into a trip-ready JSON payload."""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass
from urllib.request import urlopen
from urllib.error import URLError
from pathlib import Path


MAP_LIST_URL = "https://maps.app.goo.gl/d8uJyAX5x9ba8P2g6?g_st=i"
USER_AGENT = "Mozilla/5.0 (compatible; ai-travel-planner-maps-import/1.0)"
DEFAULT_OUTPUT = Path("docs/trips/awaji-2026/maps-import-output.json")


@dataclass(frozen=True)
class MapCandidate:
    source_id: int
    name: str
    address: str
    latitude: float
    longitude: float


def _fetch_url(url: str) -> str:
    req = urlopen(url, timeout=20)
    with req as response:
        return response.read().decode("utf-8", errors="replace")


def _find_entity_list_url(html_text: str) -> str:
    match = re.search(r"/maps/preview/entitylist/getlist[^\"']+", html_text)
    if not match:
        raise RuntimeError("Cannot find maps entitylist payload in response")
    return "https://www.google.com" + html.unescape(match.group(0))


def _parse_list_response(raw: str) -> list[tuple[object, ...]]:
    if not raw.startswith(")]}'"):
        raise RuntimeError("Unexpected payload header")
    payload = json.loads(raw[4:])
    entries = payload[0][8]
    if not isinstance(entries, list):
        raise RuntimeError("Entity payload missing list entries")
    return entries


def _normalize_entry(entry: object) -> MapCandidate | None:
    if not isinstance(entry, list) or len(entry) < 2:
        return None
    item = entry[1]
    if not isinstance(item, list) or len(item) <= 5:
        return None
    full_name = item[2]
    short_name = entry[2] if len(entry) > 2 and isinstance(entry[2], str) else None
    if not isinstance(full_name, str) or "," not in full_name:
        return None
    if not isinstance(item[4], str) or len(item[4].strip()) < 4:
        return None
    coords = item[5]
    if not isinstance(coords, list) or len(coords) < 4:
        return None
    latitude = float(coords[2])
    longitude = float(coords[3])
    if not all(isinstance(value, (int, float)) for value in (latitude, longitude)):
        return None
    address = item[4].replace("\u3000", " ").replace("日本", "").strip(" ,")
    return MapCandidate(
        source_id=len(full_name),
        name=(short_name or full_name.split(",", 1)[0]).strip() or "maps-import-place",
        address=address,
        latitude=latitude,
        longitude=longitude,
    )


def _is_awaji_or_naruto(candidate: MapCandidate) -> bool:
    text = f"{candidate.name} {candidate.address}".lower()
    return any(tag in text for tag in ("awaji", "minamiawaji", "sumoto", "naruto", "hyogo", "tokushima"))


def build_candidates() -> dict:
    try:
        html_text = _fetch_url(MAP_LIST_URL)
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch map link: {exc}") from exc

    payload_url = _find_entity_list_url(html_text)
    try:
        payload_text = _fetch_url(payload_url)
        entries = _parse_list_response(payload_text)
    except (URLError, RuntimeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to parse map payload: {exc}") from exc

    accepted: list[MapCandidate] = []
    excluded: list[MapCandidate] = []
    for entry in entries:
        normalized = _normalize_entry(entry)
        if not normalized:
            continue
        if _is_awaji_or_naruto(normalized):
            accepted.append(normalized)
        else:
            excluded.append(normalized)

    return {
        "source_map_url": MAP_LIST_URL,
        "accepted_count": len(accepted),
        "excluded_count": len(excluded),
        "accepted": [
            {
                "name": c.name,
                "address": c.address,
                "coordinates": {"lat": c.latitude, "lng": c.longitude},
                "import_note": "awaji_or_naruto"
            }
            for c in accepted
        ],
        "excluded": [
            {
                "name": c.name,
                "address": c.address,
                "coordinates": {"lat": c.latitude, "lng": c.longitude},
                "import_note": "outside_awaji_naruto_scope",
            }
            for c in excluded
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Awaji/Naruto Maps list")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()

    result = build_candidates()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.print:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"awaji/naruto map import wrote {args.output}")
        print(f"accepted: {result['accepted_count']}  excluded: {result['excluded_count']}")


if __name__ == "__main__":
    main()
