"""Search Agent의 canonical handoff 및 내부 실행 계약."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
CURRENCY_PATTERN = r"^[A-Z]{3}$"
IATA_PATTERN = r"^[A-Z]{3}$"

Category = Literal["관광지", "식사", "카페", "쇼핑", "휴식", "숙소"]
WalkingLevel = Literal["낮음", "중", "중간", "높음"]
TaskStatus = Literal["success", "skipped", "error"]
IssueSeverity = Literal["warning", "error"]


def _require_unique(values: list[object], label: str) -> list[object]:
    """canonical schema의 uniqueItems 제약을 provider 호출 전에 적용한다."""

    if len({str(value) for value in values}) != len(values):
        raise ValueError(f"{label}에는 중복을 넣을 수 없습니다")
    return values


class StrictModel(BaseModel):
    """알 수 없는 필드를 거부해 JSON Schema의 additionalProperties=false를 따른다."""

    model_config = ConfigDict(extra="forbid")


class Persona(StrictModel):
    description: str = Field(min_length=1)
    must_visit: list[str]
    avoid: list[str]
    pace: Literal["여유", "보통", "빡빡"]
    max_walking_level: WalkingLevel

    @field_validator("must_visit", "avoid")
    @classmethod
    def validate_unique_non_empty_items(cls, values: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "persona")
        if any(not value for value in values):
            raise ValueError(f"{field_name} 항목은 빈 문자열일 수 없습니다")
        return _require_unique(values, field_name)  # type: ignore[return-value]


class TripInfo(StrictModel):
    destination: str = Field(min_length=1)
    start_date: str = Field(pattern=DATE_PATTERN)
    end_date: str = Field(pattern=DATE_PATTERN)
    num_travelers: int = Field(ge=1)
    budget_total: float = Field(ge=0)
    budget_currency: str = Field(pattern=CURRENCY_PATTERN)
    budget_includes: list[Category]
    transport_mode: str = Field(min_length=1)
    day_start_time: str = Field(pattern=TIME_PATTERN)
    day_end_time: str = Field(pattern=TIME_PATTERN)
    persona: Persona

    @field_validator("budget_includes")
    @classmethod
    def validate_unique_budget_categories(cls, values: list[Category]) -> list[Category]:
        return _require_unique(values, "budget_includes")  # type: ignore[return-value]


class Money(StrictModel):
    amount: float = Field(ge=0)
    currency: str = Field(pattern=CURRENCY_PATTERN)


class TravelLeg(StrictModel):
    depart_at: str = Field(min_length=16)
    arrive_at: str = Field(min_length=16)
    duration_min: int = Field(ge=0)


class SelectedFlight(StrictModel):
    id: str = Field(min_length=1)
    outbound: TravelLeg
    inbound: TravelLeg | None
    total_price: Money


class SelectedStay(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    price: float = Field(ge=0)
    price_unit: Literal["per_stay"] = "per_stay"
    check_in_time: str = Field(pattern=TIME_PATTERN)
    check_out_time: str = Field(pattern=TIME_PATTERN)
    note: str


class SelectedPlace(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1)
    category: Category
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    price: float = Field(ge=0)
    price_unit: Literal["per_person", "per_stay"]
    opening_hours: str = Field(min_length=1)
    closed_days: list[Literal["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]]
    expected_duration_min: int = Field(ge=0)
    physical_intensity: WalkingLevel
    note: str

    @field_validator("closed_days")
    @classmethod
    def validate_unique_closed_days(cls, values: list[str]) -> list[str]:
        return _require_unique(values, "closed_days")  # type: ignore[return-value]


class SelectedResults(StrictModel):
    flight: SelectedFlight | None
    stay: SelectedStay | None
    places: list[SelectedPlace] = Field(min_length=1)


class SearchToPlanInput(StrictModel):
    """agent/schemas/search-to-plan.schema.json과 동일한 최종 wire 객체."""

    schema_version: Literal["1.0"] = "1.0"
    trip_info: TripInfo
    selected: SelectedResults


class SourceEvidence(StrictModel):
    provider: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: HttpUrl | None = None
    retrieved_at: datetime
    fields: list[str] = Field(default_factory=list)


class VerificationIssue(StrictModel):
    severity: IssueSeverity
    code: str = Field(min_length=1)
    field: str | None = None
    message: str = Field(min_length=1)


class FactVerification(StrictModel):
    """공급자 근거, 추정 필드와 내부 모순 검사 결과. 최종 handoff에는 포함하지 않는다."""

    accepted: bool
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    issues: list[VerificationIssue] = Field(default_factory=list)
    evidence: list[SourceEvidence] = Field(default_factory=list)
    estimated_fields: list[str] = Field(default_factory=list)


class FlightCandidate(StrictModel):
    offer: SelectedFlight
    carrier_codes: list[str] = Field(default_factory=list)
    verification: FactVerification


class StayCandidate(StrictModel):
    stay: SelectedStay
    rating: float | None = Field(default=None, ge=0, le=5)
    verification: FactVerification


class PlaceCandidate(StrictModel):
    place: SelectedPlace
    rating: float | None = Field(default=None, ge=0, le=5)
    verification: FactVerification


class WebSource(StrictModel):
    title: str = Field(min_length=1)
    url: HttpUrl
    publisher: str = Field(min_length=1)
    retrieved_at: datetime


class CityWeather(StrictModel):
    summary: str = Field(min_length=1)
    packing_tips: list[str]


class CityTransport(StrictModel):
    summary: str = Field(min_length=1)
    tips: list[str]


class CitySafety(StrictModel):
    summary: str = Field(min_length=1)
    emergency_numbers: list[str]
    tips: list[str]


class CityInfo(StrictModel):
    """내부 cityInfo 결과. 최신 Search→Plan handoff에는 직렬화하지 않는다."""

    city_id: str = Field(min_length=1)
    city_name: str = Field(min_length=1)
    country_name: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    currency: str = Field(pattern=CURRENCY_PATTERN)
    languages: list[str] = Field(min_length=1)
    overview: str = Field(min_length=1)
    weather: CityWeather
    transport: CityTransport
    safety: CitySafety
    etiquette_tips: list[str]
    practical_tips: list[str]
    sources: list[WebSource] = Field(min_length=1)
    fetched_at: datetime


class FlightSearchResult(StrictModel):
    status: TaskStatus
    candidates: list[FlightCandidate] = Field(default_factory=list, max_length=20)
    issues: list[str] = Field(default_factory=list)
    error: str | None = None


class StaySearchResult(StrictModel):
    status: TaskStatus
    candidates: list[StayCandidate] = Field(default_factory=list, max_length=20)
    issues: list[str] = Field(default_factory=list)
    error: str | None = None


class PlaceSearchResult(StrictModel):
    status: TaskStatus
    candidates: list[PlaceCandidate] = Field(default_factory=list, max_length=20)
    issues: list[str] = Field(default_factory=list)
    error: str | None = None


class CityInfoResult(StrictModel):
    status: TaskStatus
    city_info: CityInfo | None = None
    verification: FactVerification | None = None
    error: str | None = None


class SearchRequest(StrictModel):
    """4개 subagent가 공유하는 내부 요청. canonical trip_info를 그대로 포함한다."""

    trip_info: TripInfo
    origin_iata: str | None = Field(default=None, pattern=IATA_PATTERN)
    destination_iata: str | None = Field(default=None, pattern=IATA_PATTERN)
    include_flights: bool = True
    flight_trip_type: Literal["round_trip", "one_way"] = "round_trip"
    include_stays: bool = True
    max_results: int = Field(default=20, ge=1, le=20)
    place_query: str | None = None

    @model_validator(mode="after")
    def require_airports_for_flight_search(self) -> "SearchRequest":
        if self.include_flights and (not self.origin_iata or not self.destination_iata):
            raise ValueError("항공 검색에는 origin_iata와 destination_iata가 필요합니다")
        return self


class SearchSelection(StrictModel):
    """UI에서 선택한 후보 ID. 선택 후에만 Plan handoff를 만들 수 있다."""

    flight_id: str | None = None
    stay_id: str | None = None
    place_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_places(self) -> "SearchSelection":
        if len(set(self.place_ids)) != len(self.place_ids):
            raise ValueError("place_ids에는 중복을 넣을 수 없습니다")
        return self


class SearchRunResult(StrictModel):
    """병렬 검색을 취합한 내부 결과. 검증 근거와 cityInfo를 보존한다."""

    request: SearchRequest
    flights: FlightSearchResult
    stays: StaySearchResult
    places: PlaceSearchResult
    city: CityInfoResult
