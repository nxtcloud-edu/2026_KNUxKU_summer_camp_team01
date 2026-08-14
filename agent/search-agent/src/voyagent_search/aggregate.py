"""검증된 후보와 사용자 선택을 canonical SearchToPlanInput으로 투영한다."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

from .contracts import SearchRunResult, SearchSelection, SearchToPlanInput, SelectedResults
from .schema_registry import validate_search_to_plan

T = TypeVar("T")


def _find(items: Iterable[T], item_id: str, get_id: Callable[[T], str], label: str) -> T:
    for item in items:
        if get_id(item) == item_id:
            return item
    raise ValueError(f"선택한 {label} ID가 검증된 후보에 없습니다: {item_id}")


def _reject_estimated(candidate: object, label: str) -> None:
    """canonical schema가 추정 여부를 표현하지 못하므로 추정 필드 후보의 전달을 차단한다."""

    verification = getattr(candidate, "verification", None)
    estimated_fields = getattr(verification, "estimated_fields", [])
    if estimated_fields:
        fields = ", ".join(estimated_fields)
        raise ValueError(f"선택한 {label}에 미확인 추정 필드가 있어 Plan Agent로 전달할 수 없습니다: {fields}")


def build_search_to_plan(result: SearchRunResult, selection: SearchSelection) -> SearchToPlanInput:
    """근거가 확인된 선택만 JSON Schema가 허용하는 필드로 투영한다."""

    flight = None
    if selection.flight_id:
        flight_candidate = _find(
            result.flights.candidates,
            selection.flight_id,
            lambda candidate: candidate.offer.id,
            "항공편",
        )
        _reject_estimated(flight_candidate, "항공편")
        flight = flight_candidate.offer

    stay = None
    if selection.stay_id:
        stay_candidate = _find(
            result.stays.candidates,
            selection.stay_id,
            lambda candidate: candidate.stay.id,
            "숙소",
        )
        _reject_estimated(stay_candidate, "숙소")
        stay = stay_candidate.stay

    places = []
    for place_id in selection.place_ids:
        place_candidate = _find(
            result.places.candidates,
            place_id,
            lambda candidate: candidate.place.id,
            "장소",
        )
        _reject_estimated(place_candidate, "장소")
        places.append(place_candidate.place)

    handoff = SearchToPlanInput(
        trip_info=result.request.trip_info,
        selected=SelectedResults(flight=flight, stay=stay, places=places),
    )
    validate_search_to_plan(handoff)
    return handoff
