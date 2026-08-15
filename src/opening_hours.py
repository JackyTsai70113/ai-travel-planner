"""Provider-neutral restaurant opening-hours snapshots.

The planner and validator deliberately share this module.  Adapters normalize
provider responses into the JSON-compatible snapshot contract; no consumer
needs to know whether a period came from Google, an official feed, or a fixture.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class HoursStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"


class Eligibility(str, Enum):
    ELIGIBLE = "eligible"
    CLOSED = "closed"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class OpeningInterval:
    """One local weekly interval; Monday is 0.

    ``closes_day_offset`` represents overnight and 24-hour intervals without
    accepting non-ISO clock strings such as ``24:00`` or ``29:30``.
    """

    weekday: int
    opens_at: time
    closes_at: time
    closes_day_offset: int = 0
    last_order_at: time | None = None
    last_order_day_offset: int = 0


@dataclass(frozen=True)
class SpecialHours:
    date: date
    status: str
    intervals: tuple[OpeningInterval, ...] = ()


@dataclass(frozen=True)
class OpeningHoursSnapshot:
    status: HoursStatus
    timezone: str
    intervals: tuple[OpeningInterval, ...] = ()
    closed_weekdays: tuple[int, ...] = ()
    regular_holidays: tuple[str, ...] = ()
    special_hours: tuple[SpecialHours, ...] = ()
    provenance: Mapping[str, Any] | None = None
    alternatives: tuple[Mapping[str, Any], ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class EligibilityResult:
    status: Eligibility
    reason: str

    @property
    def eligible(self) -> bool:
        return self.status is Eligibility.ELIGIBLE


def parse_clock(value: object, *, field: str = "time") -> time:
    """Parse canonical HH:MM while rejecting the former accidental 24-29h range."""

    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError(f"{field} must use HH:MM")
    try:
        hour, minute = int(value[:2]), int(value[3:])
    except ValueError as exc:
        raise ValueError(f"{field} must use HH:MM") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"{field} must be between 00:00 and 23:59")
    return time(hour, minute)


def snapshot_from_mapping(value: object, *, default_timezone: str | None = None) -> OpeningHoursSnapshot:
    """Validate and parse the canonical JSON snapshot.

    Legacy snapshots without ``timezone`` remain readable only when a caller
    supplies the trip timezone.  This keeps existing fixtures compatible while
    ensuring new provider snapshots are location-aware.
    """

    if isinstance(value, OpeningHoursSnapshot):
        return value
    if not isinstance(value, Mapping):
        return OpeningHoursSnapshot(HoursStatus.UNVERIFIED, default_timezone or "UTC")
    try:
        status = HoursStatus(str(value.get("status", "unverified")))
    except ValueError:
        status = HoursStatus.UNVERIFIED
    timezone_name = value.get("timezone") or default_timezone or "UTC"
    try:
        ZoneInfo(str(timezone_name))
    except (ZoneInfoNotFoundError, ValueError):
        return OpeningHoursSnapshot(HoursStatus.UNVERIFIED, "UTC", note="invalid restaurant timezone")

    intervals = tuple(_parse_interval(item) for item in _mappings(value.get("intervals")))
    special: list[SpecialHours] = []
    for item in _mappings(value.get("special_hours")):
        try:
            special_date = date.fromisoformat(str(item["date"]))
        except (KeyError, TypeError, ValueError):
            continue
        special_status = str(item.get("status", "unverified"))
        if special_status not in {"open", "closed", "unverified"}:
            special_status = "unverified"
        special.append(SpecialHours(
            special_date,
            special_status,
            tuple(_parse_interval(period, weekday=special_date.weekday()) for period in _mappings(item.get("intervals"))),
        ))
    closed = tuple(sorted({day for day in value.get("closed_weekdays", ()) if isinstance(day, int) and 0 <= day <= 6}))
    holidays = tuple(str(item) for item in value.get("regular_holidays", ()) if isinstance(item, str) and item)
    provenance = value.get("provenance") if isinstance(value.get("provenance"), Mapping) else None
    alternatives = tuple(_mappings(value.get("alternatives")))
    note = value.get("note") if isinstance(value.get("note"), str) else None
    return OpeningHoursSnapshot(status, str(timezone_name), intervals, closed, holidays, tuple(special), provenance, alternatives, note)


def snapshot_to_mapping(snapshot: OpeningHoursSnapshot) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": snapshot.status.value,
        "timezone": snapshot.timezone,
        "intervals": [_interval_mapping(interval) for interval in snapshot.intervals],
        "closed_weekdays": list(snapshot.closed_weekdays),
        "regular_holidays": list(snapshot.regular_holidays),
        "special_hours": [
            {
                "date": special.date.isoformat(),
                "status": special.status,
                "intervals": [_interval_mapping(interval, include_weekday=False) for interval in special.intervals],
            }
            for special in snapshot.special_hours
        ],
    }
    if snapshot.provenance is not None:
        result["provenance"] = dict(snapshot.provenance)
    if snapshot.alternatives:
        result["alternatives"] = [dict(item) for item in snapshot.alternatives]
    if snapshot.note:
        result["note"] = snapshot.note
    return result


def evaluate_opening_hours(
    snapshot: OpeningHoursSnapshot | Mapping[str, object], start: datetime, end: datetime, *, default_timezone: str | None = None
) -> EligibilityResult:
    """Require the complete absolute meal interval to be confirmed open."""

    parsed = snapshot_from_mapping(snapshot, default_timezone=default_timezone)
    if parsed.status is not HoursStatus.FRESH:
        return EligibilityResult(Eligibility.UNVERIFIED, f"opening hours are {parsed.status.value}")
    if start.tzinfo is None or end.tzinfo is None:
        return EligibilityResult(Eligibility.UNVERIFIED, "scheduled interval lacks timezone offset")
    if end <= start:
        return EligibilityResult(Eligibility.CLOSED, "scheduled interval is invalid")
    local_zone = ZoneInfo(parsed.timezone)
    local_start, local_end = start.astimezone(local_zone), end.astimezone(local_zone)
    special = next((item for item in parsed.special_hours if item.date == local_start.date()), None)
    if special is not None:
        if special.status == "closed":
            return EligibilityResult(Eligibility.CLOSED, "restaurant is closed on this special date")
        if special.status == "unverified":
            return EligibilityResult(Eligibility.UNVERIFIED, "special-date hours are unverified")
        candidates = tuple((item, special.date) for item in special.intervals)
    else:
        if local_start.weekday() in parsed.closed_weekdays:
            return EligibilityResult(Eligibility.CLOSED, "restaurant is closed on this weekday")
        candidates = tuple(
            (item, local_start.date())
            for item in parsed.intervals
            if item.weekday == local_start.weekday()
        )
        previous_special = next((item for item in parsed.special_hours if item.date == local_start.date() - timedelta(days=1)), None)
        previous_unverified = previous_special is not None and previous_special.status == "unverified"
        if previous_special is None:
            candidates += tuple(
                (item, local_start.date() - timedelta(days=1))
                for item in parsed.intervals
                if (local_start.weekday() - item.weekday) % 7 == 1 and item.closes_day_offset == 1
            )
        elif previous_special.status == "open":
            candidates += tuple((item, previous_special.date) for item in previous_special.intervals if item.closes_day_offset == 1)
    if any(_contains(item, local_start, local_end, anchor_date) for item, anchor_date in candidates):
        return EligibilityResult(Eligibility.ELIGIBLE, "complete interval is open")
    if special is None and previous_unverified:
        return EligibilityResult(Eligibility.UNVERIFIED, "previous special-date overnight hours are unverified")
    return EligibilityResult(Eligibility.CLOSED, "scheduled interval falls outside confirmed opening hours")


def legacy_snapshot(intervals: Sequence[OpeningInterval], timezone_name: str) -> OpeningHoursSnapshot:
    """Adapt the validator's original interval-only context to the shared model."""

    return OpeningHoursSnapshot(HoursStatus.FRESH, timezone_name, tuple(intervals))


def _contains(interval: OpeningInterval, start: datetime, end: datetime, anchor_date: date) -> bool:
    open_at = datetime.combine(anchor_date, interval.opens_at, start.tzinfo)
    close_at = datetime.combine(anchor_date + timedelta(days=interval.closes_day_offset), interval.closes_at, start.tzinfo)
    if interval.closes_day_offset == 0 and close_at <= open_at:
        return False
    if not (open_at <= start and end <= close_at):
        return False
    if interval.last_order_at is None:
        return True
    cutoff = datetime.combine(
        anchor_date + timedelta(days=interval.last_order_day_offset),
        interval.last_order_at,
        start.tzinfo,
    )
    return start <= cutoff


def _parse_interval(value: Mapping[str, Any], weekday: int | None = None) -> OpeningInterval:
    parsed_weekday = weekday if weekday is not None else int(value["weekday"])
    if not 0 <= parsed_weekday <= 6:
        raise ValueError("weekday must be between 0 and 6")
    close_offset = int(value.get("closes_day_offset", 0))
    last_order_offset = int(value.get("last_order_day_offset", close_offset))
    if close_offset not in {0, 1} or last_order_offset not in {0, 1}:
        raise ValueError("day offsets must be 0 or 1")
    last_order = value.get("last_order_at")
    return OpeningInterval(
        parsed_weekday,
        parse_clock(value["opens_at"], field="opens_at"),
        parse_clock(value["closes_at"], field="closes_at"),
        close_offset,
        parse_clock(last_order, field="last_order_at") if last_order is not None else None,
        last_order_offset,
    )


def _interval_mapping(interval: OpeningInterval, *, include_weekday: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if include_weekday:
        result["weekday"] = interval.weekday
    result.update({"opens_at": interval.opens_at.strftime("%H:%M"), "closes_at": interval.closes_at.strftime("%H:%M")})
    if interval.closes_day_offset:
        result["closes_day_offset"] = interval.closes_day_offset
    if interval.last_order_at is not None:
        result["last_order_at"] = interval.last_order_at.strftime("%H:%M")
        if interval.last_order_day_offset:
            result["last_order_day_offset"] = interval.last_order_day_offset
    return result


def _mappings(value: object) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, (list, tuple)) else []
