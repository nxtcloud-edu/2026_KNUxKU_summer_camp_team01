from __future__ import annotations

import re
from datetime import date, time, timedelta

from .models import (
    AvoidCheck,
    AvoidMatch,
    BudgetCheck,
    CheckIssue,
    MustVisitCheck,
    PlanDay,
    PlanItem,
    PlanToVerificationInput,
    StandardCheck,
    VerificationChecks,
)

WEEKDAYS_KO = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")
BUDGET_ALIASES = {
    "관광지": {"관광지", "관광", "activity", "activities"},
    "식사": {"식사", "food"},
    "카페": {"카페", "cafe"},
    "쇼핑": {"쇼핑", "shopping"},
    "휴식": {"휴식", "relax"},
    "숙소": {"숙소", "stay"},
}
PACE_MAX_ITEMS = {"여유": 3, "보통": 4, "빡빡": 7}
INTENSITY_RANK = {"낮음": 0, "중": 1, "중간": 1, "높음": 2}
OPENING_HOURS_PATTERN = re.compile(
    r"^\s*(\d{2}):(\d{2})\s*[-~–]\s*(\d{2}):(\d{2})\s*$"
)
OPEN_AFTER_PATTERN = re.compile(
    r"^\s*(?:체크인\s*)?([01]\d|2[0-3]):([0-5]\d)\s*이후\s*$"
)


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _normalize(value: str) -> str:
    return value.strip().casefold()


def _name_matches(required: str, candidate: str) -> bool:
    required_norm = _normalize(required)
    candidate_norm = _normalize(candidate)
    return bool(
        required_norm
        and candidate_norm
        and (required_norm in candidate_norm or candidate_norm in required_norm)
    )


def _issue(code: str, message: str, day: int | None = None, item_id: str | None = None) -> CheckIssue:
    return CheckIssue(code=code, message=message, day=day, item_id=item_id)


def _check(issues: list[CheckIssue]) -> StandardCheck:
    return StandardCheck(status="fail" if issues else "pass", issues=issues)


def _parse_opening_hours(value: str) -> tuple[int, int] | None:
    range_match = OPENING_HOURS_PATTERN.fullmatch(value)
    if range_match is not None:
        open_hour, open_minute, close_hour, close_minute = map(int, range_match.groups())
        valid_open = open_hour <= 23 and open_minute <= 59
        valid_close = close_minute <= 59 and (
            close_hour <= 23 or (close_hour == 24 and close_minute == 0)
        )
        if valid_open and valid_close:
            return open_hour * 60 + open_minute, close_hour * 60 + close_minute
        return None

    after_match = OPEN_AFTER_PATTERN.fullmatch(value)
    if after_match is not None:
        open_hour, open_minute = map(int, after_match.groups())
        return open_hour * 60 + open_minute, 24 * 60

    return None


def _is_closed(day_date: date, closed_days: list[str]) -> bool:
    weekday = WEEKDAYS_KO[day_date.weekday()]
    normalized = {_normalize(value) for value in closed_days}
    return _normalize(weekday) in normalized or _normalize(weekday[0]) in normalized


def _is_included_in_budget(category: str, budget_includes: list[str]) -> bool:
    if not budget_includes:
        return True
    normalized = {_normalize(value) for value in budget_includes}
    return bool(BUDGET_ALIASES[category] & normalized)


def check_daily_schedule(payload: PlanToVerificationInput) -> StandardCheck:
    issues: list[CheckIssue] = []
    trip = payload.trip_info
    days = payload.plan.days

    if trip.start_date > trip.end_date:
        return _check([_issue("INVALID_DATE_RANGE", "여행 시작일이 종료일보다 늦습니다.")])

    expected_day_count = (trip.end_date - trip.start_date).days + 1
    if len(days) != expected_day_count:
        issues.append(_issue("DAY_COUNT_MISMATCH", "계획의 일수와 여행 날짜 범위가 일치하지 않습니다."))

    seen_ids: set[str] = set()
    for index, day in enumerate(days):
        expected_day = index + 1
        expected_date = trip.start_date + timedelta(days=index)

        if day.day != expected_day:
            issues.append(_issue("INVALID_DAY_SEQUENCE", "일차 번호가 1부터 연속되지 않습니다.", day.day))
        if day.date != expected_date:
            issues.append(_issue("DATE_OUT_OF_RANGE", "날짜가 여행 날짜 범위와 일치하지 않습니다.", day.day))
        if day.items[0].travel_from_prev is not None:
            issues.append(_issue("INVALID_FIRST_TRAVEL", "첫 항목의 travel_from_prev는 null이어야 합니다.", day.day, day.items[0].id))
        for item in day.items[1:]:
            if item.travel_from_prev is None:
                issues.append(_issue("MISSING_TRAVEL", "이전 항목의 이동 정보가 없습니다.", day.day, item.id))
        is_last_trip_day = index == len(days) - 1
        if not is_last_trip_day and day.items[-1].category != "숙소":
            issues.append(_issue("LAST_ITEM_NOT_STAY", "마지막 여행일 전에는 하루의 마지막 항목이 숙소여야 합니다.", day.day, day.items[-1].id))
        if _minutes(day.items[0].start_time) < _minutes(trip.day_start_time):
            issues.append(_issue("BEFORE_DAY_START", "첫 일정이 허용 시작 시각보다 이릅니다.", day.day, day.items[0].id))
        if _minutes(day.items[-1].end_time) > _minutes(trip.day_end_time):
            issues.append(_issue("AFTER_DAY_END", "마지막 일정이 허용 종료 시각보다 늦습니다.", day.day, day.items[-1].id))

        for item in day.items:
            if item.id in seen_ids:
                issues.append(_issue("DUPLICATE_ITEM_ID", "일정 항목 ID가 중복됩니다.", day.day, item.id))
            seen_ids.add(item.id)

    return _check(issues)


def _check_item_physical_time(day: PlanDay, item: PlanItem) -> list[CheckIssue]:
    start = _minutes(item.start_time)
    end = _minutes(item.end_time)
    if start >= end:
        return [_issue("INVALID_TIME_RANGE", "종료 시각이 시작 시각보다 늦지 않습니다.", day.day, item.id)]
    if end - start != item.expected_duration_min:
        return [_issue("DURATION_MISMATCH", "일정 시간과 예상 체류시간이 일치하지 않습니다.", day.day, item.id)]
    return []


def check_physical_feasibility(payload: PlanToVerificationInput) -> StandardCheck:
    issues: list[CheckIssue] = []
    for day in payload.plan.days:
        for index, item in enumerate(day.items):
            issues.extend(_check_item_physical_time(day, item))
            if index == 0 or item.travel_from_prev is None:
                continue
            previous = day.items[index - 1]
            earliest_start = _minutes(previous.end_time) + item.travel_from_prev.estimated_min
            if _minutes(item.start_time) < earliest_start:
                shortage = earliest_start - _minutes(item.start_time)
                issues.append(
                    _issue(
                        "INSUFFICIENT_TRAVEL_TIME",
                        f"이전 일정에서 이동할 시간이 {shortage}분 부족합니다.",
                        day.day,
                        item.id,
                    )
                )
    return _check(issues)


def check_operating_hours(payload: PlanToVerificationInput) -> StandardCheck:
    issues: list[CheckIssue] = []
    for day in payload.plan.days:
        for item in day.items:
            if _is_closed(day.date, item.closed_days):
                issues.append(_issue("CLOSED_DAY", "방문일이 휴무일입니다.", day.day, item.id))

            opening_window = _parse_opening_hours(item.opening_hours)
            if opening_window is None:
                issues.append(_issue("INVALID_OPENING_HOURS", "opening_hours 형식을 확인할 수 없습니다.", day.day, item.id))
                continue

            opens_at, closes_at = opening_window
            start = _minutes(item.start_time)
            end = _minutes(item.end_time)
            if opens_at > closes_at or start < opens_at:
                issues.append(_issue("BEFORE_OPENING", "일정이 영업 시작 시각보다 이릅니다.", day.day, item.id))
            if opens_at <= closes_at and end > closes_at:
                issues.append(_issue("AFTER_CLOSING", "일정이 영업 종료 시각보다 늦습니다.", day.day, item.id))
    return _check(issues)


def check_budget(payload: PlanToVerificationInput) -> BudgetCheck:
    trip = payload.trip_info
    estimated_total = 0.0
    for day in payload.plan.days:
        for item in day.items:
            if not _is_included_in_budget(item.category, trip.budget_includes):
                continue
            multiplier = trip.num_travelers if item.price_unit == "per_person" else 1
            estimated_total += item.price * multiplier

    over_by = max(0.0, estimated_total - trip.budget_total)
    return BudgetCheck(
        status="fail" if over_by > 0 else "pass",
        budget_total=trip.budget_total,
        estimated_total=estimated_total,
        over_by=over_by,
        currency=trip.budget_currency,
    )


def check_must_visit(payload: PlanToVerificationInput) -> MustVisitCheck:
    item_names = [item.name for day in payload.plan.days for item in day.items]
    missing = [
        place
        for place in payload.trip_info.persona.must_visit
        if not any(_name_matches(place, name) for name in item_names)
    ]
    return MustVisitCheck(status="fail" if missing else "pass", missing=missing)


def check_avoid(payload: PlanToVerificationInput) -> AvoidCheck:
    matches: list[AvoidMatch] = []
    avoid_terms = [
        (value, value.strip().casefold())
        for value in payload.trip_info.persona.avoid
        if value.strip()
    ]
    for day in payload.plan.days:
        for item in day.items:
            haystack = " ".join(
                [item.name, item.category, item.note, item.physical_intensity]
            ).casefold()
            for original, normalized in avoid_terms:
                if normalized in haystack:
                    matches.append(
                        AvoidMatch(
                            avoid=original,
                            message=(
                                f"회피 조건 '{original}'이 일정 항목 '{item.name}'과 "
                                "직접적으로 겹칠 수 있습니다."
                            ),
                            day=day.day,
                            item_id=item.id,
                        )
                    )
                    continue
                travel = item.travel_from_prev
                if (
                    "도보" in normalized
                    and travel is not None
                    and travel.distance_km >= 3.0
                ):
                    matches.append(
                        AvoidMatch(
                            avoid=original,
                            message=(
                                f"회피 조건 '{original}'이 있는데 '{item.name}'로 이동하는 "
                                f"구간 거리가 {travel.distance_km:g}km입니다."
                            ),
                            day=day.day,
                            item_id=item.id,
                        )
                    )
    return AvoidCheck(status="warning" if matches else "pass", matched=matches)


def check_pace(payload: PlanToVerificationInput) -> StandardCheck:
    max_items = PACE_MAX_ITEMS.get(payload.trip_info.persona.pace, 4)
    issues: list[CheckIssue] = []
    for day in payload.plan.days:
        visit_count = sum(1 for item in day.items if item.category != "숙소")
        if visit_count > max_items:
            issues.append(
                _issue(
                    "PACE_TOO_DENSE",
                    (
                        f"요청한 페이스({payload.trip_info.persona.pace}) 기준 하루 "
                        f"{max_items}곳 이하가 적절하지만 {visit_count}곳이 배치됐습니다."
                    ),
                    day.day,
                )
            )
    return StandardCheck(status="warning" if issues else "pass", issues=issues)


def check_walking_level(payload: PlanToVerificationInput) -> StandardCheck:
    limit = INTENSITY_RANK.get(payload.trip_info.persona.max_walking_level, 1)
    issues: list[CheckIssue] = []
    for day in payload.plan.days:
        for item in day.items:
            item_rank = INTENSITY_RANK.get(item.physical_intensity, 1)
            if item_rank > limit:
                issues.append(
                    _issue(
                        "WALKING_LEVEL_EXCEEDED",
                        (
                            f"요청한 최대 걷기 수준({payload.trip_info.persona.max_walking_level})보다 "
                            f"활동 강도({item.physical_intensity})가 높은 일정입니다."
                        ),
                        day.day,
                        item.id,
                    )
                )
            travel = item.travel_from_prev
            if limit == 0 and travel is not None and travel.distance_km >= 2.0:
                issues.append(
                    _issue(
                        "LONG_TRAVEL_DISTANCE_FOR_LOW_WALKING",
                        (
                            f"걷기 수준을 낮음으로 요청했지만 '{item.name}' 이동 구간 거리가 "
                            f"{travel.distance_km:g}km입니다."
                        ),
                        day.day,
                        item.id,
                    )
                )
    return StandardCheck(status="fail" if issues else "pass", issues=issues)


def build_rule_checks(payload: PlanToVerificationInput) -> VerificationChecks:
    return VerificationChecks(
        physical_feasibility=check_physical_feasibility(payload),
        budget=check_budget(payload),
        operating_hours=check_operating_hours(payload),
        daily_schedule=check_daily_schedule(payload),
        must_visit=check_must_visit(payload),
        avoid=check_avoid(payload),
        pace=check_pace(payload),
        walking_level=check_walking_level(payload),
    )
