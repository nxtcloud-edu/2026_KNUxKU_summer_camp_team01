"""자기 검증기 — 산출 직전에 검증 에이전트의 판정을 미리 돌린다.

## 왜 필요한가

Plan Agent가 만든 일정은 곧바로 Verification Agent로 넘어간다. 거기서 `fail`이
나면 사용자에게 "실행하기 어려운 일정"이 표시된다. 그런데 그 실패의 원인은
대부분 Plan Agent가 지킬 수 있었던 조건들이다.

그래서 산출 직전에 **검증 에이전트와 같은 판정을 우리가 먼저 돌린다.** 걸리면
고치고, 못 고치면 최소한 무엇이 왜 걸렸는지 명시한다.

## 조용히 버리지 않는다

이 모듈의 모든 함수는 위반을 `Violation` 목록으로 **반환**한다. 조건을 못 맞춘
항목을 `continue`로 건너뛰거나 빈 값으로 채워 통과시키지 않는다. 그렇게 하면
"왜 이 장소가 사라졌지"를 나중에 디버깅하게 된다.

## 대응하는 검증 에이전트 규칙

| 여기 함수 | rules.py 함수 | 검증 결과 키 |
|---|---|---|
| `check_daily_schedule` | `check_daily_schedule` | `daily_schedule` |
| `check_physical_feasibility` | `check_physical_feasibility` | `physical_feasibility` |
| `check_operating_hours` | `check_operating_hours` | `operating_hours` |
| `check_must_visit` | `check_must_visit` | `must_visit` |
| `budget.check_budget` | `check_budget` | `budget` |

`avoid` · `pace` · `walking_level`은 검증 에이전트가 Gemini로 판단하는 주관 항목
이므로 여기서 흉내내지 않는다. 대신 Plan Agent는 배치 단계에서 `pace`와
`max_walking_level`을 제약으로 반영한다.
"""

from __future__ import annotations

from .config import CONFIG
from . import timecalc
from .budget import check_budget
from .models import (
    PlanDay,
    PlanItem,
    PlanToVerificationInput,
    SearchToPlanInput,
    Violation,
)


# ── 입력 단계 검사 ────────────────────────────────────────────


def check_input_usable(payload: SearchToPlanInput) -> list[Violation]:
    """받은 입력만으로 계약을 지키는 일정을 만들 수 있는지 미리 확인한다.

    특히 `opening_hours`가 검증 에이전트의 정규식으로 파싱되지 않으면, 그 장소를
    어디에 배치하든 `INVALID_OPENING_HOURS`로 fail이 된다. 배치를 시작하기 전에
    알아야 한다. 이걸 통과시켜 놓고 뒤에서 실패하는 것이 가장 나쁘다.
    """

    violations: list[Violation] = []
    trip = payload.trip_info

    if timecalc.parse_date(trip.start_date) > timecalc.parse_date(trip.end_date):
        violations.append(
            Violation(
                code="INVALID_DATE_RANGE",
                message="여행 시작일이 종료일보다 늦습니다.",
            )
        )

    if timecalc.to_minutes(trip.day_start_time) >= timecalc.to_minutes(trip.day_end_time):
        violations.append(
            Violation(
                code="INVALID_DAY_WINDOW",
                message="day_start_time이 day_end_time보다 늦거나 같습니다.",
            )
        )

    seen_ids: set[str] = set()
    for place in payload.selected.places:
        if place.id in seen_ids:
            violations.append(
                Violation(
                    code="DUPLICATE_PLACE_ID",
                    message=f"선택된 장소 id가 중복됩니다: {place.id}",
                    item_id=place.id,
                )
            )
        seen_ids.add(place.id)

        if (
            timecalc.parse_opening_hours(place.opening_hours) is None
            and not CONFIG.strict_facts
        ):
            violations.append(
                Violation(
                    code="INVALID_OPENING_HOURS",
                    message=(
                        f"'{place.name}'의 opening_hours를 검증 에이전트가 "
                        f"파싱할 수 없는 형식입니다: {place.opening_hours!r}. "
                        "'HH:MM-HH:MM' 또는 'HH:MM 이후'만 인정됩니다."
                    ),
                    item_id=place.id,
                )
            )

        if place.expected_duration_min <= 0:
            violations.append(
                Violation(
                    code="INVALID_DURATION",
                    message=f"'{place.name}'의 expected_duration_min이 0 이하입니다.",
                    item_id=place.id,
                )
            )

    # 필수 방문지가 선택 목록에 실제로 있는지. 없으면 어떻게 배치해도
    # `must_visit` 검사가 fail이다.
    available = [place.name for place in payload.selected.places]
    if payload.selected.stay is not None:
        available.append(payload.selected.stay.name)
    for required in trip.persona.must_visit:
        if not any(_name_matches(required, name) for name in available):
            violations.append(
                Violation(
                    code="MUST_VISIT_NOT_SELECTED",
                    message=(
                        f"필수 방문지 '{required}'가 선택 결과에 없습니다. "
                        "Plan Agent는 장소를 만들어낼 수 없으므로 Search 단계에서 "
                        "포함되어야 합니다."
                    ),
                )
            )

    total_days = timecalc.day_count(trip.start_date, trip.end_date)
    if not CONFIG.strict_facts and total_days > 1:
        has_stay_category = any(
            place.category == "숙소" for place in payload.selected.places
        )
        if payload.selected.stay is None and not has_stay_category:
            violations.append(
                Violation(
                    code="STAY_REQUIRED_FOR_MULTIDAY",
                    message=(
                        f"{total_days}일 일정인데 숙소가 선택되지 않았습니다. "
                        "검증 규칙상 마지막 날을 제외한 모든 날의 마지막 항목이 "
                        "숙소여야 하므로, 숙소 없이는 통과할 수 없습니다."
                    ),
                )
            )

    # 모든 날이 휴무일인 장소는 어디에도 배치할 수 없다.
    all_dates = [timecalc.add_days(trip.start_date, offset) for offset in range(total_days)]
    for place in payload.selected.places:
        if all(
            timecalc.is_closed_on(date_str, list(place.closed_days))
            for date_str in all_dates
        ):
            violations.append(
                Violation(
                    code="CLOSED_ON_ALL_DAYS",
                    message=(
                        f"'{place.name}'은 여행 기간 전체가 휴무일입니다 "
                        f"(휴무: {', '.join(place.closed_days)})."
                    ),
                    item_id=place.id,
                )
            )

    return violations


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


# ── 산출 단계 검사 (rules.py 복제) ────────────────────────────


def check_daily_schedule(payload: PlanToVerificationInput) -> list[Violation]:
    """rules.py `check_daily_schedule`와 같은 판정."""

    violations: list[Violation] = []
    trip = payload.trip_info
    days = payload.plan.days

    start = timecalc.parse_date(trip.start_date)
    end = timecalc.parse_date(trip.end_date)
    if start > end:
        return [
            Violation(code="INVALID_DATE_RANGE", message="여행 시작일이 종료일보다 늦습니다.")
        ]

    expected_day_count = timecalc.day_count(trip.start_date, trip.end_date)
    if len(days) != expected_day_count:
        violations.append(
            Violation(
                code="DAY_COUNT_MISMATCH",
                message=(
                    f"계획 일수 {len(days)}가 여행 기간 {expected_day_count}일과 "
                    "일치하지 않습니다."
                ),
            )
        )

    seen_ids: set[str] = set()
    for index, day in enumerate(days):
        expected_day = index + 1
        expected_date = timecalc.add_days(trip.start_date, index)

        if day.day != expected_day:
            violations.append(
                Violation(
                    code="INVALID_DAY_SEQUENCE",
                    message=f"일차 번호가 1부터 연속되지 않습니다 (기대 {expected_day}).",
                    day=day.day,
                )
            )
        if day.date != expected_date:
            violations.append(
                Violation(
                    code="DATE_OUT_OF_RANGE",
                    message=f"날짜가 {expected_date}이어야 합니다.",
                    day=day.day,
                )
            )

        if day.items[0].travel_from_prev is not None:
            violations.append(
                Violation(
                    code="INVALID_FIRST_TRAVEL",
                    message="첫 항목의 travel_from_prev는 null이어야 합니다.",
                    day=day.day,
                    item_id=day.items[0].id,
                )
            )
        for item in day.items[1:]:
            if item.travel_from_prev is None:
                violations.append(
                    Violation(
                        code="MISSING_TRAVEL",
                        message="이전 항목의 이동 정보가 없습니다.",
                        day=day.day,
                        item_id=item.id,
                    )
                )

        is_last_trip_day = index == len(days) - 1
        if (
            not CONFIG.strict_facts
            and not is_last_trip_day
            and day.items[-1].category != "숙소"
        ):
            violations.append(
                Violation(
                    code="LAST_ITEM_NOT_STAY",
                    message="마지막 여행일 전에는 하루의 마지막 항목이 숙소여야 합니다.",
                    day=day.day,
                    item_id=day.items[-1].id,
                )
            )

        # 항공편 항목은 예외다. 도착·출발 시각은 실제 비행 시각이지 사용자가
        # 정한 "활동 시작/종료 허용 시각" 선호가 아니다. 이른 아침 도착
        # 항공편을 BEFORE_DAY_START로 잡으면 매번 위반이 나게 된다.
        if day.items[0].category != "항공" and timecalc.to_minutes(
            day.items[0].start_time
        ) < timecalc.to_minutes(trip.day_start_time):
            violations.append(
                Violation(
                    code="BEFORE_DAY_START",
                    message=(
                        f"첫 일정 {day.items[0].start_time}이 허용 시작 시각 "
                        f"{trip.day_start_time}보다 이릅니다."
                    ),
                    day=day.day,
                    item_id=day.items[0].id,
                )
            )
        if day.items[-1].category != "항공" and timecalc.to_minutes(
            day.items[-1].end_time
        ) > timecalc.to_minutes(trip.day_end_time):
            violations.append(
                Violation(
                    code="AFTER_DAY_END",
                    message=(
                        f"마지막 일정 {day.items[-1].end_time}이 허용 종료 시각 "
                        f"{trip.day_end_time}보다 늦습니다."
                    ),
                    day=day.day,
                    item_id=day.items[-1].id,
                )
            )

        for item in day.items:
            if item.id in seen_ids:
                violations.append(
                    Violation(
                        code="DUPLICATE_ITEM_ID",
                        message="일정 항목 ID가 중복됩니다.",
                        day=day.day,
                        item_id=item.id,
                    )
                )
            seen_ids.add(item.id)

    return violations


def _check_item_physical_time(day: PlanDay, item: PlanItem) -> list[Violation]:
    start = timecalc.to_minutes(item.start_time)
    end = timecalc.to_minutes(item.end_time)
    if start >= end:
        return [
            Violation(
                code="INVALID_TIME_RANGE",
                message="종료 시각이 시작 시각보다 늦지 않습니다.",
                day=day.day,
                item_id=item.id,
            )
        ]
    if end - start != item.expected_duration_min:
        return [
            Violation(
                code="DURATION_MISMATCH",
                message=(
                    f"일정 시간 {end - start}분과 expected_duration_min "
                    f"{item.expected_duration_min}분이 일치하지 않습니다."
                ),
                day=day.day,
                item_id=item.id,
            )
        ]
    return []


def check_physical_feasibility(payload: PlanToVerificationInput) -> list[Violation]:
    """rules.py `check_physical_feasibility`와 같은 판정."""

    violations: list[Violation] = []
    for day in payload.plan.days:
        for index, item in enumerate(day.items):
            violations.extend(_check_item_physical_time(day, item))
            if index == 0 or item.travel_from_prev is None:
                continue
            previous = day.items[index - 1]
            earliest = (
                timecalc.to_minutes(previous.end_time)
                + item.travel_from_prev.estimated_min
            )
            actual = timecalc.to_minutes(item.start_time)
            if actual < earliest:
                violations.append(
                    Violation(
                        code="INSUFFICIENT_TRAVEL_TIME",
                        message=f"이전 일정에서 이동할 시간이 {earliest - actual}분 부족합니다.",
                        day=day.day,
                        item_id=item.id,
                    )
                )
    return violations


def check_operating_hours(payload: PlanToVerificationInput) -> list[Violation]:
    """rules.py `check_operating_hours`와 같은 판정."""

    violations: list[Violation] = []
    for day in payload.plan.days:
        for item in day.items:
            if timecalc.is_closed_on(day.date, list(item.closed_days)):
                violations.append(
                    Violation(
                        code="CLOSED_DAY",
                        message=(
                            f"방문일 {day.date}({timecalc.weekday_ko(day.date)})은 "
                            f"'{item.name}'의 휴무일입니다."
                        ),
                        day=day.day,
                        item_id=item.id,
                    )
                )

            window = timecalc.parse_opening_hours(item.opening_hours)
            if window is None:
                if CONFIG.strict_facts:
                    continue
                violations.append(
                    Violation(
                        code="INVALID_OPENING_HOURS",
                        message=f"opening_hours 형식을 확인할 수 없습니다: {item.opening_hours!r}",
                        day=day.day,
                        item_id=item.id,
                    )
                )
                continue

            opens_at, closes_at = window
            start = timecalc.to_minutes(item.start_time)
            end = timecalc.to_minutes(item.end_time)
            if opens_at > closes_at or start < opens_at:
                violations.append(
                    Violation(
                        code="BEFORE_OPENING",
                        message=(
                            f"일정 {item.start_time}이 영업 시작 "
                            f"{timecalc.to_hhmm(opens_at)}보다 이릅니다."
                        ),
                        day=day.day,
                        item_id=item.id,
                    )
                )
            if opens_at <= closes_at and end > closes_at:
                violations.append(
                    Violation(
                        code="AFTER_CLOSING",
                        message=(
                            f"일정 {item.end_time}이 영업 종료 "
                            f"{closes_at // 60:02d}:{closes_at % 60:02d}보다 늦습니다."
                        ),
                        day=day.day,
                        item_id=item.id,
                    )
                )
    return violations


def check_must_visit(payload: PlanToVerificationInput) -> list[Violation]:
    """rules.py `check_must_visit`와 같은 판정."""

    names = [item.name for day in payload.plan.days for item in day.items]
    missing = [
        place
        for place in payload.trip_info.persona.must_visit
        if not any(_name_matches(place, name) for name in names)
    ]
    if not missing:
        return []
    return [
        Violation(
            code="MUST_VISIT_MISSING",
            message="필수 방문지가 일정에 없습니다: " + ", ".join(missing),
        )
    ]


def check_names_are_grounded(
    payload: PlanToVerificationInput, source: SearchToPlanInput
) -> list[Violation]:
    """일정 항목 이름이 전부 Search 선택 결과에서 왔는지 확인한다.

    `conformance.mjs`의 cross-handoff 검사와 같은 조건이다. Plan Agent가 장소를
    창작하면 여기서 걸린다.
    """

    available = {_normalize(place.name) for place in source.selected.places}
    if source.selected.stay is not None:
        available.add(_normalize(source.selected.stay.name))

    violations: list[Violation] = []
    for day in payload.plan.days:
        for item in day.items:
            # 항공편 항목은 Plan Agent가 flights.py에서 직접 합성한다
            # (search 선택 결과에는 "출국 항공편" 같은 장소 이름이 없다).
            if item.category == "항공":
                continue
            if _normalize(item.name) not in available:
                violations.append(
                    Violation(
                        code="UNGROUNDED_ITEM_NAME",
                        message=(
                            f"'{item.name}'은 Search 선택 결과에 없는 이름입니다. "
                            "Plan Agent는 장소를 만들어낼 수 없습니다."
                        ),
                        day=day.day,
                        item_id=item.id,
                    )
                )
    return violations


def check_trip_info_unchanged(
    payload: PlanToVerificationInput, source: SearchToPlanInput
) -> list[Violation]:
    """`trip_info`를 한 글자도 바꾸지 않았는지 확인한다.

    `conformance.mjs`가 두 handoff의 `trip_info`를 deepEqual로 비교한다.
    직렬화 과정에서 시각에 초가 붙는 것 같은 변화도 여기서 잡힌다.
    """

    produced = payload.trip_info.model_dump(mode="json")
    original = source.trip_info.model_dump(mode="json")
    if produced == original:
        return []

    changed = sorted(
        key
        for key in set(produced) | set(original)
        if produced.get(key) != original.get(key)
    )
    return [
        Violation(
            code="TRIP_INFO_MUTATED",
            message=(
                "trip_info가 입력과 달라졌습니다. 그대로 넘겨야 합니다. "
                f"달라진 필드: {', '.join(changed)}"
            ),
        )
    ]


def verify_all(
    payload: PlanToVerificationInput, source: SearchToPlanInput | None = None
) -> list[Violation]:
    """산출 직전 전체 검사. 통과하면 빈 목록.

    `source`를 주면 그라운딩(이름 창작 여부)과 `trip_info` 불변까지 확인한다.
    """

    violations: list[Violation] = []
    violations.extend(check_daily_schedule(payload))
    violations.extend(check_physical_feasibility(payload))
    violations.extend(check_operating_hours(payload))
    violations.extend(check_must_visit(payload))
    violations.extend(check_budget(payload))
    if source is not None:
        violations.extend(check_names_are_grounded(payload, source))
        violations.extend(check_trip_info_unchanged(payload, source))
    return violations


__all__ = [
    "check_daily_schedule",
    "check_input_usable",
    "check_must_visit",
    "check_names_are_grounded",
    "check_operating_hours",
    "check_physical_feasibility",
    "check_trip_info_unchanged",
    "verify_all",
]
