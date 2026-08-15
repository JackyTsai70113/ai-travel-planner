"""Conservative, dependency-free Chinese trip-request extraction.

This is intentionally a deterministic normalization layer rather than an LLM
planner.  A value is emitted only when a pattern explicitly states it.
"""

from __future__ import annotations

import re
from collections import defaultdict

from src.planner.contracts import HardConstraint, SoftPreference

from .contracts import (
    AmbiguousField, ConstraintCondition, ConstraintIssue, ConstraintScope,
    FieldProvenance, MissingField, RequestConstraint, TimeWindow,
    TravelerGroup, TripRequest,
)

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

    capture("origin", r"(?:(?:從|由|出發地[：:]?)(台北|高雄|桃園|香港|東京|大阪)(?:出發|飛|去)?|(台北|高雄|桃園|香港|東京|大阪)出發)", lambda m: m.group(1) or m.group(2))
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
    request_constraints, constraint_issues = _request_constraints(text, start_date)
    extension_spans = tuple(
        (source.start, source.end)
        for item in request_constraints
        if item.scope or item.time_window or item.condition
        for source in item.provenance
        if source.field == "request_constraints"
    )
    required = _after_markers(text, ("一定要去", "必去", "想去"), provenance, "required_places", extension_spans)
    forbidden = _after_markers(text, ("不要去", "不去", "避開"), provenance, "forbidden_places", extension_spans)
    constraint_issues = tuple(constraint_issues) + tuple(
        ConstraintIssue(
            "contradictory_strength", (item.id,), "request_constraints", item.subject or "",
            "全旅程地點限制與特定範圍的要求互相矛盾",
        )
        for item in request_constraints
        if item.kind == "place" and item.subject and (
            (item.strength == "forbidden" and item.subject in required)
            or (item.strength in {"required", "preferred"} and item.subject in forbidden)
        )
    )
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
    return TripRequest(
        raw_text=text, destinations=places, regions=regions, start_date=start_date,
        end_date=end_date, duration_days=days, duration_nights=nights,
        origin=values.get("origin"),
        travelers=TravelerGroup(values.get("adults"), values.get("children"), ages),
        budget_amount=budget_amount, currency=currency, transport=transport,
        required_places=required, forbidden_places=forbidden,
        accommodation_preferences=accommodation, food_preferences=food, pace=pace,
        hard_constraints=tuple(hard), soft_preferences=tuple(soft),
        missing_fields=tuple(missing), ambiguous_fields=tuple(ambiguous),
        provenance=dict(provenance), request_constraints=request_constraints,
        constraint_issues=constraint_issues,
    )


def _request_constraints(text: str, trip_start_date: str | None):
    found: list[tuple[int, RequestConstraint]] = []
    issues: list[ConstraintIssue] = []

    def add(kind, strength, match, subject=None, scope=None, window=None,
            relation=None, object_=None, condition=None):
        identifier = f"request-{len(found) + 1}"
        source = FieldProvenance(match.group(0), match.start(), match.end(), "request_constraints")
        sources = [source]

        def trace(field, pattern):
            if any(item.field == field for item in sources):
                return
            located = re.search(pattern, source.text)
            if located:
                sources.append(FieldProvenance(
                    located.group(0), source.start + located.start(),
                    source.start + located.end(), field,
                ))

        kind_patterns = {
            "place": r"去|避開",
            "order": r"先去[^，。；;!?！？]*再去|排在",
            "daily_boundary": r"開始|出門|結束|回飯店|回旅館|返回飯店|返回旅館",
            "nap": r"午睡",
            "meal": r"早餐|午餐|晚餐",
            "return_deadline": r"回飯店|回旅館|返回飯店|返回旅館",
            "proximity": r"機場附近|離機場近|不要跑遠",
        }
        strength_patterns = {
            # In a scoped assignment ("第一天去 X"), 去 is itself the
            # requester's explicit required action rather than an inferred
            # default.  It can support both kind and strength provenance.
            "required": r"一定要|必去|需要|要|每天|每日|只排|先去|排在|開始|出門|結束|午睡|前|後|去",
            "preferred": r"想去|希望去|下雨|雨天",
            "optional": r"有時間(?:的話)?|時間允許(?:的話)?|來得及(?:的話)?",
            "forbidden": r"不要去|不去|避開",
        }
        trace("kind", kind_patterns[kind])
        trace("strength", strength_patterns[strength])
        if subject:
            subject_patterns = {
                "child": r"小孩|兒童|孩子",
                "day": r"每天|每日|開始|出門|結束",
                "hotel": r"飯店|旅館",
                "airport": r"機場",
                "breakfast": r"早餐",
                "lunch": r"午餐",
                "dinner": r"晚餐",
                "meal": r"吃飯|用餐|餐",
            }
            trace("subject", subject_patterns.get(subject, re.escape(subject)))
        if scope:
            if scope.day_number is not None:
                trace("scope", r"第[\d一二三四五六七八九十]+天")
            elif scope.day_selector:
                trace("scope", r"最後一天")
            elif scope.date:
                year, month, day = scope.date.split("-")
                trace("scope", rf"{year}[/-]0?{int(month)}[/-]0?{int(day)}")
        if window:
            if window.start:
                hour, minute = window.start.split(":")
                pattern = rf"0?{int(hour)}[:：]{minute}"
                if window.end:
                    end_hour, end_minute = window.end.split(":")
                    pattern += rf"\s*(?:到|至|[-~])\s*0?{int(end_hour)}[:：]{end_minute}"
                trace("time_window", pattern)
            elif window.end:
                hour, minute = window.end.split(":")
                trace("time_window", rf"0?{int(hour)}[:：]{minute}")
            elif window.period:
                trace("time_window", r"早上|上午|中午|下午|晚上|晚間")
        if condition:
            trace("condition", r"(?:(?:如果|若)\s*)?(?:下雨|雨天)|有時間(?:的話)?|時間允許(?:的話)?|來得及(?:的話)?")
        if relation:
            relation_patterns = {
                "before": r"先去|之前|排在[^，。；;!?！？]*前|前",
                "after": r"之後|排在[^，。；;!?！？]*後|後",
                "start": r"開始|出門",
                "end": r"結束|回飯店|回旅館|返回飯店|返回旅館",
                "by": r"前",
                "near": r"機場附近|離機場近|不要跑遠|附近",
            }
            trace("relation", relation_patterns[relation])
        if object_:
            trace("object", r"飯店入住|旅館入住|入住飯店|入住旅館" if object_ == "hotel_check_in" else re.escape(object_))
        found.append((match.start(), RequestConstraint(identifier, kind, strength, subject, scope,
                                                       window, relation, object_, condition, tuple(sources))))

    # An absolute-date selector deliberately requires an explicit strength
    # marker.  This keeps the end date in "YYYY/MM/DD 到 YYYY/MM/DD 去東京"
    # from being mistaken for a day-scoped place request.
    dated_place_pattern = (
        r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*"
        r"(?:(早上|上午|中午|下午|晚上|晚間)\s*)?"
        r"(一定要去|必去|不要去|不去|避開|想去|希望去)\s*"
        r"([\u4e00-\u9fffA-Za-z0-9]+)"
    )
    dated_place_spans = []
    for match in re.finditer(dated_place_pattern, text):
        dated_place_spans.append(match.span())
        scope = ConstraintScope(date=f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}")
        window = _time_window(match.group(4)) if match.group(4) else None
        add("place", _strength(match.group(0)), match, match.group(6), scope, window)

    place_pattern = (
        r"(?:(第[\d一二三四五六七八九十]+天|最後一天)\s*)?"
        r"(?:(早上|上午|中午|下午|晚上|晚間)\s*)?"
        r"(?:(\d{1,2})[:：](\d{2})\s*(?:到|至|[-~])\s*(\d{1,2})[:：](\d{2})\s*)?"
        r"(?:(?:(?:如果|若)\s*)?(下雨(?:的話)?|雨天|有時間(?:的話)?|時間允許(?:的話)?|來得及(?:的話)?)\s*)?"
        r"(?:才|再|就)?\s*(一定要去|必去|不要去|不去|避開|想去|希望去|去)\s*"
        r"([\u4e00-\u9fffA-Za-z0-9]+)"
    )
    for match in re.finditer(place_pattern, text):
        if any(start <= match.start() and match.end() <= end for start, end in dated_place_spans):
            continue
        qualifier = any(match.group(index) for index in range(1, 8))
        if not qualifier:
            continue
        window = None
        if match.group(3):
            window = TimeWindow(f"{int(match.group(3)):02d}:{match.group(4)}", f"{int(match.group(5)):02d}:{match.group(6)}")
        elif match.group(2):
            window = _time_window(match.group(2))
        add("place", _strength(match.group(0)), match, match.group(9), _scope(match.group(0)),
            window, condition=_condition(match.group(0)))

    for match in re.finditer(r"先去([\u4e00-\u9fffA-Za-z0-9]+?)再去([\u4e00-\u9fffA-Za-z0-9]+)", text):
        add("order", "required", match, match.group(1), relation="before", object_=match.group(2))
    for match in re.finditer(r"([\u4e00-\u9fffA-Za-z0-9]+?)排在(?:飯店入住|旅館入住|入住飯店|入住旅館)(前|後)", text):
        add("order", "required", match, match.group(1), relation="before" if match.group(2) == "前" else "after", object_="hotel_check_in")

    # Daily start/end and return-to-hotel boundaries.
    for match in re.finditer(r"(?:每天|每日)?\s*(\d{1,2})[:：](\d{2})\s*(後|以後|前|以前)?\s*(?:才)?\s*(開始|出門|結束|回飯店|回旅館|返回飯店|返回旅館)", text):
        time = f"{int(match.group(1)):02d}:{match.group(2)}"
        action = match.group(4)
        if action in {"回飯店", "回旅館", "返回飯店", "返回旅館"} and not re.search(r"每天|每日", match.group(0)):
            add("return_deadline", "required", match, "hotel", _scope(match.group(0)),
                TimeWindow(end=time), "by")
        else:
            relation = "start" if action in {"開始", "出門"} else "end"
            add("daily_boundary", "required", match, "day", _scope(match.group(0)),
                TimeWindow(start=time) if relation == "start" else TimeWindow(end=time), relation)

    # Child nap and meal windows.
    for match in re.finditer(r"(?:第[\d一二三四五六七八九十]+天\s*)?(?:小孩|兒童|孩子)?\s*(?:每天|每日)?\s*(?:(\d{1,2})[:：](\d{2})\s*(?:到|至|[-~])\s*(\d{1,2})[:：](\d{2})\s*)?(?:小孩|兒童|孩子)?\s*(?:要|需要)?午睡", text):
        window = TimeWindow(f"{int(match.group(1)):02d}:{match.group(2)}", f"{int(match.group(3)):02d}:{match.group(4)}") if match.group(1) else TimeWindow(period="afternoon")
        add("nap", "required", match, "child", _scope(match.group(0)), window)
    for match in re.finditer(r"(?:每天|每日)?\s*(午餐|晚餐|早餐)(?:要在)?\s*(\d{1,2})[:：](\d{2})\s*(?:到|至|[-~])\s*(\d{1,2})[:：](\d{2})", text):
        meal = {"早餐": "breakfast", "午餐": "lunch", "晚餐": "dinner"}.get(match.group(1), "meal")
        add("meal", "required", match, meal, _scope(match.group(0)),
            TimeWindow(f"{int(match.group(2)):02d}:{match.group(3)}", f"{int(match.group(4)):02d}:{match.group(5)}"))

    for match in re.finditer(r"最後一天[^，。；;!?！？]*(?:機場附近|離機場近|不要跑遠)", text):
        add("proximity", "required", match, "airport", ConstraintScope(day_selector="last"),
            relation="near")

    # Machine-readable issues.
    found.sort(key=lambda pair: pair[0])
    constraints = [item for _, item in found]
    constraints = [RequestConstraint(f"request-{index}", item.kind, item.strength, item.subject,
                                     item.scope, item.time_window, item.relation, item.object,
                                     item.condition, item.provenance)
                   for index, item in enumerate(constraints, 1)]
    scoped_ids = tuple(item.id for item in constraints if item.scope and (item.scope.day_number or item.scope.date))
    if scoped_ids and trip_start_date is None:
        issues.append(ConstraintIssue("missing_trip_date", scoped_ids, "start_date", "", "有指定日序或日期的限制，但未提供完整旅程起始日期"))
    for match in re.finditer(r"(?:那天|某天|其中一天)", text):
        issues.append(ConstraintIssue("ambiguous_day_reference", (), "scope", match.group(0), "無法判定所指日期"))
    issues.extend(_constraint_conflicts(constraints))
    return tuple(constraints), tuple(issues)


def _offset_match(original, offset, clause):
    class Match:
        def group(self, _=0): return clause
        def start(self): return offset
        def end(self): return offset + len(clause)
    return Match()


def _scope(value: str) -> ConstraintScope | None:
    match = re.search(r"第([\d一二三四五六七八九十]+)天", value)
    if match:
        return ConstraintScope(day_number=_number(match.group(1)))
    if "最後一天" in value:
        return ConstraintScope(day_selector="last")
    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", value)
    if match:
        return ConstraintScope(date=f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}")
    return None


def _time_window(value: str) -> TimeWindow | None:
    period_match = re.search(r"早上|上午|中午|下午|晚上|晚間", value)
    periods = {"早上": "morning", "上午": "morning", "中午": "noon", "下午": "afternoon", "晚上": "evening", "晚間": "evening"}
    explicit = re.search(r"(\d{1,2})[:：](\d{2})(?:\s*(?:到|至|[-~])\s*(\d{1,2})[:：](\d{2}))?", value)
    if explicit:
        return TimeWindow(f"{int(explicit.group(1)):02d}:{explicit.group(2)}",
                          f"{int(explicit.group(3)):02d}:{explicit.group(4)}" if explicit.group(3) else None,
                          periods.get(period_match.group(0)) if period_match else None)
    return TimeWindow(period=periods[period_match.group(0)]) if period_match else None


def _condition(value: str) -> ConstraintCondition | None:
    if re.search(r"下雨|雨天|如果下雨|若下雨", value):
        return ConstraintCondition("weather", "rain")
    if re.search(r"有時間(?:的話|才)?|時間允許|來得及(?:的話)?", value):
        return ConstraintCondition("time_available")
    return None


def _strength(value: str) -> str:
    if re.search(r"不要去|不去|避開", value): return "forbidden"
    if re.search(r"有時間|時間允許|來得及", value): return "optional"
    if re.search(r"下雨|雨天", value): return "preferred"
    if re.search(r"想去|希望|最好", value): return "preferred"
    return "required"


def _normalize_check_in(value: str) -> str:
    return "hotel_check_in" if "入住" in value else value


def _constraint_conflicts(constraints):
    issues = []
    for index, left in enumerate(constraints):
        for right in constraints[index + 1:]:
            if left.kind == right.kind == "place" and left.subject == right.subject and left.scope == right.scope:
                if {left.strength, right.strength} & {"required", "preferred"} and "forbidden" in {left.strength, right.strength}:
                    issues.append(ConstraintIssue("contradictory_strength", (left.id, right.id), "request_constraints", left.subject or "", "同一範圍內同時要求並禁止相同地點"))
            if left.kind == right.kind == "order" and left.subject == right.object and left.object == right.subject and left.relation == right.relation:
                issues.append(ConstraintIssue("contradictory_order", (left.id, right.id), "relation", "", "排序限制互相矛盾"))
    for item in constraints:
        window = item.time_window
        if window and window.start and window.end and window.start >= window.end:
            issues.append(ConstraintIssue("invalid_time_window", (item.id,), "time_window", item.provenance[0].text, "開始時間不得晚於或等於結束時間"))
    return issues


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


def _after_markers(text, markers, provenance, field, excluded_spans=()):
    names = []
    for marker in markers:
        for match in re.finditer(re.escape(marker) + r"\s*([\u4e00-\u9fffA-Za-z0-9]+)", text):
            if any(start <= match.start() and match.end() <= end for start, end in excluded_spans):
                continue
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
