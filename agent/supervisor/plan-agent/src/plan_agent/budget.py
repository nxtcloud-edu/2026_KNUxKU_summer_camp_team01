"""예산 합산과 숙박비 분배.

## 검증 에이전트의 예산 판정을 그대로 복제한다

`verification-agent/rules.py::check_budget`은 이렇게 계산한다.

    for item in 모든 항목:
        if item.category가 budget_includes에 없으면: skip
        multiplier = num_travelers if price_unit == "per_person" else 1
        estimated_total += item.price * multiplier

    over_by = max(0, estimated_total - budget_total)
    status = "fail" if over_by > 0 else "pass"

`budget_includes`가 빈 배열이면 **전부 포함**으로 본다(`_is_included_in_budget`).
빈 배열을 "아무것도 포함하지 않음"으로 해석하지 않는다.

## 숙박비 중복 가산 문제

검증 에이전트는 `LAST_ITEM_NOT_STAY` 규칙으로 **마지막 여행일을 제외한 모든 날의
마지막 항목이 `숙소`**이기를 요구한다. 4박 5일이면 숙소 항목이 4번 등장한다.

그런데 `SelectedStay.price_unit`은 `per_stay`이고 `price`는 숙박 전체 금액이다.
그대로 4번 넣으면 예산 합산에서 숙박비가 4배로 잡힌다. 18만원이 72만원이 된다.

그래서 총액을 밤 수만큼 나눠 **각 숙소 항목에 1박 요금을 넣는다.** 합이 총액과
정확히 일치하도록 마지막 밤에 잔액을 넣어 반올림 오차를 흡수한다.
"""

from __future__ import annotations

from .models import (
    Category,
    PlanToVerificationInput,
    TripInfo,
    Violation,
)

# rules.py `BUDGET_ALIASES`와 동일. 원본이 바뀌면 함께 바꾼다.
BUDGET_ALIASES: dict[str, set[str]] = {
    "관광지": {"관광지", "관광", "activity", "activities"},
    "식사": {"식사", "food"},
    "카페": {"카페", "cafe"},
    "쇼핑": {"쇼핑", "shopping"},
    "휴식": {"휴식", "relax"},
    "숙소": {"숙소", "stay"},
}


def _normalize(value: str) -> str:
    """rules.py `_normalize`와 동일."""

    return value.strip().casefold()


def is_included_in_budget(category: str, budget_includes: list[str]) -> bool:
    """rules.py `_is_included_in_budget`와 동일.

    빈 `budget_includes`는 '전부 포함'이다.
    """

    if not budget_includes:
        return True
    normalized = {_normalize(value) for value in budget_includes}
    return bool(BUDGET_ALIASES[category] & normalized)


def price_multiplier(price_unit: str, num_travelers: int) -> int:
    """rules.py `check_budget`의 multiplier와 동일."""

    return num_travelers if price_unit == "per_person" else 1


def distribute_stay_price(total_price: float, occurrences: int) -> list[float]:
    """숙박 총액을 등장 횟수만큼 나눈다. 합은 총액과 정확히 같다.

    `round`를 각 항목에 그대로 쓰면 합이 총액과 어긋난다(예: 100000 / 3).
    그래서 앞의 n-1개는 반올림하고 마지막 하나에 잔액을 넣는다.

    >>> distribute_stay_price(180000, 4)
    [45000.0, 45000.0, 45000.0, 45000.0]
    >>> sum(distribute_stay_price(100000, 3)) == 100000
    True
    """

    if occurrences <= 0:
        return []
    if occurrences == 1:
        return [round(total_price, 2)]

    per_night = round(total_price / occurrences, 2)
    amounts = [per_night] * (occurrences - 1)
    remainder = round(total_price - per_night * (occurrences - 1), 2)
    amounts.append(remainder)
    return amounts


def estimate_total(payload: PlanToVerificationInput) -> float:
    """검증 에이전트가 계산할 `estimated_total`을 미리 같은 방식으로 구한다."""

    trip = payload.trip_info
    total = 0.0
    for day in payload.plan.days:
        for item in day.items:
            if not is_included_in_budget(item.category, trip.budget_includes):
                continue
            total += item.price * price_multiplier(item.price_unit, trip.num_travelers)
    return total


def check_budget(payload: PlanToVerificationInput) -> list[Violation]:
    """예산 초과를 미리 잡는다.

    검증 에이전트는 초과를 `fail`로 판정하므로, 여기서 걸리면 일정을 고쳐야 한다.
    조용히 넘기지 않고 초과액을 담아 반환한다.
    """

    trip = payload.trip_info
    total = estimate_total(payload)
    over_by = total - trip.budget_total
    if over_by <= 0:
        return []
    return [
        Violation(
            code="BUDGET_EXCEEDED",
            message=(
                f"예상 비용 {total:,.0f}{trip.budget_currency}가 "
                f"예산 {trip.budget_total:,.0f}{trip.budget_currency}를 "
                f"{over_by:,.0f} 초과합니다."
            ),
        )
    ]


def item_cost(
    price: float, price_unit: str, category: Category, trip: TripInfo
) -> float:
    """항목 하나가 예산 합산에 기여하는 금액. 배치 중 누적 확인용."""

    if not is_included_in_budget(category, trip.budget_includes):
        return 0.0
    return price * price_multiplier(price_unit, trip.num_travelers)


__all__ = [
    "BUDGET_ALIASES",
    "check_budget",
    "distribute_stay_price",
    "estimate_total",
    "is_included_in_budget",
    "item_cost",
    "price_multiplier",
]
