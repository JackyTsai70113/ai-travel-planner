"""Deterministic contingency derivation for an already validated Trip V1."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.conditions import (
    ConditionDecisionMode,
    ConditionKind,
    ConditionPolicy,
    ConditionSnapshot,
    evaluate_condition_gate,
    load_condition_snapshot,
)

from src.validator import BudgetLimit, OpeningInterval, ValidationContext, validate_itinerary
from src.validator.itinerary import Outcome

TRIGGER_CONDITION_KINDS = {
    "rain": ConditionKind.WEATHER,
    "queue": ConditionKind.CROWD,
    "closure": ConditionKind.CLOSURE,
}

TRIGGER_PRIORITIES = {
    "rain": "high",
    "delay": "high",
    "queue": "medium",
    "parking_full": "medium",
    "closure": "medium",
    "fatigue": "low",
    "shortened_day": "low",
}
TRIGGER_ORDER = ("rain", "delay", "queue", "parking_full", "closure", "fatigue", "shortened_day")

TRIGGER_LABELS = {
    "rain": "天氣風險",
    "delay": "延誤風險",
    "queue": "排隊 / 無法入座",
    "parking_full": "停車位滿位",
    "closure": "景點關閉",
    "fatigue": "體力不足",
    "shortened_day": "行程縮短",
}

INSTRUCTIONS = {
    "rain": "在惡劣天候時改為同日室內替代，保留原日原時段。",
    "delay": "若出現塞車或延誤，優先切換到同類型短距替代項目並保留原旅館。",
    "queue": "若餐廳排隊、售罄或到位時間過長，改採同區較短用餐替代。",
    "parking_full": "如停車場滿位，改以步行/共乘接駁到附近替代點。",
    "closure": "若場域臨時關閉，改為同區可供預約的替代場域。",
    "fatigue": "若出現明顯體力不足，將行程降級為近距與較短停留。",
    "shortened_day": "若前段嚴重延誤，將本日後段項目改為可刪減項目。",
}


@dataclass(frozen=True)
class _Candidate:
    place_id: str
    name: str
    provenance: dict[str, Any]
    kind: str


def analyze_contingencies(trip: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic alternatives for common disruption triggers.

    Output is a derived read model; the canonical Trip is not modified.
    """
    if not isinstance(trip, dict):
        return {"contingencies": []}

    day_sets = trip.get("days")
    if not isinstance(day_sets, list):
        return {"contingencies": []}

    candidate_places = _index_candidates(trip)
    context = _validation_context(trip)
    condition_snapshot = _load_condition_snapshot(trip.get("conditions"))
    contingencies: list[dict[str, Any]] = []

    for day_index, day in enumerate(day_sets):
        if not isinstance(day, dict):
            continue
        items = day.get("items")
        if not isinstance(items, list):
            continue
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            if item.get("kind") in {"transport", "check_in", "check_out", "flight", "hotel", "airport"}:
                continue
            place_id = item.get("place_id")
            if not isinstance(place_id, str) or place_id not in candidate_places:
                continue
            for trigger in _triggers_for_item(day_index, item_index, item, trip, items, context, candidate_places):
                contingencies.append(
                    _build_contingency(
                        trip,
                        day_index,
                        item_index,
                        item,
                        trigger,
                        candidate_places,
                        context,
                        condition_snapshot,
                    )
                )

    contingencies.sort(
        key=lambda item: (
            TRIGGER_ORDER.index(item["trigger"]),
            item["priority"],
            item["day_index"],
            item["item"]["index"],
        )
    )
    return {
        "contingencies": contingencies,
        "generated_at": datetime.now().replace(microsecond=0).isoformat() + "+09:00",
        "trip_id": trip.get("id"),
    }


def _build_contingency(
    trip: dict[str, Any],
    day_index: int,
    item_index: int,
    item: dict[str, Any],
    trigger: str,
    candidate_places: dict[str, _Candidate],
    context: ValidationContext,
    condition_snapshot: ConditionSnapshot | None,
) -> dict[str, Any]:
    alternatives = [
        _build_alternative(trip, day_index, item_index, item, candidate, trigger, context)
        for candidate in _candidate_alternatives(item, trigger, candidate_places)
    ]
    alternatives = [candidate for candidate in alternatives if candidate is not None]

    decision_gate = _evaluate_condition_gate(
        trip,
        item,
        trigger,
        condition_snapshot,
    )
    result = {
        "id": f"{trigger}:{trip.get('id','trip')}:{day_index}:{item.get('id', item_index)}",
        "trigger": trigger,
        "label": TRIGGER_LABELS[trigger],
        "priority": TRIGGER_PRIORITIES[trigger],
        "day_index": day_index,
        "item": _item_reference(day_index, item_index, item, candidate_places),
        "status": "available" if alternatives else "unavailable",
        "instruction": INSTRUCTIONS[trigger],
        "decision": decision_gate,
        "alternatives": alternatives,
        "validation": _snapshot_validation(trip, context),
    }
    return result


def _build_alternative(
    trip: dict[str, Any],
    day_index: int,
    item_index: int,
    item: dict[str, Any],
    candidate: _Candidate,
    trigger: str,
    context: ValidationContext,
) -> dict[str, Any] | None:
    replacement_id = candidate.place_id
    if replacement_id == item.get("place_id"):
        return None

    replaced = copy.deepcopy(trip)
    replaced["days"][day_index]["items"][item_index]["place_id"] = replacement_id
    validation = validate_itinerary(replaced, context)
    route_impact = _route_impact(replaced["days"][day_index]["items"], item_index, replacement_id, context)
    tradeoff = _tradeoff(trigger, item)

    return {
        "alternative_place_id": replacement_id,
        "alternative_name": candidate.name,
        "reason": _alternative_reason(trigger, item, candidate),
        "tradeoff": tradeoff,
        "source_evidence": _evidence(candidate.provenance),
        "valid_window": {"start_at": item.get("start_at"), "end_at": item.get("end_at")},
        "route_impact": route_impact,
        "validation": validation.as_dict(),
        "priority": TRIGGER_PRIORITIES[trigger],
        "additional_travel_minutes": route_impact.get("delta_minutes"),
        "additional_cost": 0,
        "user_instruction": INSTRUCTIONS[trigger],
        "preserves_confirmed_reservations": True,
    }


def _tradeoff(trigger: str, item: dict[str, Any]) -> str:
    if item.get("kind") == "meal":
        return "較短候位壓力，但口味與氛圍可能不同。"
    if trigger in {"rain", "closure"}:
        return "改為室內行程可避免外部天候影響，但與原題材風格可能不同。"
    if trigger == "delay":
        return "降低未來段落的時間壓力，但需接受行程順序調整。"
    return "替代方案可維持當日行程完整性，但體感品質將有差異。"


def _candidate_alternatives(item: dict[str, Any], trigger: str, candidate_places: dict[str, _Candidate]) -> list[_Candidate]:
    current = item.get("place_id")
    selected_candidates = [candidate for candidate in candidate_places.values() if candidate.place_id != current]

    if item.get("kind") == "meal":
        selected_candidates = [candidate for candidate in selected_candidates if candidate.kind == "restaurant"]
    elif item.get("kind") == "visit":
        selected_candidates = [candidate for candidate in selected_candidates if candidate.kind == "poi"]

    if trigger == "queue":
        selected_candidates = [candidate for candidate in selected_candidates if candidate.kind == "restaurant"]

    selected_candidates.sort(key=lambda candidate: (candidate.kind, candidate.place_id))
    return selected_candidates[:2]


def _alternative_reason(trigger: str, item: dict[str, Any], candidate: _Candidate) -> str:
    if trigger == "rain":
        return f"{candidate.name} 為室內替代點，可減少露天活動受天候影響。"
    if trigger == "queue":
        return f"{candidate.name} 取代 {item.get('place_id')} 可降低排隊與候位風險。"
    if trigger == "parking_full":
        return f"{candidate.name} 更接近替代停留點，可減少停車轉移壓力。"
    if trigger == "closure":
        return f"{candidate.name} 提供非室外關閉風險較低的替代。"
    if trigger == "delay":
        return f"{candidate.name} 供交通波動時提前接軌行程，降低延誤擴大。"
    return f"{candidate.name} 為 {item.get('kind', '行程項目')} 的備援選項。"


def _evidence(provenance: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": provenance.get("provider"),
        "freshness": provenance.get("status", "unverified"),
        "retrieved_at": provenance.get("retrieved_at"),
        "note": provenance.get("note"),
        "confidence": provenance.get("confidence"),
    }


def _item_reference(day_index: int, item_index: int, item: dict[str, Any], candidates: dict[str, _Candidate]) -> dict[str, Any]:
    place = candidates.get(item.get("place_id", ""))
    return {
        "day_index": day_index,
        "index": item_index,
        "item_id": item.get("id"),
        "time_range": {"start_at": item.get("start_at"), "end_at": item.get("end_at")},
        "place_id": item.get("place_id"),
        "place_name": place.name if place else item.get("place_id"),
        "kind": item.get("kind"),
    }


def _snapshot_validation(trip: dict[str, Any], context: ValidationContext) -> dict[str, Any]:
    snapshot = validate_itinerary(trip, context)
    return {
        "outcome": snapshot.outcome.value,
        "violations": [item.as_dict() for item in snapshot.violations],
        "is_complete": snapshot.outcome is not Outcome.INVALID,
    }


def _evaluate_condition_gate(
    trip: dict[str, Any],
    item: dict[str, Any],
    trigger: str,
    snapshot: ConditionSnapshot | None,
) -> dict[str, Any]:
    if snapshot is None:
        return {
            "status": "unknown",
            "reason": "no_condition_snapshot",
            "kind": TRIGGER_CONDITION_KINDS.get(trigger, "none"),
        }

    kind = TRIGGER_CONDITION_KINDS.get(trigger)
    if kind is None:
        return {"status": "unknown", "reason": "no_condition_mapping", "kind": trigger}

    place_id = item.get("place_id")
    if not isinstance(place_id, str):
        return {"status": "unknown", "reason": "invalid_place_id", "kind": kind.value}

    starts_at = _parse_datetime(item.get("start_at"))
    ends_at = _parse_datetime(item.get("end_at"))
    if starts_at is None or ends_at is None:
        return {"status": "unknown", "reason": "invalid_item_window", "kind": kind.value}
    if ends_at <= starts_at:
        return {"status": "unknown", "reason": "invalid_interval_order", "kind": kind.value}

    evaluated_at = _resolve_condition_evaluated_at(trip, snapshot)
    if evaluated_at is None:
        return {"status": "unknown", "reason": "missing_evaluation_time", "kind": kind.value}

    gate = evaluate_condition_gate(
        snapshot,
        place_id=place_id,
        starts_at=starts_at,
        ends_at=ends_at,
        evaluated_at=evaluated_at,
        policy=ConditionPolicy(),
        mode=ConditionDecisionMode.WARN,
    )
    return {
        "status": gate.status.value,
        "mode": ConditionDecisionMode.WARN.value,
        "kind": kind.value,
        "evaluated_at": evaluated_at.isoformat(),
        "soft_penalty": gate.soft_penalty,
        "findings": [
            {"code": finding.code, "severity": finding.severity, "message": finding.message}
            for finding in gate.findings
        ],
    }


def _load_condition_snapshot(payload: Any) -> ConditionSnapshot | None:
    if payload is None:
        return None
    if not isinstance(payload, (dict, str, Path)):
        return None
    try:
        if isinstance(payload, dict):
            return load_condition_snapshot(payload)
        path = Path(payload)
        if path.exists():
            return load_condition_snapshot(path)
    except Exception:
        return None
    return None


def _resolve_condition_evaluated_at(trip: dict[str, Any], snapshot: ConditionSnapshot) -> datetime | None:
    timestamps = [record.retrieved_at for record in snapshot.records]
    if timestamps:
        return max(timestamps)
    source = trip.get("provenance")
    if isinstance(source, dict):
        return _parse_datetime(source.get("retrieved_at"))
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _route_impact(items: list[dict[str, Any]], item_index: int, replacement_id: str, context: ValidationContext) -> dict[str, Any]:
    previous_id = items[item_index - 1]["place_id"] if item_index > 0 else None
    next_id = items[item_index + 1]["place_id"] if item_index + 1 < len(items) else None
    original_id = items[item_index]["place_id"]

    base_minutes = []
    alternative_minutes = []
    if previous_id is not None:
        base_minutes.append(context.travel_minutes.get((previous_id, original_id)))
        alternative_minutes.append(context.travel_minutes.get((previous_id, replacement_id)))
    if next_id is not None:
        base_minutes.append(context.travel_minutes.get((original_id, next_id)))
        alternative_minutes.append(context.travel_minutes.get((replacement_id, next_id)))

    base_unknown = any(value is None for value in base_minutes) or len(base_minutes) == 0
    replacement_unknown = any(value is None for value in alternative_minutes) or len(alternative_minutes) == 0

    if base_unknown or replacement_unknown:
        status = "unverified"
        base_total = None
        replacement_total = None
        delta = None
    else:
        base_total = sum(int(value) for value in base_minutes)
        replacement_total = sum(int(value) for value in alternative_minutes)
        status = "verified"
        delta = replacement_total - base_total
    return {
        "status": status,
        "from": {"previous": previous_id, "replacement": replacement_id, "original": original_id},
        "to": {"replacement": replacement_id, "next": next_id, "original_next": original_id},
        "base_travel_minutes": base_total,
        "replacement_travel_minutes": replacement_total,
        "delta_minutes": delta,
        "notes": "衍生層以 transport_legs 為主，不足路段需再以即時路由重新驗證。",
    }


def _triggers_for_item(
    day_index: int,
    item_index: int,
    item: dict[str, Any],
    trip: dict[str, Any],
    items: list[dict[str, Any]],
    context: ValidationContext,
    candidate_places: dict[str, _Candidate],
) -> list[str]:
    triggers: list[str] = []
    has_restaurants = any(candidate.kind == "restaurant" for candidate in candidate_places.values())
    if item.get("kind") in {"meal", "visit"} and has_restaurants:
        triggers.append("queue")
    if item.get("kind") == "visit":
        triggers.append("rain")
    if _has_delay_signal(items, item_index, context):
        triggers.append("delay")
    if len(items) >= 4:
        triggers.append("fatigue")
        if item_index >= 2:
            triggers.append("shortened_day")
    if item.get("kind") == "visit" and item.get("start_at", "").endswith("+09:00"):
        triggers.append("closure")
    if day_index > 0 and trip.get("traveler_profile", {}).get("children"):
        triggers.append("parking_full")
    if not triggers:
        triggers.append("delay")
    return sorted(set(triggers), key=TRIGGER_ORDER.index)


def _has_delay_signal(items: list[dict[str, Any]], item_index: int, context: ValidationContext) -> bool:
    if not items:
        return False
    previous_id = items[item_index - 1]["place_id"] if item_index > 0 else None
    next_id = items[item_index + 1]["place_id"] if item_index + 1 < len(items) else None
    current_id = items[item_index]["place_id"]
    if previous_id == current_id or next_id == current_id:
        return False
    if previous_id is not None and context.travel_minutes.get((previous_id, current_id)) is None:
        return True
    if next_id is not None and context.travel_minutes.get((current_id, next_id)) is None:
        return True
    return False


def _index_candidates(trip: dict[str, Any]) -> dict[str, _Candidate]:
    places = trip.get("candidate_sets", {}).get("places", [])
    restaurants = trip.get("candidate_sets", {}).get("restaurants", [])
    result: dict[str, _Candidate] = {}
    for candidate in places:
        if not isinstance(candidate, dict):
            continue
        place_id = candidate.get("id")
        if not isinstance(place_id, str):
            continue
        result[place_id] = _Candidate(
            place_id,
            candidate.get("name", place_id),
            candidate.get("provenance", {}) or {},
            candidate.get("kind", "poi"),
        )
    for candidate in restaurants:
        if not isinstance(candidate, dict):
            continue
        place = candidate.get("place")
        if not isinstance(place, dict):
            continue
        place_id = place.get("id")
        if not isinstance(place_id, str):
            continue
        place_name = place.get("name", place_id)
        provenance = candidate.get("provenance") or place.get("provenance", {})
        result[place_id] = _Candidate(place_id, place_name, provenance, "restaurant")
    return result


def _validation_context(trip: dict[str, Any]) -> ValidationContext:
    budget = trip.get("budget", {})
    total = budget.get("total", {})
    currency = budget.get("currency") or total.get("currency")
    amount = total.get("amount") if isinstance(total, dict) else None
    budget_limit = BudgetLimit(amount, currency) if isinstance(amount, (int, float)) and currency else None

    minutes: dict[tuple[str, str], int] = {}
    for route in trip.get("candidate_sets", {}).get("transport_legs", []) or []:
        if not isinstance(route, dict):
            continue
        origin = route.get("from_place_id")
        destination = route.get("to_place_id")
        departure = route.get("departure_at")
        arrival = route.get("arrival_at")
        if not isinstance(origin, str) or not isinstance(destination, str):
            continue
        if not isinstance(departure, str) or not isinstance(arrival, str):
            continue
        try:
            minutes[(origin, destination)] = max(
                1,
                int((datetime.fromisoformat(arrival) - datetime.fromisoformat(departure)).total_seconds() / 60),
            )
        except ValueError:
            continue

    opening_hours: dict[str, tuple[OpeningInterval, ...]] = {}
    for candidate in trip.get("candidate_sets", {}).get("restaurants", []):
        if not isinstance(candidate, dict):
            continue
        place = candidate.get("place")
        if not isinstance(place, dict):
            continue
        opening = candidate.get("opening_hours")
        intervals = []
        if isinstance(opening, dict) and opening.get("status") == "fresh":
            for period in opening.get("intervals", []):
                if not isinstance(period, dict):
                    continue
                try:
                    intervals.append(
                        OpeningInterval(
                            weekday=int(period.get("weekday", 0)),
                            opens_at=datetime.strptime(period["opens_at"], "%H:%M").time(),
                            closes_at=datetime.strptime(period["closes_at"], "%H:%M").time(),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        if intervals:
            opening_hours[place["id"]] = tuple(intervals)
    return ValidationContext(minutes, opening_hours, budget_limit)
