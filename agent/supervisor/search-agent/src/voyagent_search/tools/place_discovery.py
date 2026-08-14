"""Places와 가격·일정 보강 원문을 Plan Agent용 SelectedPlace 후보로 만드는 Tool."""

from __future__ import annotations

from typing import Any

from ..contracts import Category, PlaceCandidate, SearchRequest, SelectedPlace
from .fact_check import verify_place

_WEEKDAYS = {"월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"}


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
        return str(raw["openingHoursText"])
    regular = raw.get("regularOpeningHours") or {}
    descriptions = regular.get("weekdayDescriptions") or []
    return "; ".join(map(str, descriptions)) or "정보 확인 필요"


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
            closed_days = [day for day in raw["closedDays"] if day in _WEEKDAYS]
            place = SelectedPlace(
                id=str(raw["id"]),
                name=_name(raw),
                category=_category(raw),
                lat=float(location["latitude"]),
                lng=float(location["longitude"]),
                price=float(raw["estimatedPrice"]),
                price_unit=str(raw["priceUnit"]),
                opening_hours=_opening_hours(raw),
                closed_days=closed_days,
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
