"""Places와 가격·일정 보강 원문을 Plan Agent용 SelectedPlace 후보로 만드는 Tool."""

from __future__ import annotations

import re
from typing import Any

from ..contracts import Category, PlaceCandidate, SearchRequest, SelectedPlace
from .fact_check import verify_place

_WEEKDAYS = {"월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"}
_DAY_PATTERN = re.compile(r"(월요일|화요일|수요일|목요일|금요일|토요일|일요일)")
_HHMM_PATTERN = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")
_KOREAN_TIME_PATTERN = re.compile(r"(오전|오후)\s*([0-1]?\d|2[0-3]):([0-5]\d)")


def _format_hhmm(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def _korean_time_to_hhmm(match: re.Match[str]) -> str:
    period, hour_text, minute_text = match.groups()
    hour = int(hour_text)
    minute = int(minute_text)
    if period == "오후" and hour < 12:
        hour += 12
    if period == "오전" and hour == 12:
        hour = 0
    return _format_hhmm(hour, minute)


def _extract_hour_range(text: str) -> str | None:
    converted = _KOREAN_TIME_PATTERN.sub(_korean_time_to_hhmm, text)
    matches = _HHMM_PATTERN.findall(converted)
    if len(matches) < 2:
        return None
    start_hour, start_minute = map(int, matches[0])
    end_hour, end_minute = map(int, matches[1])
    return f"{_format_hhmm(start_hour, start_minute)}-{_format_hhmm(end_hour, end_minute)}"


def _name(raw: dict[str, Any]) -> str:
    display_name = raw.get("displayName")
    return str(display_name.get("text", "")) if isinstance(display_name, dict) else str(display_name or raw.get("name", ""))


def _category(raw: dict[str, Any]) -> Category:
    explicit = raw.get("primaryCategory")
    if explicit in {"관광지", "식사", "카페", "쇼핑", "휴식", "숙소"}:
        return explicit
    types = " ".join([str(raw.get("primaryType", "")), *map(str, raw.get("types", []))])
    if "cafe" in types:
        return "카페"
    if "restaurant" in types or "food" in types:
        return "식사"
    if "store" in types or "shopping" in types:
        return "쇼핑"
    if "park" in types or "spa" in types:
        return "휴식"
    if "lodging" in types or "hotel" in types:
        return "숙소"
    return "관광지"


def _opening_hours(raw: dict[str, Any]) -> str:
    if raw.get("openingHoursText"):
        normalized = _extract_hour_range(str(raw["openingHoursText"]))
        return normalized or str(raw["openingHoursText"])
    regular = raw.get("regularOpeningHours") or {}
    descriptions = regular.get("weekdayDescriptions") or []
    for description in map(str, descriptions):
        if "휴무" in description:
            continue
        normalized = _extract_hour_range(description)
        if normalized:
            return normalized
    return "정보 확인 필요"


def _closed_days(raw: dict[str, Any]) -> list[str]:
    explicit = [day for day in raw.get("closedDays", []) if day in _WEEKDAYS]
    if explicit:
        return explicit

    regular = raw.get("regularOpeningHours") or {}
    descriptions = regular.get("weekdayDescriptions") or []
    closed: list[str] = []
    for description in map(str, descriptions):
        if "휴무" not in description:
            continue
        match = _DAY_PATTERN.search(description)
        if match:
            closed.append(match.group(1))
    return closed


def _note(raw: dict[str, Any]) -> str:
    address = str(raw.get("formattedAddress", "")).strip()
    demo_note = str(raw.get("_demo_note", "")).strip()
    return " · ".join(part for part in (address, demo_note) if part)


def normalize_places(
    raw_items: list[dict[str, Any]],
    request: SearchRequest,
) -> tuple[list[PlaceCandidate], list[str]]:
    """계약 필수 가격·일정 정보를 가진 row만 정규화하고 탈락 원인을 보존한다."""

    candidates: list[PlaceCandidate] = []
    issues: list[str] = []
    for index, raw in enumerate(raw_items):
        record_id = str(raw.get("id", f"row-{index}"))
        try:
            location = raw.get("location") or {}
            place = SelectedPlace(
                id=str(raw["id"]),
                name=_name(raw),
                category=_category(raw),
                lat=float(location["latitude"]),
                lng=float(location["longitude"]),
                price=float(raw["estimatedPrice"]),
                price_unit=str(raw["priceUnit"]),
                opening_hours=_opening_hours(raw),
                closed_days=_closed_days(raw),
                expected_duration_min=int(raw["expectedDurationMin"]),
                physical_intensity=str(raw["physicalIntensity"]),
                note=_note(raw),
            )
            verification = verify_place(place, raw, request.trip_info.budget_currency)
            if verification.accepted:
                rating = float(raw["rating"]) if raw.get("rating") is not None else None
                candidates.append(PlaceCandidate(place=place, rating=rating, verification=verification))
            else:
                codes = ", ".join(issue.code for issue in verification.issues if issue.severity == "error")
                issues.append(f"{record_id}: 사실 검증 거부 ({codes or 'unknown'})")
        except (KeyError, TypeError, ValueError) as error:
            issues.append(f"{record_id}: 정규화 실패 ({error})")
    candidates.sort(key=lambda candidate: (-(candidate.rating or 0), candidate.place.price, candidate.place.name))
    return candidates[: request.max_results], issues
