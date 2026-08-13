"""배치 → 시각 확정 → 자기 검증을 엮는 결정론 파이프라인.

LLM 없이 여기까지만으로 계약을 만족하는 일정이 나와야 한다. Gemini는 나중에
`note`와 진행 문장을 다듬는 데만 쓴다. 그래야 키가 없어도 제품이 동작하고,
LLM이 실패해도 결과가 살아남는다.

## 재시도

시각 확정에서 넘친 장소(`overflow`)는 버리지 않고 **다른 날에 한 번 더** 시도한다.
그래도 안 되면 미배치로 보고한다. 무한 재시도는 하지 않는다 — 같은 제약이면
같은 결과가 나오므로 반복해도 달라지지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import contracts
from .allocate import AllocationResult, Unassigned, allocate
from .quota import BUDGET
from .models import (
    Plan,
    PlanToVerificationInput,
    SearchToPlanInput,
    SelectedPlace,
    Violation,
)
from .schedule import ScheduleResult, build_schedule

logger = logging.getLogger(__name__)

MAX_REALLOCATION_PASSES = 2


@dataclass
class PlanningDiagnostics:
    """경계를 넘지 않는 내부 진단.

    계약에는 담을 자리가 없다. 로그와 `done` 이벤트의 `summary`로만 나간다.
    """

    unassigned: list[Unassigned] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    estimated_leg_count: int = 0
    total_leg_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary_line(self, day_count: int, item_count: int) -> str:
        """`done.summary`용 한 문장. 계약상 200자 이내."""

        parts = [f"{day_count}일 일정에 {item_count}개 항목을 배치했어요."]
        if self.unassigned:
            names = ", ".join(item.place_name for item in self.unassigned[:2])
            more = f" 외 {len(self.unassigned) - 2}곳" if len(self.unassigned) > 2 else ""
            parts.append(f"{names}{more}은 넣지 못했어요.")
        if self.estimated_leg_count:
            parts.append(
                f"이동시간 {self.estimated_leg_count}건은 좌표로 추정했어요."
            )
        return " ".join(parts)[:200]


@dataclass
class PlanningResult:
    payload: PlanToVerificationInput | None
    diagnostics: PlanningDiagnostics


def build_plan(source: SearchToPlanInput) -> PlanningResult:
    """`SearchToPlanInput`으로 `PlanToVerificationInput`을 만든다.

    입력이 구조적으로 불가능하면 `payload`가 None이고 `violations`에 이유가 담긴다.
    """

    diagnostics = PlanningDiagnostics()

    input_violations = contracts.check_input_usable(source)
    fatal = [
        violation
        for violation in input_violations
        if violation.code
        in {
            "INVALID_DATE_RANGE",
            "INVALID_DAY_WINDOW",
            "STAY_REQUIRED_FOR_MULTIDAY",
            "MUST_VISIT_NOT_SELECTED",
        }
    ]
    if fatal:
        diagnostics.violations.extend(fatal)
        logger.error(
            "입력만으로는 계약을 지키는 일정을 만들 수 없습니다: %s",
            "; ".join(f"{v.code} {v.message}" for v in fatal),
        )
        return PlanningResult(payload=None, diagnostics=diagnostics)

    # 치명적이지 않은 입력 문제는 기록만 하고 진행한다.
    for violation in input_violations:
        if violation not in fatal:
            diagnostics.notes.append(f"[{violation.code}] {violation.message}")

    trip = source.trip_info
    stay = source.selected.stay
    places = list(source.selected.places)

    # 이번 요청의 Routes API 호출 예산을 초기화한다. 요청당 상한이 있어
    # 한 번의 일정 생성이 과금을 폭발시킬 수 없다.
    BUDGET.begin_request()

    allocation = allocate(places, trip, stay)
    schedule = build_schedule(allocation, places, trip, stay)

    # 넘친 장소를 다른 날에 다시 시도한다.
    for _ in range(MAX_REALLOCATION_PASSES - 1):
        if not schedule.overflow:
            break
        allocation, moved = _reallocate_overflow(allocation, schedule, places)
        if not moved:
            break
        schedule = build_schedule(allocation, places, trip, stay)

    by_id = {place.id: place for place in places}
    for overflow in schedule.overflow:
        place = by_id.get(overflow.place_id)
        diagnostics.unassigned.append(
            Unassigned(
                place_id=overflow.place_id,
                place_name=place.name if place else overflow.place_id,
                reason=f"Day {overflow.day_number}: {overflow.reason}",
            )
        )

    diagnostics.unassigned.extend(allocation.unassigned)
    diagnostics.notes.extend(allocation.notes)
    diagnostics.notes.extend(schedule.notes)
    diagnostics.estimated_leg_count = schedule.estimated_leg_count
    diagnostics.total_leg_count = schedule.total_leg_count

    # 하루에 최소 1개 항목이 필요하다(계약 minItems: 1).
    #
    # 빈 날이 생기는 원인은 두 가지다.
    #   1. 배치할 장소가 부족하다 (장소 수 < 여행 일수)
    #   2. 그 날에 넣을 수 있는 장소가 휴무·영업시간 때문에 없다
    #
    # 숙소가 있으면 숙소만으로도 날을 채울 수 있어서 마지막 날을 뺀 날은
    # 비지 않는다. 마지막 날이 비는 경우는 남는다.
    if schedule.empty_days:
        diagnostics.violations.append(
            Violation(
                code="EMPTY_DAY",
                message=(
                    f"Day {', '.join(map(str, schedule.empty_days))}에 배치할 항목이 "
                    "없습니다. 계약은 하루에 최소 1개 항목을 요구하므로 일정을 "
                    "만들 수 없습니다. 장소를 더 선택하거나 여행 기간을 줄여야 합니다."
                ),
            )
        )
        logger.error(
            "빈 날이 있어 일정을 만들지 못했습니다: Day %s (선택 장소 %d곳, 여행 %d일)",
            schedule.empty_days,
            len(places),
            len(allocation.days),
        )
        return PlanningResult(payload=None, diagnostics=diagnostics)

    payload = PlanToVerificationInput(
        schema_version="1.0",
        # trip_info는 한 글자도 바꾸지 않는다. 그대로 넘긴다.
        trip_info=trip,
        plan=Plan(days=schedule.days),
    )

    # 산출 직전 자기 검증. 검증 에이전트와 같은 판정을 미리 돌린다.
    diagnostics.violations.extend(contracts.verify_all(payload, source))
    if diagnostics.violations:
        logger.warning(
            "자기 검증에서 %d건이 걸렸습니다: %s",
            len(diagnostics.violations),
            "; ".join(f"{v.code}" for v in diagnostics.violations),
        )

    if diagnostics.estimated_leg_count:
        logger.info(
            "이동 구간 %d건 중 %d건을 좌표 기반으로 추정했습니다.",
            diagnostics.total_leg_count,
            diagnostics.estimated_leg_count,
        )
    logger.info(BUDGET.describe())

    return PlanningResult(payload=payload, diagnostics=diagnostics)


def _reallocate_overflow(
    allocation: AllocationResult,
    schedule: ScheduleResult,
    places: list[SelectedPlace],
) -> tuple[AllocationResult, bool]:
    """넘친 장소를 항목이 가장 적은 다른 날로 옮긴다."""

    by_id = {place.id: place for place in places}
    overflow_ids = {item.place_id for item in schedule.overflow}
    if not overflow_ids:
        return allocation, False

    moved = False
    for day in allocation.days:
        day.place_ids = [pid for pid in day.place_ids if pid not in overflow_ids]

    for place_id in sorted(overflow_ids):
        place = by_id.get(place_id)
        if place is None:
            continue
        candidates = [
            day
            for day in allocation.days
            if place_id not in day.place_ids
            and not _is_closed_for(place, day.date)
        ]
        if not candidates:
            continue
        target = min(candidates, key=lambda day: (len(day.place_ids), day.day_number))
        # 원래 있던 날과 같으면 옮긴 게 아니다.
        target.place_ids.append(place_id)
        moved = True

    return allocation, moved


def _is_closed_for(place: SelectedPlace, date_str: str) -> bool:
    from . import timecalc

    return timecalc.is_closed_on(date_str, list(place.closed_days))


__all__ = [
    "MAX_REALLOCATION_PASSES",
    "PlanningDiagnostics",
    "PlanningResult",
    "build_plan",
]
