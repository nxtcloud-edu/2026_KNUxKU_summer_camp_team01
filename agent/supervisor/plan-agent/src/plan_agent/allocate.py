"""일자 배치 — 어느 장소를 며칠에 둘지 결정한다. 전부 결정론적이다.

## 왜 LLM을 쓰지 않는가

이 단계의 판단 근거는 전부 숫자다. 휴무일은 날짜에서 계산되고, 근접성은
좌표에서 나오고, 하루 용량은 시각 산술이다. `behavior.md`가 지적한 것처럼
계산을 LLM에 맡기면 신뢰가 무너진다. LLM은 나중에 **배치 이유 문장**만 쓴다.

## 알고리즘

1. 각 장소의 방문 가능 날짜를 계산한다 (휴무일 제외)
2. 제약이 강한 것부터 배치한다 — 필수 방문지, 그다음 갈 수 있는 날이 적은 것
3. 후보 날 중에서 (a) 아직 여유 있는 날 (b) 이미 배치된 것과 가까운 날을 고른다
4. 하루 안의 순서는 숙소에서 출발하는 최근접 경로로 정한다

정렬 기준에 항상 `place.id`를 마지막 tiebreak으로 넣는다. 같은 입력이면 같은
결과가 나와야 디버깅과 데모가 가능하다.

## 배치하지 못한 장소

계약(`PlanToVerificationInput`)에는 미배치 장소를 담을 필드가 없다. 그래서
배치에 실패한 장소는 **조용히 사라지는 것이 아니라** `AllocationResult.unassigned`에
이유와 함께 담기고, 로그와 `done` 이벤트의 `summary`로 보고된다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import geo, timecalc
from .models import SelectedPlace, SelectedStay, TripInfo

logger = logging.getLogger(__name__)

# 페이스별 하루 목표 장소 수 (최소, 최대).
# `spec.md`의 PACE_CONFIG를 한국어 enum에 대응시킨 값이다.
PACE_TARGET: dict[str, tuple[int, int]] = {
    "여유": (2, 3),
    "보통": (3, 4),
    "빡빡": (5, 7),
}
DEFAULT_PACE_TARGET = (3, 4)

# 걷기·활동 강도 순위.
#
# 계약 enum은 `["낮음", "중", "중간", "높음"]`인데 '중'과 '중간'은 같은 뜻이다.
# 같은 순위로 취급한다. 이건 계약의 모호함이라 담당자와 정리할 항목이다
# (둘 중 하나로 통일하는 게 맞다).
INTENSITY_RANK: dict[str, int] = {"낮음": 0, "중": 1, "중간": 1, "높음": 2}


@dataclass
class DayAllocation:
    """하루에 배치된 장소들. 시각은 아직 정하지 않았다."""

    day_number: int  # 1부터
    date: str
    place_ids: list[str] = field(default_factory=list)


@dataclass
class Unassigned:
    place_id: str
    place_name: str
    reason: str


@dataclass
class AllocationResult:
    days: list[DayAllocation]
    unassigned: list[Unassigned] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def assigned_count(self) -> int:
        return sum(len(day.place_ids) for day in self.days)


def pace_target(pace: str) -> tuple[int, int]:
    return PACE_TARGET.get(pace, DEFAULT_PACE_TARGET)


def intensity_rank(level: str) -> int:
    return INTENSITY_RANK.get(level, 1)


def trip_dates(trip: TripInfo) -> list[str]:
    total = timecalc.day_count(trip.start_date, trip.end_date)
    return [timecalc.add_days(trip.start_date, offset) for offset in range(total)]


def _feasible_dates(place: SelectedPlace, dates: list[str]) -> list[str]:
    """휴무일을 뺀 방문 가능 날짜."""

    return [
        date_str
        for date_str in dates
        if not timecalc.is_closed_on(date_str, list(place.closed_days))
    ]


def _day_capacity_minutes(trip: TripInfo) -> int:
    return timecalc.to_minutes(trip.day_end_time) - timecalc.to_minutes(
        trip.day_start_time
    )


def allocate(
    places: list[SelectedPlace],
    trip: TripInfo,
    stay: SelectedStay | None,
) -> AllocationResult:
    """장소를 일자에 배치한다.

    필수 방문지를 먼저, 그다음 제약이 강한 순서로 배치한다. 배치하지 못한
    장소는 이유와 함께 `unassigned`에 담는다.
    """

    dates = trip_dates(trip)
    days = [
        DayAllocation(day_number=index + 1, date=date_str)
        for index, date_str in enumerate(dates)
    ]
    result = AllocationResult(days=days)

    if not places:
        result.notes.append("선택된 장소가 없습니다.")
        return result

    by_id = {place.id: place for place in places}
    must_visit_names = {name.strip().casefold() for name in trip.persona.must_visit}

    def is_must_visit(place: SelectedPlace) -> bool:
        return place.name.strip().casefold() in must_visit_names

    # 방문 가능 날짜를 미리 계산한다.
    feasible: dict[str, list[str]] = {
        place.id: _feasible_dates(place, dates) for place in places
    }

    # 어디에도 배치할 수 없는 장소를 먼저 걸러낸다.
    placeable: list[SelectedPlace] = []
    for place in places:
        if feasible[place.id]:
            placeable.append(place)
            continue
        result.unassigned.append(
            Unassigned(
                place_id=place.id,
                place_name=place.name,
                reason=(
                    f"여행 기간 전체가 휴무일입니다 (휴무: {', '.join(place.closed_days)})"
                ),
            )
        )

    # 배치 순서: 필수 방문지 먼저 → 갈 수 있는 날이 적은 것 → id (결정론)
    ordered = sorted(
        placeable,
        key=lambda place: (
            0 if is_must_visit(place) else 1,
            len(feasible[place.id]),
            place.id,
        ),
    )

    _, pace_max = pace_target(trip.persona.pace)
    capacity = _day_capacity_minutes(trip)

    # 하루에 몇 곳까지 둘지.
    #
    # 균등 분배를 우선한다. 페이스 상한(예: 4곳)만 기준으로 삼으면 한 날에
    # 4곳이 찰 때까지 계속 넣어서 2/1/4/1처럼 심하게 치우친다. 사용자가
    # "보통 페이스"라고 했는데 어떤 날은 4곳, 어떤 날은 1곳이면 요청을
    # 지킨 것이 아니다.
    #
    # 그래서 상한을 `ceil(장소 수 / 일수)`로 잡고, 페이스 상한을 넘지 않는
    # 선에서만 쓴다. 장소가 너무 많으면 버리는 대신 상한을 넘긴다 —
    # 페이스 초과는 검증에서 warning이지만 장소를 버리는 것은 사용자가
    # 고른 것을 잃는 일이다.
    day_count = len(days)
    needed_per_day = -(-len(ordered) // day_count) if day_count else 0
    per_day_cap = max(1, min(pace_max, needed_per_day)) if day_count else pace_max
    if needed_per_day > pace_max:
        per_day_cap = needed_per_day
        result.notes.append(
            f"장소 {len(ordered)}곳을 {day_count}일에 담으려면 하루 {needed_per_day}곳이 "
            f"필요해 페이스 상한({pace_max}곳)을 넘습니다. 장소를 버리지 않는 쪽을 택했습니다."
        )

    # 누적 소요시간(체류시간만). 이동시간은 schedule 단계에서 정확히 계산한다.
    used_minutes = [0] * day_count

    for place in ordered:
        candidates = feasible[place.id]
        best_index = _choose_day(
            place=place,
            candidate_dates=candidates,
            days=days,
            by_id=by_id,
            used_minutes=used_minutes,
            per_day_cap=per_day_cap,
            capacity=capacity,
        )
        if best_index is None:
            result.unassigned.append(
                Unassigned(
                    place_id=place.id,
                    place_name=place.name,
                    reason="방문 가능한 날의 하루 시간이 모두 부족합니다",
                )
            )
            continue
        days[best_index].place_ids.append(place.id)
        used_minutes[best_index] += place.expected_duration_min

    # 하루 안의 순서를 최근접 경로로 정한다.
    seed = (stay.lat, stay.lng) if stay is not None else None
    for day in days:
        day.place_ids = _order_within_day(day.place_ids, by_id, seed)

    _add_intensity_notes(result, days, by_id, trip)
    return result


def _choose_day(
    *,
    place: SelectedPlace,
    candidate_dates: list[str],
    days: list[DayAllocation],
    by_id: dict[str, SelectedPlace],
    used_minutes: list[int],
    per_day_cap: int,
    capacity: int,
) -> int | None:
    """장소를 둘 가장 좋은 날의 인덱스. 없으면 None."""

    date_to_index = {day.date: index for index, day in enumerate(days)}
    scored: list[tuple[tuple, int]] = []

    for date_str in candidate_dates:
        index = date_to_index[date_str]
        day = days[index]

        # 체류시간 합이 하루 창을 넘으면 그 날은 후보에서 뺀다.
        # 이동시간은 아직 모르므로 여유를 남긴다(schedule이 최종 판정).
        if used_minutes[index] + place.expected_duration_min > capacity:
            continue

        already_full = len(day.place_ids) >= per_day_cap
        affinity = _affinity_minutes(place, day.place_ids, by_id)

        # 우선순위를 이 순서로 둔다.
        #   1. 상한을 넘지 않은 날 (균등 분배의 기본)
        #   2. 항목이 적은 날      (같은 조건이면 비어 있는 날부터)
        #   3. 지리적으로 가까운 날 (이동을 줄인다)
        #   4. 앞선 날            (결정론적 tiebreak)
        #
        # 근접성을 항목 수보다 먼저 보면 한 지역 장소가 모두 같은 날에 몰려
        # 다른 날이 비게 된다. 이동을 조금 더 하더라도 하루 밀도를 사용자가
        # 요청한 페이스에 맞추는 것이 낫다.
        scored.append(
            (
                (1 if already_full else 0, len(day.place_ids), affinity, index),
                index,
            )
        )

    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0])
    return scored[0][1]


def _affinity_minutes(
    place: SelectedPlace, assigned_ids: list[str], by_id: dict[str, SelectedPlace]
) -> int:
    """이미 그 날에 배치된 장소들과의 근접도. 작을수록 가깝다.

    좌표 기반 추정을 쓴다. 이 단계에서 Routes API를 부르면 호출 수가 폭발한다
    (장소 수 × 날 수). 정확한 이동시간은 schedule 단계에서 확정 구간에만 구한다.
    """

    if not assigned_ids:
        return 0
    distances = [
        geo.haversine_km(
            place.lat, place.lng, by_id[other].lat, by_id[other].lng
        )
        for other in assigned_ids
        if other in by_id
    ]
    if not distances:
        return 0
    return int(round(min(distances) * 10))  # 0.1km 단위 정수화 (결정론 정렬용)


def _order_within_day(
    place_ids: list[str],
    by_id: dict[str, SelectedPlace],
    seed: tuple[float, float] | None,
) -> list[str]:
    """하루 안의 방문 순서를 최근접 이웃으로 정한다.

    숙소 좌표가 있으면 거기서 출발한다. 실제로 아침에 숙소에서 나오기 때문이고,
    하루의 마지막에 숙소로 돌아가는 이동도 짧아진다.
    """

    remaining = [pid for pid in place_ids if pid in by_id]
    if len(remaining) <= 1:
        return remaining

    if seed is None:
        # 숙소가 없으면 가장 서쪽·북쪽 장소에서 시작한다(결정론적 선택).
        start_id = min(remaining, key=lambda pid: (by_id[pid].lng, by_id[pid].lat, pid))
        ordered = [start_id]
        remaining.remove(start_id)
        current = (by_id[start_id].lat, by_id[start_id].lng)
    else:
        ordered = []
        current = seed

    while remaining:
        next_id = min(
            remaining,
            key=lambda pid: (
                geo.haversine_km(current[0], current[1], by_id[pid].lat, by_id[pid].lng),
                pid,
            ),
        )
        ordered.append(next_id)
        remaining.remove(next_id)
        current = (by_id[next_id].lat, by_id[next_id].lng)

    return ordered


def _add_intensity_notes(
    result: AllocationResult,
    days: list[DayAllocation],
    by_id: dict[str, SelectedPlace],
    trip: TripInfo,
) -> None:
    """`max_walking_level`을 넘는 장소를 보고한다. 버리지는 않는다.

    사용자가 직접 고른 장소를 Plan Agent가 빼면 그게 더 나쁜 실패다. 대신
    사실을 기록해 두고, 검증 에이전트의 `walking_level` 판단에 맡긴다.
    """

    limit = intensity_rank(trip.persona.max_walking_level)
    exceeded = [
        by_id[pid].name
        for day in days
        for pid in day.place_ids
        if pid in by_id and intensity_rank(by_id[pid].physical_intensity) > limit
    ]
    if exceeded:
        result.notes.append(
            f"활동 강도가 요청 수준({trip.persona.max_walking_level})을 넘는 장소가 "
            f"{len(exceeded)}곳 있습니다: {', '.join(exceeded[:3])}"
            + ("…" if len(exceeded) > 3 else "")
        )


__all__ = [
    "AllocationResult",
    "DEFAULT_PACE_TARGET",
    "DayAllocation",
    "INTENSITY_RANK",
    "PACE_TARGET",
    "Unassigned",
    "allocate",
    "intensity_rank",
    "pace_target",
    "trip_dates",
]
