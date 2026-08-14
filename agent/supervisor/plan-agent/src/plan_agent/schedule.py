"""시각 확정 — 배치된 장소에 실제 시작·종료 시각을 넣는다.

검증 에이전트의 규칙 대부분이 이 단계의 산출물을 본다. 그래서 여기서 만드는
모든 항목은 **만들자마자 조건을 만족해야** 한다. 나중에 검사해서 고치는 것보다
애초에 어기지 않는 편이 낫다.

## 반드시 지키는 조건

| 조건 | 어기면 나오는 검증 코드 |
|---|---|
| `end - start == expected_duration_min` | `DURATION_MISMATCH` |
| `start >= 이전 종료 + 이동시간` | `INSUFFICIENT_TRAVEL_TIME` |
| `start >= 영업 시작`, `end <= 영업 종료` | `BEFORE_OPENING` / `AFTER_CLOSING` |
| 첫 항목 `start >= day_start_time` | `BEFORE_DAY_START` |
| 마지막 항목 `end <= day_end_time` | `AFTER_DAY_END` |
| 첫 항목 `travel_from_prev is None`, 나머지는 값 있음 | `INVALID_FIRST_TRAVEL` / `MISSING_TRAVEL` |
| 마지막 여행일 외에는 마지막 항목이 `숙소` | `LAST_ITEM_NOT_STAY` |
| 항목 id가 전체에서 유일 | `DUPLICATE_ITEM_ID` |

## 넣지 못한 항목

시간이 안 맞아 넣지 못한 장소는 **조용히 사라지지 않는다.** `overflow`에 이유와
함께 담아 호출부가 재배치를 시도하거나 사용자에게 보고할 수 있게 한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import budget, routing, timecalc
from .allocate import AllocationResult
from .models import (
    PlanDay,
    PlanItem,
    SelectedPlace,
    SelectedStay,
    TripInfo,
)

logger = logging.getLogger(__name__)

# 숙소 체크인 항목의 체류시간. `SelectedStay`에는 소요시간 필드가 없어서
# 우리가 정한다. 공식 fixture도 30분을 쓴다.
STAY_ITEM_DURATION_MIN = 30

# 숙소 항목의 활동 강도. 체크인은 이동이 아니므로 가장 낮은 값.
STAY_INTENSITY = "낮음"


@dataclass
class Overflow:
    place_id: str
    place_name: str
    day_number: int
    reason: str


@dataclass
class ScheduleResult:
    days: list[PlanDay]
    overflow: list[Overflow] = field(default_factory=list)
    # 항목이 하나도 없어서 만들지 못한 날의 일차 번호.
    # 계약이 하루 최소 1개 항목을 요구하므로 빈 `PlanDay`를 만들 수 없다.
    empty_days: list[int] = field(default_factory=list)
    estimated_leg_count: int = 0
    total_leg_count: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def used_estimates(self) -> bool:
        return self.estimated_leg_count > 0


def _stay_occurrence_days(total_days: int) -> list[int]:
    """숙소 항목이 들어갈 일차(1부터).

    검증 규칙은 **마지막 여행일을 뺀 모든 날**의 마지막 항목이 `숙소`이기를
    요구한다. 그래서 1..(총일수-1)에 들어간다. 이 개수가 곧 숙박 일수다.

    총 1일이면 숙박이 0박이지만, 숙소를 선택했다면 그 날에 한 번 넣는다.
    공식 fixture가 그렇게 되어 있고, 마지막 날에 숙소를 두는 것은 규칙 위반이
    아니다(규칙은 비마지막 날에 대해서만 요구한다).
    """

    if total_days <= 1:
        return [1]
    return list(range(1, total_days))


def _needs_stay_on_day(
    day_number: int,
    stay_days: list[int],
    day_place_count: int,
    is_last_day: bool,
    has_stay: bool,
) -> bool:
    """이 날에 숙소 항목을 넣어야 하는가.

    기본은 `stay_days`(마지막 날 제외)다. 여기에 예외가 하나 있다.

    **마지막 날에 넣을 장소가 하나도 없으면 숙소를 넣는다.** 계약은 하루에
    최소 1개 항목을 요구하므로 빈 날은 만들 수 없고, 빈 날 때문에 일정 생성을
    포기하는 것보다 숙소(체크아웃) 항목으로 채우는 편이 낫다. 마지막 날에
    숙소를 두는 것은 규칙 위반이 아니다 — `LAST_ITEM_NOT_STAY`는 비마지막
    날에 대해서만 숙소를 요구한다.
    """

    if not has_stay:
        return False
    if day_number in stay_days:
        return True
    return is_last_day and day_place_count == 0


def build_schedule(
    allocation: AllocationResult,
    places: list[SelectedPlace],
    trip: TripInfo,
    stay: SelectedStay | None,
) -> ScheduleResult:
    """배치 결과에 시각을 넣어 계약 형식의 일자 목록을 만든다."""

    by_id = {place.id: place for place in places}
    total_days = len(allocation.days)
    day_start = timecalc.to_minutes(trip.day_start_time)
    day_end = timecalc.to_minutes(trip.day_end_time)

    stay_days = _stay_occurrence_days(total_days) if stay is not None else []
    stay_prices = (
        budget.distribute_stay_price(stay.price, len(stay_days))
        if stay is not None and stay_days
        else []
    )

    result = ScheduleResult(days=[])

    for day_index, day_allocation in enumerate(allocation.days):
        day_number = day_allocation.day_number
        is_last_day = day_index == total_days - 1
        # 요금이 배정된 숙박일인가. 마지막 날 예외로 추가되는 체크아웃 항목은
        # 여기 해당하지 않으므로 요금이 0이다.
        is_paid_night = day_number in stay_days
        needs_stay = is_paid_night

        items: list[PlanItem] = []
        cursor = day_start  # 지금까지 채워진 시각
        last_point: tuple[float, float] | None = None

        for place_id in day_allocation.place_ids:
            place = by_id.get(place_id)
            if place is None:
                # 있을 수 없는 상황이지만, 조용히 넘기면 장소가 사라진다.
                result.overflow.append(
                    Overflow(
                        place_id=place_id,
                        place_name=place_id,
                        day_number=day_number,
                        reason="선택 목록에서 장소를 찾지 못했습니다",
                    )
                )
                continue

            placed = _place_item(
                place=place,
                items=items,
                cursor=cursor,
                last_point=last_point,
                day_start=day_start,
                day_end=day_end,
                day_number=day_number,
                transport_mode=trip.transport_mode,
                reserve_minutes=_reserve_for_stay(needs_stay, last_point, place, stay),
                result=result,
            )
            if placed is None:
                continue
            item, cursor, last_point = placed
            items.append(item)

        # 장소 배치가 끝난 뒤 다시 판단한다. 마지막 날에 넣을 장소가 없으면
        # 빈 날을 만드는 대신 체크아웃 항목으로 채운다.
        needs_stay = _needs_stay_on_day(
            day_number=day_number,
            stay_days=stay_days,
            day_place_count=len(items),
            is_last_day=is_last_day,
            has_stay=stay is not None,
        )

        if needs_stay and stay is not None:
            stay_price = (
                stay_prices[stay_days.index(day_number)]
                if is_paid_night and stay_prices
                else 0.0
            )
            stay_item = _build_stay_item(
                stay=stay,
                items=items,
                cursor=cursor,
                last_point=last_point,
                day_start=day_start,
                day_end=day_end,
                day_number=day_number,
                transport_mode=trip.transport_mode,
                price=stay_price,
                result=result,
            )
            if stay_item is not None:
                items.append(stay_item)

        if not items:
            # 계약은 하루에 최소 1개 항목을 요구한다(`items` minItems: 1).
            # `PlanDay`를 만들면 Pydantic이 예외를 던지고, 그러면 스트림이
            # 종료 이벤트 없이 끊겨 화면이 멈춘다. 그래서 여기서는 날을
            # 만들지 않고 `empty_days`에 기록해 호출부가 판단하게 한다.
            result.empty_days.append(day_number)
            result.notes.append(
                f"Day {day_number}({day_allocation.date})에 배치할 항목이 없습니다."
            )
            continue

        # id를 마지막에 다시 매겨 순서와 일치시킨다. 패턴은 ^d[1-9]\d*-[1-9]\d*$.
        renumbered = [
            item.model_copy(update={"id": f"d{day_number}-{position}"})
            for position, item in enumerate(items, start=1)
        ]

        result.days.append(
            PlanDay(
                day=day_number,
                date=day_allocation.date,
                items=renumbered,
            )
        )

    return result


def _reserve_for_stay(
    needs_stay: bool,
    last_point: tuple[float, float] | None,
    place: SelectedPlace,
    stay: SelectedStay | None,
) -> int:
    """숙소 항목을 넣을 시간을 미리 남겨둔다.

    남겨두지 않으면 관광지로 하루를 꽉 채운 뒤 숙소를 못 넣어
    `LAST_ITEM_NOT_STAY`가 된다. 이동시간은 좌표 기반으로 대략만 잡는다
    (정확한 값은 실제로 넣을 때 구한다).
    """

    if not needs_stay or stay is None:
        return 0
    estimate = routing.estimate_leg(
        (place.lat, place.lng), (stay.lat, stay.lng), "대중교통"
    )
    return estimate.minutes + STAY_ITEM_DURATION_MIN


def _place_item(
    *,
    place: SelectedPlace,
    items: list[PlanItem],
    cursor: int,
    last_point: tuple[float, float] | None,
    day_start: int,
    day_end: int,
    day_number: int,
    transport_mode: str,
    reserve_minutes: int,
    result: ScheduleResult,
) -> tuple[PlanItem, int, tuple[float, float]] | None:
    """장소 하나를 넣는다. 조건을 못 맞추면 None을 돌려주고 overflow에 기록한다."""

    window = timecalc.parse_opening_hours(place.opening_hours)
    if window is None:
        # 입력 검사에서 이미 걸러졌어야 한다. 여기까지 왔다면 그대로 넣으면
        # 검증에서 INVALID_OPENING_HOURS가 되므로 넣지 않고 보고한다.
        result.overflow.append(
            Overflow(
                place_id=place.id,
                place_name=place.name,
                day_number=day_number,
                reason=f"영업시간 형식을 해석할 수 없습니다: {place.opening_hours!r}",
            )
        )
        return None

    opens_at, closes_at = window

    travel = None
    earliest = max(cursor, day_start)
    if items:
        assert last_point is not None
        travel = routing.estimate_leg(
            last_point, (place.lat, place.lng), transport_mode
        )
        earliest = cursor + travel.minutes
        result.total_leg_count += 1
        if travel.is_estimated:
            result.estimated_leg_count += 1
            logger.info(
                "Day %d '%s' 이동시간을 좌표 기반으로 추정했습니다 (%d분, %.2fkm)",
                day_number,
                place.name,
                travel.minutes,
                travel.distance_km,
            )

    start = max(earliest, opens_at, day_start)
    end = start + place.expected_duration_min

    if end > closes_at:
        result.overflow.append(
            Overflow(
                place_id=place.id,
                place_name=place.name,
                day_number=day_number,
                reason=(
                    f"영업 종료({timecalc.to_hhmm(min(closes_at, timecalc.MINUTES_PER_DAY - 1))})"
                    f" 전에 {place.expected_duration_min}분을 넣을 수 없습니다"
                ),
            )
        )
        return None

    if end + reserve_minutes > day_end:
        result.overflow.append(
            Overflow(
                place_id=place.id,
                place_name=place.name,
                day_number=day_number,
                reason=(
                    "하루 종료 시각까지 남은 시간이 부족합니다"
                    + (f" (숙소 이동·체크인 {reserve_minutes}분 확보 필요)" if reserve_minutes else "")
                ),
            )
        )
        return None

    item = PlanItem(
        id=f"d{day_number}-{len(items) + 1}",
        name=place.name,
        category=place.category,
        start_time=timecalc.to_hhmm(start),
        end_time=timecalc.to_hhmm(end),
        lat=place.lat,
        lng=place.lng,
        price=place.price,
        price_unit=place.price_unit,
        opening_hours=place.opening_hours,
        closed_days=list(place.closed_days),
        expected_duration_min=place.expected_duration_min,
        physical_intensity=place.physical_intensity,
        note=place.note,
        travel_from_prev=travel.to_contract() if travel is not None else None,
    )
    return item, end, (place.lat, place.lng)


def _build_stay_item(
    *,
    stay: SelectedStay,
    items: list[PlanItem],
    cursor: int,
    last_point: tuple[float, float] | None,
    day_start: int,
    day_end: int,
    day_number: int,
    transport_mode: str,
    price: float,
    result: ScheduleResult,
) -> PlanItem | None:
    """숙소 체크인 항목을 만든다.

    `SelectedStay`에는 `category`·`opening_hours`·`expected_duration_min`·
    `physical_intensity`가 없다. 계약이 요구하므로 우리가 합성한다.

    - `category`: `숙소`
    - `opening_hours`: `체크인 HH:MM 이후` (검증 에이전트가 파싱할 수 있는 형식)
    - `expected_duration_min`: 30분
    - `physical_intensity`: `낮음`
    - `price`: 숙박 총액을 밤 수로 나눈 1박 요금 (중복 가산 방지)
    """

    opening_hours = timecalc.format_open_after(stay.check_in_time)
    check_in = timecalc.to_minutes(stay.check_in_time)

    travel = None
    earliest = max(cursor, day_start)
    if items:
        assert last_point is not None
        travel = routing.estimate_leg(
            last_point, (stay.lat, stay.lng), transport_mode
        )
        earliest = cursor + travel.minutes
        result.total_leg_count += 1
        if travel.is_estimated:
            result.estimated_leg_count += 1
            logger.info(
                "Day %d 숙소 이동시간을 좌표 기반으로 추정했습니다 (%d분)",
                day_number,
                travel.minutes,
            )

    start = max(earliest, check_in, day_start)
    end = start + STAY_ITEM_DURATION_MIN

    if end > day_end:
        # 숙소를 못 넣으면 그 날은 LAST_ITEM_NOT_STAY가 된다. 치명적이므로
        # 조용히 넘기지 않고 명시한다.
        result.notes.append(
            f"Day {day_number}: 체크인 {stay.check_in_time} 기준으로 숙소 항목을 "
            f"하루 종료 {timecalc.to_hhmm(day_end)} 안에 넣을 수 없습니다."
        )
        return None

    return PlanItem(
        id=f"d{day_number}-{len(items) + 1}",
        name=stay.name,
        category="숙소",
        start_time=timecalc.to_hhmm(start),
        end_time=timecalc.to_hhmm(end),
        lat=stay.lat,
        lng=stay.lng,
        price=price,
        price_unit="per_stay",
        opening_hours=opening_hours,
        closed_days=[],
        expected_duration_min=STAY_ITEM_DURATION_MIN,
        physical_intensity=STAY_INTENSITY,
        note=stay.note,
        travel_from_prev=travel.to_contract() if travel is not None else None,
    )


__all__ = [
    "STAY_INTENSITY",
    "STAY_ITEM_DURATION_MIN",
    "Overflow",
    "ScheduleResult",
    "build_schedule",
]
