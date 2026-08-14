from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CheckStatus = Literal["pass", "warning", "fail", "skipped"]
FindingLevel = Literal["주의", "위험"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Persona(StrictModel):
    description: str
    must_visit: list[str]
    avoid: list[str]
    pace: Literal["여유", "보통", "빡빡"]
    max_walking_level: Literal["낮음", "중", "중간", "높음"]


class TripInfo(StrictModel):
    destination: str
    start_date: date
    end_date: date
    num_travelers: int = Field(ge=1)
    budget_total: float = Field(ge=0)
    budget_currency: str = Field(pattern=r"^[A-Z]{3}$")
    budget_includes: list[Literal["관광지", "식사", "카페", "쇼핑", "휴식", "숙소"]]
    transport_mode: str
    day_start_time: time
    day_end_time: time
    persona: Persona


class TravelFromPrevious(StrictModel):
    mode: str
    estimated_min: int = Field(ge=0)
    distance_km: float = Field(ge=0)


class PlanItem(StrictModel):
    id: str = Field(pattern=r"^d[1-9]\d*-[1-9]\d*$")
    name: str
    category: Literal["관광지", "식사", "카페", "쇼핑", "휴식", "숙소"]
    start_time: time
    end_time: time
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    price: float = Field(ge=0)
    price_unit: Literal["per_person", "per_stay"]
    opening_hours: str
    closed_days: list[str]
    expected_duration_min: int = Field(ge=0)
    physical_intensity: Literal["낮음", "중", "중간", "높음"]
    note: str
    travel_from_prev: TravelFromPrevious | None


class PlanDay(StrictModel):
    day: int = Field(ge=1)
    date: date
    items: list[PlanItem] = Field(min_length=1)


class Plan(StrictModel):
    days: list[PlanDay] = Field(min_length=1)


class PlanToVerificationInput(StrictModel):
    schema_version: Literal["1.0"]
    trip_info: TripInfo
    plan: Plan


class CheckIssue(StrictModel):
    code: str
    message: str
    day: int | None = None
    item_id: str | None = None


class StandardCheck(StrictModel):
    status: CheckStatus
    issues: list[CheckIssue] = Field(default_factory=list)


class DurationRealismIssue(StrictModel):
    code: Literal["DURATION_TOO_SHORT", "DURATION_TOO_LONG"]
    severity: Literal["warning", "fail"]
    message: str
    day: int = Field(ge=1)
    item_id: str
    allocated_min: int = Field(ge=0)
    suggested_min: int = Field(ge=0)
    suggested_max: int = Field(ge=0)


class DurationRealismCheck(StrictModel):
    status: CheckStatus
    reviewed_item_ids: list[str] = Field(default_factory=list)
    issues: list[DurationRealismIssue] = Field(default_factory=list)


class BudgetCheck(StrictModel):
    status: CheckStatus
    budget_total: float
    estimated_total: float
    over_by: float
    currency: str


class MustVisitCheck(StrictModel):
    status: CheckStatus
    missing: list[str] = Field(default_factory=list)


class AvoidMatch(StrictModel):
    avoid: str
    message: str
    day: int | None = None
    item_id: str | None = None


class AvoidCheck(StrictModel):
    status: CheckStatus
    matched: list[AvoidMatch] = Field(default_factory=list)


class VerificationChecks(StrictModel):
    physical_feasibility: StandardCheck
    budget: BudgetCheck
    operating_hours: StandardCheck
    daily_schedule: StandardCheck
    must_visit: MustVisitCheck
    avoid: AvoidCheck
    pace: StandardCheck
    walking_level: StandardCheck
    duration_realism: DurationRealismCheck


class VerificationFinding(StrictModel):
    level: FindingLevel
    check: str
    code: str
    message: str
    attention: str | None = None
    day: int | None = None
    item_id: str | None = None


class VerificationFeedback(StrictModel):
    cautions: list[VerificationFinding] = Field(default_factory=list)
    dangers: list[VerificationFinding] = Field(default_factory=list)


class VerificationResult(StrictModel):
    possible: bool
    checks: VerificationChecks
    feedback: VerificationFeedback = Field(default_factory=VerificationFeedback)


class AiHumanJudgement(StrictModel):
    """Structured Gemini response for subjective persona-related checks."""

    avoid: AvoidCheck
    pace: StandardCheck
    walking_level: StandardCheck
    duration_realism: DurationRealismCheck
