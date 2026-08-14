"""공급자 중립 내부 항공 원문을 Search→Plan의 SelectedFlight 후보로 만드는 Tool."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from ..contracts import FlightCandidate, Money, SearchRequest, SelectedFlight, TravelLeg
from .fact_check import verify_flight

_DURATION = re.compile(r"^P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?$")


def _minutes(value: str, depart_at: str, arrive_at: str) -> int:
    """ISO-8601 duration을 분으로 바꾸고 없으면 같은 timezone 시각 차이로 계산한다."""

    match = _DURATION.match(value or "")
    if match:
        return int(match.group(1) or 0) * 60 + int(match.group(2) or 0)
    depart = datetime.fromisoformat(depart_at.replace("Z", "+00:00"))
    arrive = datetime.fromisoformat(arrive_at.replace("Z", "+00:00"))
    if depart.tzinfo is None or arrive.tzinfo is None:
        raise ValueError("timezone 없는 항공 시각에는 provider duration이 필요합니다")
    return max(int((arrive - depart).total_seconds() // 60), 0)


def _leg(itinerary: dict[str, Any]) -> TravelLeg:
    segments = itinerary.get("segments") or []
    if not segments:
        raise ValueError("항공 itinerary에 segment가 없습니다")
    depart_at = str(segments[0]["departure"]["at"])
    arrive_at = str(segments[-1]["arrival"]["at"])
    return TravelLeg(
        depart_at=depart_at,
        arrive_at=arrive_at,
        duration_min=_minutes(str(itinerary.get("duration", "")), depart_at, arrive_at),
    )


def normalize_flight_offers(
    raw_items: list[dict[str, Any]],
    request: SearchRequest,
) -> tuple[list[FlightCandidate], list[str]]:
    """원문을 정규화하고 탈락 row 원인을 보존한 뒤 가격·시간순 최대 20건 정렬한다."""

    candidates: list[FlightCandidate] = []
    issues: list[str] = []
    for index, raw in enumerate(raw_items):
        record_id = str(raw.get("id", f"row-{index}"))
        try:
            itineraries = raw.get("itineraries") or []
            outbound = _leg(itineraries[0])
            inbound = _leg(itineraries[1]) if len(itineraries) > 1 else None
            price = raw.get("price")
            if not isinstance(price, dict):
                raise ValueError("항공 원문에 price object가 필요합니다")
            if "grandTotal" in price:
                raw_amount = price["grandTotal"]
            elif "total" in price:
                raw_amount = price["total"]
            else:
                raise ValueError("항공 원문에 명시적 가격이 필요합니다")
            amount = float(raw_amount)
            if not math.isfinite(amount) or amount <= 0:
                raise ValueError("항공 원문의 가격은 유한한 양수여야 합니다")
            currency = price.get("currency")
            if not isinstance(currency, str) or not currency:
                raise ValueError("항공 원문에 명시적 통화가 필요합니다")
            offer = SelectedFlight(
                id=str(raw["id"]),
                outbound=outbound,
                inbound=inbound,
                total_price=Money(amount=amount, currency=currency),
            )
            carriers = sorted({
                str(segment.get("carrierCode"))
                for itinerary in itineraries
                for segment in itinerary.get("segments", [])
                if segment.get("carrierCode")
            })
            verification = verify_flight(offer, raw, request.trip_info.budget_currency)
            if verification.accepted:
                candidates.append(FlightCandidate(offer=offer, carrier_codes=carriers, verification=verification))
            else:
                codes = ", ".join(issue.code for issue in verification.issues if issue.severity == "error")
                issues.append(f"{record_id}: 사실 검증 거부 ({codes or 'unknown'})")
        except (IndexError, KeyError, TypeError, ValueError) as error:
            issues.append(f"{record_id}: 정규화 실패 ({error})")
    candidates.sort(key=lambda candidate: (candidate.offer.total_price.amount, candidate.offer.outbound.duration_min))
    return candidates[: request.max_results], issues
