"""Conservative, dependency-free Chinese trip-request extraction.

This is intentionally a deterministic normalization layer rather than an LLM
planner.  A value is emitted only when a pattern explicitly states it.
"""

from __future__ import annotations

import re
from collections import defaultdict

from src.planner.contracts import HardConstraint, SoftPreference

from .contracts import AmbiguousField, FieldProvenance, MissingField, TravelerGroup, TripRequest

_KNOWN_PLACES = (
    "東京", "大阪", "京都", "神戶", "德島", "福岡", "札幌", "沖繩", "名古屋", "奈良", "熊本", "由布院", "北海道", "東京迪士尼", "環球影城",
)
_REGIONS = {"關西", "關東", "九州", "北海道", "四國"}


def parse_trip_request(text: str) -> TripRequest:
    """Extract a :class:`TripRequest` from Chinese free text.

    Unknown details remain ``None`` and are listed in ``missing_fields``.
    Exact matched substrings are stored as field provenance.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    values: dict[str, object] = {}
    provenance: dict[str, list[FieldProvenance]] = defaultdict(list)

    def capture(field: str, pattern: str, transform=lambda match: match.group(0), flags: int = 0):
        matches = list(re.finditer(pattern, text, flags))
        if matches:
            values[field] = transform(matches[0])
            provenance[field].extend(FieldProvenance(match.group(0), match.start(), match.end(), field) for match in matches)
        return matches

    places = tuple(place for place in _KNOWN_PLACES if (matches := list(re.finditer(re.escape(place), text))) and not _record_matches(provenance, "destinations", matches))
    # _record_matches always returns False: the expression keeps ordering compact.
    regions = tuple(region for region in _REGIONS if region in text)
    for region in regions:
        match = re.search(re.escape(region), text)
        assert match is not None
        provenance["regions"].append(FieldProvenance(region, match.start(), match.end(), "regions"))
    values["destinations"], values["regions"] = places, regions

    capture("origin", r"(?:從|由|出發地[：:]?)(台北|高雄|桃園|香港|東京|大阪)(?:出發|飛|去)?", lambda m: m.group(1))
    capture("duration", r"([\d一二三四五六七八九十]+)天([\d一二三四五六七八九十]+)夜", lambda m: (_number(m.group(1)), _number(m.group(2))))
    if "duration" not in values:
        capture("duration", r"([\d一二三四五六七八九十]+)天", lambda m: (_number(m.group(1)), None))
    date_match = capture("date_range", r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*(?:到|至|[-~])\s*(\d{4})?[/-]?(\d{1,2})[/-](\d{1,2})")
    start_date = end_date = None
    if date_match:
        m = date_match[0]
        year = m.group(1)
        start_date = f"{year}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        end_year = m.group(4) or year
        end_date = f"{end_year}-{int(m.group(5)):02d}-{int(m.group(6)):02d}"

    adult_match = capture("adults", r"([\d一二三四五六七八九十]+)\s*(?:大|位大人|成人)", lambda m: _number(m.group(1)))
    child_match = capture("children", r"([\d一二三四五六七八九十]+)\s*(?:小|位小孩|位兒童|小孩|兒童)", lambda m: _number(m.group(1)))
    ages = tuple(int(match.group(1)) for match in re.finditer(r"(\d{1,2})\s*歲", text))
    for match in re.finditer(r"(\d{1,2})\s*歲", text):
        provenance["child_ages"].append(FieldProvenance(match.group(0), match.start(), match.end(), "child_ages"))

    budget = capture("budget", r"(?:預算|花費|總共)(?:約|最多)?\s*(\d+(?:\.\d+)?)\s*(萬|千)?\s*(台幣|NTD|日圓|JPY|元)?", lambda m: _budget(m.group(1), m.group(2), m.group(3)), re.I)
    budget_amount = currency = None
    if budget:
        budget_amount, currency = values["budget"]  # type: ignore[misc]
    transport = _choices(text, {"自駕": "drive", "開車": "drive", "大眾運輸": "transit", "搭電車": "transit", "火車": "transit", "混合": "mixed"}, provenance, "transport")
    required = _after_markers(text, ("一定要去", "必去", "想去"), provenance, "required_places")
    forbidden = _after_markers(text, ("不要去", "不去", "避開"), provenance, "forbidden_places")
    accommodation = _choices(text, {"溫泉旅館": "ryokan", "商務旅館": "business_hotel", "親子飯店": "family_hotel", "住市中心": "central"}, provenance, "accommodation_preferences")
    food = _choices(text, {"吃素": "vegetarian", "素食": "vegetarian", "海鮮": "seafood", "拉麵": "ramen", "和牛": "wagyu", "不吃牛": "no_beef"}, provenance, "food_preferences")
    pace = "relaxed" if re.search(r"不要太累|慢慢玩|輕鬆", text) else ("packed" if re.search(r"行程緊湊|排滿", text) else None)
    if pace:
        match = re.search(r"不要太累|慢慢玩|輕鬆|行程緊湊|排滿", text)
        assert match is not None
        provenance["pace"].append(FieldProvenance(match.group(0), match.start(), match.end(), "pace"))

    hard = []
    for place in required:
        hard.append(HardConstraint(f"required-{place}", "required_location", place))
    for place in forbidden:
        hard.append(HardConstraint(f"forbidden-{place}", "forbidden_location", place))
    soft = [SoftPreference("low-fatigue", "low_fatigue")] if pace == "relaxed" else []
    missing = _missing(places, start_date, values.get("duration"), values.get("adults"), budget_amount)
    ambiguous = []
    if len(ages) and values.get("children") is not None and len(ages) != values["children"]:
        ambiguous.append(AmbiguousField("child_ages", ", ".join(map(str, ages)), "兒童人數與明確年齡數量不一致"))
    if len(transport) > 1 and "mixed" not in transport:
        ambiguous.append(AmbiguousField("transport", "、".join(transport), "同時提及多種交通方式，未說明分配方式"))
    days, nights = values.get("duration", (None, None))
    return TripRequest(text, places, regions, start_date, end_date, days, nights, values.get("origin"), TravelerGroup(values.get("adults"), values.get("children"), ages), budget_amount, currency, transport, required, forbidden, accommodation, food, pace, tuple(hard), tuple(soft), tuple(missing), tuple(ambiguous), dict(provenance))


def _record_matches(provenance, field, matches):
    provenance[field].extend(FieldProvenance(m.group(0), m.start(), m.end(), field) for m in matches)
    return False


def _number(value: str) -> int:
    if value.isdigit():
        return int(value)
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value == "十":
        return 10
    if "十" in value:
        before, _, after = value.partition("十")
        return digits.get(before, 1) * 10 + digits.get(after, 0)
    return digits[value]


def _budget(number: str, scale: str | None, denomination: str | None) -> tuple[int, str]:
    multiplier = 10000 if scale == "萬" else 1000 if scale == "千" else 1
    currency = "JPY" if (denomination or "").lower() in {"jpy", "日圓"} else "TWD"
    return int(float(number) * multiplier), currency


def _choices(text, vocabulary, provenance, field):
    result = []
    for phrase, normalized in vocabulary.items():
        for match in re.finditer(re.escape(phrase), text):
            provenance[field].append(FieldProvenance(phrase, match.start(), match.end(), field))
            if normalized not in result:
                result.append(normalized)
    return tuple(result)


def _after_markers(text, markers, provenance, field):
    names = []
    for marker in markers:
        match = re.search(re.escape(marker) + r"\s*([\u4e00-\u9fffA-Za-z0-9]+)", text)
        if match:
            name = match.group(1)
            provenance[field].append(FieldProvenance(match.group(0), match.start(), match.end(), field))
            if name not in names:
                names.append(name)
    return tuple(names)


def _missing(destinations, start_date, duration, adults, budget):
    missing = []
    if not destinations:
        missing.append(MissingField("destination", "未提供目的地"))
    if not start_date and not duration:
        missing.append(MissingField("dates_or_duration", "未提供日期或旅遊天數"))
    if adults is None:
        missing.append(MissingField("travelers", "未提供旅客人數"))
    if budget is None:
        missing.append(MissingField("budget", "未提供預算"))
    return missing
