"""두 handoff 계약의 Pydantic 미러.

정본은 `agent/schemas/search-to-plan.schema.json`과
`agent/schemas/plan-to-verification.schema.json`이다. 이 모듈은 그 두 스키마를
그대로 옮긴 것이며, 임의로 필드를 늘리거나 제약을 완화하지 않는다.

`TripInfo`와 `Persona`는 두 스키마에서 **완전히 동일해야** 한다
(`agent/tools/conformance.mjs`가 `$defs.TripInfo`/`$defs.Persona`의
deepEqual을 검사한다). 그래서 이 파일에서도 정의를 한 벌만 두고 양쪽이
같은 클래스를 참조한다.

## 왜 date/time 대신 str + pattern인가

`verification-agent/models.py`는 `datetime.date`/`datetime.time`을 쓴다. 그쪽은
입력만 파싱하고 시각을 다시 내보내지 않으므로 문제가 없다.

Plan Agent는 반대로 **시각을 출력한다.** Pydantic v2가 `time`을 JSON으로
직렬화하면 `"09:00:00"`이 되는데, 계약의 Time 패턴은
`^([01]\\d|2[0-3]):[0-5]\\d$`이므로 초가 붙으면 스키마 위반이다. 또 conformance는
Search→Plan과 Plan→Verification의 `trip_info`가 deepEqual인지 검사하므로
입력받은 문자열이 한 글자도 바뀌면 안 된다.

따라서 경계를 넘는 값은 `str` + 정규식으로 두고, 산술이 필요한 곳에서만
`timecalc`로 변환한다. 이러면 검증도 되고 원본 그대로 통과된다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── 공통 스칼라 ───────────────────────────────────────────────
# 패턴은 두 스키마의 $defs와 문자 단위로 동일하다.

DateStr = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
TimeStr = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
CurrencyStr = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]

Category = Literal["관광지", "식사", "카페", "쇼핑", "휴식", "숙소"]
BudgetCategory = Literal["관광지", "식사", "카페", "쇼핑", "휴식", "숙소"]
WalkingLevel = Literal["낮음", "중", "중간", "높음"]
Pace = Literal["여유", "보통", "빡빡"]
WeekdayKo = Literal["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
PriceUnit = Literal["per_person", "per_stay"]

# 카테고리 중 예산 합산에서 인원수를 곱하지 않는 것.
# check_budget은 price_unit으로만 판단하므로 여기서는 참고용이다.
STAY_CATEGORY: Category = "숙소"


class StrictModel(BaseModel):
    """계약에 없는 필드를 조용히 통과시키지 않는다.

    두 스키마 모두 `additionalProperties: false`이므로 모델도 `extra="forbid"`다.
    """

    model_config = ConfigDict(extra="forbid")


# ── 공유 정의: Persona / TripInfo ──────────────────────────────
# 두 handoff에서 동일해야 하는 부분. 한 벌만 정의한다.


class Persona(StrictModel):
    description: str = Field(min_length=1)
    must_visit: list[str]
    avoid: list[str]
    pace: Pace
    max_walking_level: WalkingLevel


class TripInfo(StrictModel):
    destination: str = Field(min_length=1)
    start_date: DateStr
    end_date: DateStr
    num_travelers: int = Field(ge=1)
    budget_total: float = Field(ge=0)
    budget_currency: CurrencyStr
    budget_includes: list[BudgetCategory]
    transport_mode: str = Field(min_length=1)
    day_start_time: TimeStr
    day_end_time: TimeStr
    persona: Persona


class Money(StrictModel):
    amount: float = Field(ge=0)
    currency: CurrencyStr


# ── Search → Plan ────────────────────────────────────────────


class FlightTravelLeg(StrictModel):
    """항공 구간. 계약에서는 `TravelLeg`이지만 일정 항목 사이의 이동
    (`TravelFromPrevious`)과 이름이 겹치므로 여기서만 접두를 붙인다."""

    depart_at: str = Field(min_length=16)
    arrive_at: str = Field(min_length=16)
    duration_min: int = Field(ge=0)


class SelectedFlight(StrictModel):
    id: str = Field(min_length=1)
    outbound: FlightTravelLeg
    inbound: FlightTravelLeg | None
    total_price: Money


class SelectedStay(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    price: float = Field(ge=0)
    price_unit: Literal["per_stay"]
    check_in_time: TimeStr
    check_out_time: TimeStr
    note: str


class SelectedPlace(StrictModel):
    id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
    name: str = Field(min_length=1)
    category: Category
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    price: float = Field(ge=0)
    price_unit: PriceUnit
    opening_hours: str = Field(min_length=1)
    closed_days: list[WeekdayKo]
    expected_duration_min: int = Field(ge=0)
    physical_intensity: WalkingLevel
    note: str


class SelectedBundle(StrictModel):
    flight: SelectedFlight | None
    stay: SelectedStay | None
    places: list[SelectedPlace] = Field(min_length=1)


class SearchToPlanInput(StrictModel):
    schema_version: Literal["1.0"]
    trip_info: TripInfo
    selected: SelectedBundle


# ── Plan → Verification ──────────────────────────────────────


class TravelFromPrevious(StrictModel):
    mode: str = Field(min_length=1)
    estimated_min: int = Field(ge=0)
    distance_km: float = Field(ge=0)


class PlanItem(StrictModel):
    id: Annotated[str, Field(pattern=r"^d[1-9]\d*-[1-9]\d*$")]
    name: str = Field(min_length=1)
    category: Category
    start_time: TimeStr
    end_time: TimeStr
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    price: float = Field(ge=0)
    price_unit: PriceUnit
    opening_hours: str = Field(min_length=1)
    closed_days: list[WeekdayKo]
    expected_duration_min: int = Field(ge=0)
    physical_intensity: WalkingLevel
    note: str
    travel_from_prev: TravelFromPrevious | None


class PlanDay(StrictModel):
    day: int = Field(ge=1)
    date: DateStr
    items: list[PlanItem] = Field(min_length=1)


class Plan(StrictModel):
    days: list[PlanDay] = Field(min_length=1)


class PlanToVerificationInput(StrictModel):
    schema_version: Literal["1.0"]
    trip_info: TripInfo
    plan: Plan


# ── 내부 진단 타입 (경계를 넘지 않는다) ────────────────────────


class Violation(StrictModel):
    """자기 검증에서 발견한 위반.

    조용히 버리는 대신 이 객체를 반환한다. `code`는 가능하면
    `verification-agent/rules.py`의 issue code와 같은 값을 쓴다. 그래야
    사후에 어느 규칙에 걸릴지 바로 대조된다.
    """

    code: str
    message: str
    day: int | None = None
    item_id: str | None = None


__all__ = [
    "BudgetCategory",
    "Category",
    "CurrencyStr",
    "DateStr",
    "FlightTravelLeg",
    "Money",
    "Pace",
    "Persona",
    "Plan",
    "PlanDay",
    "PlanItem",
    "PlanToVerificationInput",
    "PriceUnit",
    "STAY_CATEGORY",
    "SearchToPlanInput",
    "SelectedBundle",
    "SelectedFlight",
    "SelectedPlace",
    "SelectedStay",
    "StrictModel",
    "TimeStr",
    "TravelFromPrevious",
    "TripInfo",
    "Violation",
    "WalkingLevel",
    "WeekdayKo",
]
