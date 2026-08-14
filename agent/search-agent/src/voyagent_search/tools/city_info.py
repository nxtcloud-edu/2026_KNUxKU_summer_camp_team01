"""구조화된 공식 웹 자료를 내부 CityInfo로 정규화하고 출처를 검증하는 Tool."""

from __future__ import annotations

from typing import Any

from ..contracts import CityInfo, CityInfoResult
from .fact_check import verify_city_info


def normalize_city_info(raw_items: list[dict[str, Any]]) -> CityInfoResult:
    """첫 번째 승인 도시 프로필을 검증하며 cityInfo는 최종 Plan handoff와 분리한다."""

    if not raw_items:
        return CityInfoResult(status="error", error="도시 정보 결과가 없습니다")
    raw = raw_items[0]
    try:
        payload = {key: value for key, value in raw.items() if not key.startswith("_")}
        city_info = CityInfo.model_validate(payload)
        verification = verify_city_info(city_info, raw)
    except (TypeError, ValueError) as error:
        return CityInfoResult(status="error", error=f"도시 정보 정규화 실패: {error}")
    if not verification.accepted:
        return CityInfoResult(status="error", verification=verification, error="도시 정보 출처 검증 실패")
    return CityInfoResult(status="success", city_info=city_info, verification=verification)
