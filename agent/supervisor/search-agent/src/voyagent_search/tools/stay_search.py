"""Google Places 또는 가격·일정 보강 공급자 원문을 SelectedStay 후보로 만드는 Tool."""

from __future__ import annotations

from typing import Any

from ..contracts import SearchRequest, SelectedStay, StayCandidate
from .fact_check import verify_stay


def _name(raw: dict[str, Any]) -> str:
    display_name = raw.get("displayName")
    return str(display_name.get("text", "")) if isinstance(display_name, dict) else str(display_name or raw.get("name", ""))


def _note(raw: dict[str, Any]) -> str:
    address = str(raw.get("formattedAddress", "")).strip()
    demo_note = str(raw.get("_demo_note", "")).strip()
    return " · ".join(part for part in (address, demo_note) if part)


def normalize_stays(
    raw_items: list[dict[str, Any]],
    request: SearchRequest,
) -> tuple[list[StayCandidate], list[str]]:
    """계약 필수 가격·체크인 정보를 가진 row만 정규화하고 탈락 원인을 보존한다."""

    candidates: list[StayCandidate] = []
    issues: list[str] = []
    for index, raw in enumerate(raw_items):
        record_id = str(raw.get("id", f"row-{index}"))
        try:
            location = raw.get("location") or {}
            stay = SelectedStay(
                id=str(raw["id"]),
                name=_name(raw),
                lat=float(location["latitude"]),
                lng=float(location["longitude"]),
                price=float(raw["estimatedPrice"]),
                check_in_time=str(raw["checkInTime"]),
                check_out_time=str(raw["checkOutTime"]),
                note=_note(raw),
            )
            verification = verify_stay(stay, raw, request.trip_info.budget_currency)
            if verification.accepted:
                rating = float(raw["rating"]) if raw.get("rating") is not None else None
                candidates.append(StayCandidate(stay=stay, rating=rating, verification=verification))
            else:
                codes = ", ".join(issue.code for issue in verification.issues if issue.severity == "error")
                issues.append(f"{record_id}: 사실 검증 거부 ({codes or 'unknown'})")
        except (KeyError, TypeError, ValueError) as error:
            issues.append(f"{record_id}: 정규화 실패 ({error})")
    candidates.sort(key=lambda candidate: (candidate.stay.price, -(candidate.rating or 0)))
    return candidates[: request.max_results], issues
