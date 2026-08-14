"""선택된 항공편을 일정 항목(PlanItem)과 하루 경계 조정값으로 바꾼다.

## 왜 필요한가

`SearchToPlanInput.selected.flight`는 지금까지 어디에서도 쓰이지 않았다.
`trip_info.day_start_time`/`day_end_time`은 사용자가 정한 "활동을 시작/종료해도
되는 시각" 선호일 뿐, 실제 항공편 도착·출발 시각과 무관하게 고정값이었다.
그 결과 도착이 오후여도 첫날 일정이 오전부터 잡히고, 귀국 항공편이 오전
출발이어도 마지막 날이 저녁까지 꽉 찰 수 있었다.

## 이 모듈이 하는 일 두 가지

1. **하루 경계 조정** — 도착일의 실질 시작 시각을 "도착 시각 + 공항 이탈
   버퍼"로, 출발일의 실질 종료 시각을 "출발 시각 - 공항 수속 버퍼"로 낮춘다.
   (`compute_day_overrides`)
2. **항공편 항목 생성** — 출국편을 Day 1의 첫 항목으로, 귀국편을 마지막 날의
   마지막 항목으로 만든다. (`build_outbound_item` / `build_inbound_item`)

## 좌표에 대한 정직한 타협

`SelectedFlight`에는 공항 좌표가 없다(공급자 응답에 없다). 항목은 계약상 실제
좌표가 있어야 하므로, 숙소 좌표(없으면 선택 장소들의 중심 좌표)로 근사하고
`note`에 `[DEMO DATA]`로 명시한다. 공항까지의 이동시간도 실제 경로를 모르므로
고정 버퍼를 쓰고 `distance_km=0.0`으로 "추정 아님, 정책값"임을 드러낸다.
숨기지 않고 드러내는 쪽이 이 프로젝트의 원칙이다.

## 자정을 넘는 항공편

`PlanItem.start_time`/`end_time`은 하루 안의 시각만 표현할 수 있다. 이
프로젝트의 대상(한국↔일본 등 근거리) 항공편은 사실상 항상 당일 안에 끝나므로
문제가 되지 않지만, 혹시라도 자정을 넘기면 항목을 만들지 않고 이유를
반환한다 — 조용히 잘못된 시각을 만드는 것보다 낫다.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import timecalc
from .models import FlightTravelLeg, SelectedFlight, SelectedPlace, SelectedStay, PlanItem, TripInfo

# 도착 후 짐 찾기·입국심사 등, 첫 활동을 시작하기 전 필요한 시간.
AIRPORT_ARRIVAL_BUFFER_MIN = 60
# 출국 수속을 위해 마지막 활동을 마치고 공항에 있어야 하는 시간.
AIRPORT_DEPARTURE_BUFFER_MIN = 120

FLIGHT_CATEGORY = "항공"
FLIGHT_OPENING_HOURS = "00:00-24:00"
FLIGHT_INTENSITY = "낮음"


@dataclass
class DayOverrides:
    """항공편이 있을 때만 채워지는 하루 경계 조정값. 분 단위."""

    day1_start: int | None = None
    last_day_end: int | None = None


def _anchor_point(
    stay: SelectedStay | None, places: list[SelectedPlace]
) -> tuple[float, float]:
    """항공편 항목에 쓸 근사 좌표. 실제 공항 좌표가 없어 가장 가까운 대안을 쓴다."""

    if stay is not None:
        return stay.lat, stay.lng
    if places:
        return (
            sum(place.lat for place in places) / len(places),
            sum(place.lng for place in places) / len(places),
        )
    # SelectedBundle.places는 minItems: 1이라 이 분기는 이론상 오지 않는다.
    return 0.0, 0.0


def compute_day_overrides(trip: TripInfo, flight: SelectedFlight | None) -> DayOverrides:
    """도착일 실질 시작 / 출발일 실질 종료를 계산한다.

    `max`/`min`으로 사용자의 `day_start_time`/`day_end_time`과 항상 함께
    본다 — 항공편이 아주 이르게 도착해도 사용자가 정한 시작 시각보다 앞당기지
    않는다(그건 `schedule.py`가 `max(cursor, day_start)`로 이미 보장한다).
    """

    if flight is None:
        return DayOverrides()

    overrides = DayOverrides()
    day_start = timecalc.to_minutes(trip.day_start_time)
    day_end = timecalc.to_minutes(trip.day_end_time)

    try:
        _, arrive_hhmm = timecalc.split_datetime(flight.outbound.arrive_at)
        arrive_minutes = timecalc.to_minutes(arrive_hhmm)
        overrides.day1_start = min(max(day_start, arrive_minutes + AIRPORT_ARRIVAL_BUFFER_MIN), day_end)
    except ValueError:
        overrides.day1_start = None

    if flight.inbound is not None:
        try:
            _, depart_hhmm = timecalc.split_datetime(flight.inbound.depart_at)
            depart_minutes = timecalc.to_minutes(depart_hhmm)
            overrides.last_day_end = max(min(day_end, depart_minutes - AIRPORT_DEPARTURE_BUFFER_MIN), day_start)
        except ValueError:
            overrides.last_day_end = None

    return overrides


def build_outbound_item(
    trip: TripInfo,
    flight: SelectedFlight,
    stay: SelectedStay | None,
    places: list[SelectedPlace],
) -> tuple[PlanItem | None, str | None]:
    """출국 항공편 항목을 만든다. Day 1의 첫 항목으로 쓴다."""

    leg = flight.outbound
    try:
        _, start_hhmm = timecalc.split_datetime(leg.depart_at)
    except ValueError as error:
        return None, f"출국 항공편 시각을 해석할 수 없어 일정에 넣지 못했습니다: {error}"

    start = timecalc.to_minutes(start_hhmm)
    end = start + leg.duration_min
    if end >= timecalc.MINUTES_PER_DAY:
        return None, (
            "출국 항공편이 자정을 넘겨(overnight) 하루 단위 계약으로 표현할 수 없어 "
            "일정에서 제외했습니다."
        )

    lat, lng = _anchor_point(stay, places)
    item = PlanItem(
        id="d1-1",  # build_schedule이 항목을 다시 번호 매긴다.
        name="출국 항공편",
        category=FLIGHT_CATEGORY,
        start_time=timecalc.to_hhmm(start),
        end_time=timecalc.to_hhmm(end),
        lat=lat,
        lng=lng,
        price=flight.total_price.amount,
        price_unit="per_stay",  # 총액이 이미 인원 전체 가격이므로 곱하지 않는다.
        opening_hours=FLIGHT_OPENING_HOURS,
        closed_days=[],
        expected_duration_min=leg.duration_min,
        physical_intensity=FLIGHT_INTENSITY,
        note="[DEMO DATA] 공항 좌표를 알 수 없어 숙소(또는 목적지) 좌표로 근사했습니다.",
        travel_from_prev=None,  # 하루의 첫 항목.
    )
    return item, None


def build_inbound_item(
    trip: TripInfo,
    flight: SelectedFlight,
    stay: SelectedStay | None,
    places: list[SelectedPlace],
) -> tuple[PlanItem | None, str | None]:
    """귀국 항공편 항목을 만든다. 마지막 날의 마지막 항목으로 쓴다."""

    leg = flight.inbound
    if leg is None:
        return None, None

    try:
        _, start_hhmm = timecalc.split_datetime(leg.depart_at)
    except ValueError as error:
        return None, f"귀국 항공편 시각을 해석할 수 없어 일정에 넣지 못했습니다: {error}"

    start = timecalc.to_minutes(start_hhmm)
    end = start + leg.duration_min
    if end >= timecalc.MINUTES_PER_DAY:
        return None, (
            "귀국 항공편이 자정을 넘겨(overnight) 하루 단위 계약으로 표현할 수 없어 "
            "일정에서 제외했습니다."
        )

    lat, lng = _anchor_point(stay, places)
    item = PlanItem(
        id="d1-1",
        name="귀국 항공편",
        category=FLIGHT_CATEGORY,
        start_time=timecalc.to_hhmm(start),
        end_time=timecalc.to_hhmm(end),
        lat=lat,
        lng=lng,
        # 항공권 총액은 출국편에 이미 반영했다. 여기서 또 넣으면 예산이 2배로 잡힌다.
        price=0.0,
        price_unit="per_stay",
        opening_hours=FLIGHT_OPENING_HOURS,
        closed_days=[],
        expected_duration_min=leg.duration_min,
        physical_intensity=FLIGHT_INTENSITY,
        note="[DEMO DATA] 항공권 총액은 출국 항공편 항목에 반영했습니다.",
        travel_from_prev=None,  # build_schedule이 실제 간격으로 채운다.
    )
    return item, None


__all__ = [
    "AIRPORT_ARRIVAL_BUFFER_MIN",
    "AIRPORT_DEPARTURE_BUFFER_MIN",
    "FLIGHT_CATEGORY",
    "FLIGHT_OPENING_HOURS",
    "FLIGHT_INTENSITY",
    "DayOverrides",
    "build_inbound_item",
    "build_outbound_item",
    "compute_day_overrides",
]
