"""좌표 거리와 이동시간 추정. 전부 결정론적이다.

Google Routes API를 쓸 수 없을 때의 폴백이며, 이 경로로 계산된 값은
호출부에서 **추정값임을 반드시 표시**한다(`routing.py` 참조). 추정을 실제
측정값처럼 흘려보내는 것이 이 프로젝트에서 가장 피하고 싶은 종류의 조용한
실패다.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088

# 이동 수단별 (실효 속도 km/h, 우회 계수, 고정 대기·환승 분).
#
# 직선거리에 우회 계수를 곱해 실제 경로 길이를 근사하고, 실효 속도로 나눈 뒤
# 고정 대기를 더한다. 도시 이동을 기준으로 한 보수적인 값이다.
_MODE_PROFILE: dict[str, tuple[float, float, int]] = {
    "walk": (4.5, 1.25, 0),
    "transit": (20.0, 1.30, 6),
    "car": (25.0, 1.35, 3),
    "taxi": (25.0, 1.35, 3),
    "bike": (13.0, 1.25, 0),
}

# 한국어 transport_mode를 위 프로필 키로 옮긴다.
# `transport_mode`는 계약에서 자유 문자열(minLength 1)이므로 목록에 없는 값이
# 올 수 있다. 그때는 대중교통으로 본다(도시 여행의 기본값).
_MODE_ALIASES: dict[str, str] = {
    "도보": "walk",
    "걷기": "walk",
    "walk": "walk",
    "walking": "walk",
    "대중교통": "transit",
    "지하철": "transit",
    "버스": "transit",
    "transit": "transit",
    "public": "transit",
    "자차": "car",
    "렌터카": "car",
    "자동차": "car",
    "차량": "car",
    "car": "car",
    "driving": "car",
    "택시": "taxi",
    "taxi": "taxi",
    "자전거": "bike",
    "bike": "bike",
    "bicycle": "bike",
}

DEFAULT_MODE = "transit"


def normalize_mode(transport_mode: str) -> str:
    """`transport_mode` 문자열을 내부 이동수단 키로 바꾼다.

    목록에 없으면 `transit`으로 떨어지되, 호출부가 그 사실을 알 수 있도록
    `is_known_mode`를 함께 제공한다. 조용히 기본값으로 바꾸고 넘어가면
    "왜 도보 여행인데 지하철 시간이 나오지"를 나중에 디버깅하게 된다.
    """

    return _MODE_ALIASES.get(transport_mode.strip().casefold(), DEFAULT_MODE)


def is_known_mode(transport_mode: str) -> bool:
    return transport_mode.strip().casefold() in _MODE_ALIASES


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이 대권 거리(km)."""

    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = radians(lng2 - lng1)
    inner = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(inner))


def estimate_minutes(distance_km: float, mode_key: str) -> int:
    """직선거리와 이동수단으로 소요시간(분)을 추정한다.

    반환 전 5분 단위로 올림하지 않는다. 올림은 호출부(`routing.py`)가 실제
    측정값과 추정값에 같은 규칙으로 적용한다.
    """

    speed_kmh, detour, fixed_wait = _MODE_PROFILE.get(mode_key, _MODE_PROFILE[DEFAULT_MODE])
    if distance_km <= 0:
        return fixed_wait
    road_km = distance_km * detour
    travel_minutes = (road_km / speed_kmh) * 60
    return int(round(travel_minutes)) + fixed_wait


def road_distance_km(distance_km: float, mode_key: str) -> float:
    """직선거리에 우회 계수를 적용한 경로 거리(km).

    `travel_from_prev.distance_km`에 직선거리를 그대로 넣으면 실제보다 짧아
    보인다. 추정 경로에서는 우회 계수를 반영한 값을 쓴다.
    """

    _, detour, _ = _MODE_PROFILE.get(mode_key, _MODE_PROFILE[DEFAULT_MODE])
    return round(distance_km * detour, 2)


def centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    """좌표 목록의 산술 평균. 지역 클러스터링 기준점으로 쓴다."""

    if not points:
        raise ValueError("좌표가 하나도 없습니다")
    lat = sum(point[0] for point in points) / len(points)
    lng = sum(point[1] for point in points) / len(points)
    return lat, lng


__all__ = [
    "DEFAULT_MODE",
    "EARTH_RADIUS_KM",
    "centroid",
    "estimate_minutes",
    "haversine_km",
    "is_known_mode",
    "normalize_mode",
    "road_distance_km",
]
