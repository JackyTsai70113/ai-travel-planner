"""將已驗證的 Canonical Trip 投影為 registry-driven 行程網站資料。

此模組只負責發布轉接，不會研究、排程或修復行程；這些決策仍由 production
orchestrator 與其 Canonical Trip output 負責。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping

from src.intent import TravelIntent, parse_trip_request
from src.intent.contracts import FieldProvenance, TravelerGroup


_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*\Z")


class RequestNotReadyError(ValueError):
    """需求不足以進行如實的 production planning 時拋出。"""


@dataclass(frozen=True)
class RequestSiteResult:
    slug: str
    bundle_path: Path
    registry_path: Path
    canonical_url: str


def parse_site_request(text: str) -> TravelIntent:
    """解析共用需求契約，並補上明確口語成人數。

    共用 parser 仍負責一般需求語意。此窄介面只接受網站入口中無歧義的
    ``兩個人``／``2個人``，並保留精確來源位置。
    """
    intent = parse_trip_request(text)
    if intent.travelers.adults is not None:
        return intent
    match = re.search(r"([\d一二三四五六七八九十兩]+)\s*(?:個人|人)", text)
    if match is None:
        return intent
    number = _chinese_number(match.group(1))
    if number is None or number < 1:
        return intent
    provenance = dict(intent.provenance)
    provenance["adults"] = (*provenance.get("adults", ()), FieldProvenance(match.group(0), match.start(), match.end(), "adults"))
    missing = tuple(item for item in intent.missing_fields if item.field != "travelers")
    return replace(intent, travelers=TravelerGroup(number, intent.travelers.children, intent.travelers.child_ages), missing_fields=missing, provenance=provenance)


def required_request_fields(intent: TravelIntent) -> list[str]:
    """回傳 production blocker，不虛構目的地或日期。"""
    fields: list[str] = []
    if not intent.destinations:
        fields.append("destination")
    if not intent.start_date or not intent.end_date:
        fields.append("exact_date_range")
    if intent.travelers.adults is None:
        fields.append("adult_count")
    return fields


def assert_request_ready(intent: TravelIntent) -> None:
    fields = required_request_fields(intent)
    if fields:
        labels = {
            "destination": "可辨識的目的地",
            "exact_date_range": "完整起訖日期",
            "adult_count": "成人數",
        }
        raise RequestNotReadyError("尚不能開始規劃；請補充：" + "、".join(labels[field] for field in fields))


def publish_request_site(trip: Mapping[str, Any], *, slug: str, public_root: Path) -> RequestSiteResult:
    """寫入前端相容投影，並登錄至旅程 catalog。

    產出資料放在 repository 的 ``trips/requested`` 下方，避免與人工維護的
    trip source 衝突。部署 URL 仍藉由 ``bundle_source_slug`` 對應為
    ``trips/<slug>/``。
    """
    if not _SLUG.fullmatch(slug):
        raise ValueError("site slug 僅可使用小寫英文字母、數字與連字號")
    _require_trip_basics(trip)
    bundle = trip_to_public_bundle(trip)
    source_slug = f"requested/{slug}"
    bundle_path = public_root / "trips" / source_slug / "public-bundle.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(bundle_path, bundle)

    registry_path = public_root / "trip-registry.json"
    registry = _load_registry(registry_path)
    entry = trip_to_registry_entry(trip, slug=slug, source_slug=source_slug)
    registry = [item for item in registry if item.get("slug") != slug]
    registry.append(entry)
    _write_json(registry_path, registry)
    return RequestSiteResult(slug, bundle_path, registry_path, f"trips/{slug}")


def trip_to_public_bundle(trip: Mapping[str, Any]) -> dict[str, Any]:
    """只投影 React runtime 需要的 Canonical Trip allowlist 欄位。"""
    _require_trip_basics(trip)
    candidate_sets = _mapping(trip.get("candidate_sets"))
    places = _public_places(candidate_sets)
    validation = [_public_validation(value) for value in _sequence(trip.get("validation")) if isinstance(value, Mapping)]
    has_error = any(item["severity"] in {"error", "critical"} for item in validation)
    has_warning = bool(validation)
    profile = _mapping(trip.get("traveler_profile"))
    children = [child for child in _sequence(profile.get("children")) if isinstance(child, Mapping)]
    budget = _mapping(trip.get("budget"))
    currency = str(budget.get("currency") or "JPY")
    total = _mapping(budget.get("total"))
    categories = {
        str(name): _money(value, currency)
        for name, value in _mapping(budget.get("categories")).items()
        if isinstance(value, Mapping)
    }
    return {
        "trip_id": str(trip["id"]),
        "title": str(trip["title"]),
        "status": "error" if has_error else ("warning" if has_warning else "ok"),
        "local_timezone": str(trip.get("local_timezone") or "Asia/Tokyo"),
        "date_range": dict(_mapping(trip.get("date_range"))),
        "traveler_profile": {
            "adults": int(profile.get("adults") or 0),
            "children_count": len(children),
            "children_ages": [child["age"] for child in children if isinstance(child.get("age"), int)],
        },
        "places": places,
        "selected": {key: list(_sequence(_mapping(trip.get("selected")).get(key))) for key in ("hotel_place_ids", "flight_ids")},
        "days": [_public_day(day) for day in _sequence(trip.get("days")) if isinstance(day, Mapping)],
        "transport_legs": [_public_leg(leg) for leg in _sequence(candidate_sets.get("transport_legs")) if isinstance(leg, Mapping)],
        "reservations": [],
        "preferences": _public_preferences(_mapping(trip.get("preferences"))),
        "budget": {"currency": currency, "total": _money(total, currency), "categories": categories},
        "validation": validation,
        "meta": {"generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()},
    }


def trip_to_registry_entry(trip: Mapping[str, Any], *, slug: str, source_slug: str) -> dict[str, Any]:
    profile = _mapping(trip.get("traveler_profile"))
    adults = int(profile.get("adults") or 0)
    children = len(_sequence(profile.get("children")))
    date_range = _mapping(trip.get("date_range"))
    validation = [_public_validation(value) for value in _sequence(trip.get("validation")) if isinstance(value, Mapping)]
    readiness = "blocked" if any(item["severity"] in {"error", "critical"} for item in validation) else ("incomplete" if validation else "ready")
    destinations = _destination_regions(trip)
    generated = datetime.now(timezone.utc).date().isoformat()
    return {
        "slug": slug,
        "canonical_url": f"trips/{slug}",
        "bundle_source_slug": source_slug,
        "title": str(trip["title"]),
        "short_title": str(trip["title"]),
        "destination_regions": destinations,
        "date_range": {"start_date": str(date_range["start_date"]), "end_date": str(date_range["end_date"])},
        "duration_days": len(_sequence(trip.get("days"))),
        "travelers_summary": f"{adults} 位大人" + (f"、{children} 位小孩" if children else ""),
        "theme_id": "generic-japan",
        "status": "preview",
        "readiness": readiness,
        "last_generated": generated,
        "last_verified": generated,
        "tags": ["generated-request", "needs-review"],
        "cover_media": {"kind": "gradient", "gradient": "linear-gradient(130deg, #334155 0%, #d97706 55%, #fbbf24 100%)", "fallback": "日本旅行規劃"},
        "hero_summary": f"{('、'.join(destinations) or '日本')}的每日行程、餐飲、住宿與導航資訊。",
        "key_messages": ["依即時研究資料產生，出發前請重新確認動態資訊。"],
        "critical_alert_count": sum(item["severity"] in {"error", "critical"} for item in validation),
    }


def _require_trip_basics(trip: Mapping[str, Any]) -> None:
    required = ("id", "title", "date_range", "traveler_profile", "days", "budget")
    missing = [key for key in required if key not in trip]
    dates = _mapping(trip.get("date_range"))
    if not dates.get("start_date") or not dates.get("end_date"):
        missing.append("date_range.start_date/end_date")
    if missing:
        raise ValueError("Canonical Trip 資料不完整：" + ", ".join(missing))


def _public_places(candidate_sets: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for collection in ("places", "restaurants", "hotels"):
        for candidate in _sequence(candidate_sets.get(collection)):
            if not isinstance(candidate, Mapping):
                continue
            place = _mapping(candidate.get("place")) if isinstance(candidate.get("place"), Mapping) else candidate
            identifier = place.get("id")
            if not isinstance(identifier, str) or identifier in seen:
                continue
            seen.add(identifier)
            result.append({key: place[key] for key in ("id", "name", "address", "kind", "maps_query", "official_url", "opening_hours_note", "parking", "accessibility_notes") if key in place})
    return result


def _public_day(day: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "date": str(day.get("date") or ""),
        "summary": str(day.get("summary") or ""),
        "items": [
            {key: item.get(key) for key in ("id", "kind", "start_at", "end_at", "place_id", "notes", "optional", "fixed", "expected_stay_minutes", "transfer_minutes", "buffer_minutes", "transport_leg_id") if key in item}
            for item in _sequence(day.get("items")) if isinstance(item, Mapping)
        ],
    }


def _public_leg(leg: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(leg.get("id") or ""), "mode": str(leg.get("mode") or "driving"),
        "status": str(leg.get("status") or "unknown"),
        "from_place": str(leg.get("from_place") or leg.get("from_place_id") or ""),
        "to_place": str(leg.get("to_place") or leg.get("to_place_id") or ""),
        "from_label": str(leg.get("from_label") or leg.get("from_place") or leg.get("from_place_id") or ""),
        "to_label": str(leg.get("to_label") or leg.get("to_place") or leg.get("to_place_id") or ""),
        "departure_at": leg.get("departure_at"), "arrival_at": leg.get("arrival_at"),
        "estimated_duration_minutes": leg.get("estimated_duration_minutes"),
        "distance_km": leg.get("distance_km"), "note": leg.get("note"),
    }


def _public_preferences(preferences: Mapping[str, Any]) -> dict[str, list[dict[str, str]]]:
    return {
        "hard_constraints": [{"id": str(item.get("id") or ""), "description": str(item.get("value") or item.get("kind") or "")} for item in _sequence(preferences.get("hard_constraints")) if isinstance(item, Mapping)],
        "soft_preferences": [{"id": str(item.get("id") or ""), "description": str(item.get("value") or item.get("kind") or "")} for item in _sequence(preferences.get("soft_preferences")) if isinstance(item, Mapping)],
    }


def _public_validation(value: Mapping[str, Any]) -> dict[str, str]:
    severity = str(value.get("severity") or "warning")
    if severity not in {"error", "critical", "warning", "info", "unverified", "stale", "conflict", "unknown", "pass", "passed", "ok"}:
        severity = "warning"
    return {"code": str(value.get("code") or "validation"), "message": str(value.get("message") or value.get("code") or "驗證提醒"), "severity": severity}


def _destination_regions(trip: Mapping[str, Any]) -> list[str]:
    title = str(trip.get("title") or "")
    return [title.removesuffix(" 行程")] if title else []


def _money(value: Mapping[str, Any], currency: str) -> dict[str, Any]:
    amount = value.get("amount")
    return {"amount": amount if isinstance(amount, (int, float)) else 0, "currency": str(value.get("currency") or currency)}


def _load_registry(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{path} 必須是 registry entry 的 JSON array")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _chinese_number(value: str) -> int | None:
    if value.isdecimal():
        return int(value)
    digits = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if value in digits:
        return digits[value]
    if len(value) == 2 and value.endswith("十") and value[0] in digits:
        return digits[value[0]] * 10
    if len(value) == 2 and value.startswith("十") and value[1] in digits:
        return 10 + digits[value[1]]
    if len(value) == 3 and value[1] == "十" and value[0] in digits and value[2] in digits:
        return digits[value[0]] * 10 + digits[value[2]]
    return None
