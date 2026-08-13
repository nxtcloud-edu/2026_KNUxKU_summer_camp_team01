"""이동시간 계산 — Google Routes API 1차, 좌표 기반 추정 폴백.

## 어떤 Google API를 쓰는가

**Routes API 하나만** 쓴다. Google Cloud 콘솔에서 `Routes API`만 사용 설정하면
된다. 좌표는 Search Agent가 이미 주므로 Geocoding·Places는 필요 없다.

| 메서드 | 엔드포인트 | 이 프로젝트에서의 용도 |
|---|---|---|
| `computeRouteMatrix` | `POST /directions/v2:computeRouteMatrix` | 일자 배치용 N×N 벌크 조회 |
| `computeRoutes` | `POST /directions/v2:computeRoutes` | 확정된 연속 구간 1건씩 (요금 포함) |

확인한 제약:

- **`X-Goog-FieldMask` 헤더가 필수다.** 기본 반환 필드가 없어서 빠뜨리면 에러.
- `computeRouteMatrix`는 원소(출발지 × 목적지) **625개**까지. 단
  **TRANSIT이면 100개**까지.
- TRANSIT 경로는 다른 모드와 응답 필드가 다르고, 필드 마스크로 요금을 받을 수 있다.

레거시 `Distance Matrix API` / `Directions API`는 쓰지 않는다. Routes API가
후속 API다.

## 추정값을 어떻게 표시하는가

계약(`plan-to-verification.schema.json`)의 `travel_from_prev`는
`mode` · `estimated_min` · `distance_km` 세 필드뿐이고
`additionalProperties: false`다. 추정 여부를 담을 자리가 없다.

`mode` 문자열에 `"대중교통(추정)"`처럼 끼워 넣을 수는 있지만, 그 값은 검증
에이전트의 Gemini가 그대로 읽는 입력이라 판단을 흐린다. 그래서
**계약 payload는 건드리지 않고 서버 로그와 내부 진단에만 남긴다.**
`TravelEstimate.source`가 그 정보를 들고 다니며, 경계를 넘을 때 버려진다.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal

from . import geo, timecalc
from .config import CONFIG
from .models import TravelFromPrevious

logger = logging.getLogger(__name__)

ROUTES_BASE = "https://routes.googleapis.com"
COMPUTE_ROUTES_URL = f"{ROUTES_BASE}/directions/v2:computeRoutes"
COMPUTE_MATRIX_URL = f"{ROUTES_BASE}/directions/v2:computeRouteMatrix"

# 확인된 상한. 초과하면 Google이 에러를 준다.
MATRIX_MAX_ELEMENTS = 625
MATRIX_MAX_ELEMENTS_TRANSIT = 100

# 필드 마스크는 필수다. 필요한 것만 좁게 요청해 응답 크기와 과금을 줄인다.
ROUTES_FIELD_MASK = "routes.duration,routes.distanceMeters"
ROUTES_FIELD_MASK_TRANSIT = (
    "routes.duration,routes.distanceMeters,routes.travelAdvisory.transitFare"
)
MATRIX_FIELD_MASK = (
    "originIndex,destinationIndex,duration,distanceMeters,condition"
)

# 내부 모드 키 -> Routes API travelMode
_TRAVEL_MODE = {
    "walk": "WALK",
    "transit": "TRANSIT",
    "car": "DRIVE",
    "taxi": "DRIVE",
    "bike": "BICYCLE",
}

TravelSource = Literal["routes_api", "routes_matrix", "estimated"]


@dataclass(frozen=True)
class TravelEstimate:
    """이동 구간 하나. `source`는 경계를 넘지 않는 내부 진단 정보다."""

    mode_label: str
    minutes: int
    distance_km: float
    source: TravelSource
    fare_amount: float | None = None
    fare_currency: str | None = None

    @property
    def is_estimated(self) -> bool:
        return self.source == "estimated"

    def to_contract(self) -> TravelFromPrevious:
        """계약 형식으로 변환한다. `source`와 요금은 여기서 버려진다.

        계약에 담을 자리가 없기 때문이다. 버리기 전에 호출부가 로그를 남긴다.
        """

        return TravelFromPrevious(
            mode=self.mode_label,
            estimated_min=self.minutes,
            distance_km=round(self.distance_km, 2),
        )


def _post_json(url: str, body: dict, field_mask: str) -> dict | list:
    """Routes API 호출. 실패는 예외로 올린다(호출부가 폴백을 결정한다)."""

    if not CONFIG.has_routes_api:
        raise RuntimeError("GOOGLE_MAPS_API_KEY가 없습니다")

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": CONFIG.google_maps_api_key,
            # 필수 헤더. 없으면 Google이 에러를 준다.
            "X-Goog-FieldMask": field_mask,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=CONFIG.routes_timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _waypoint(lat: float, lng: float) -> dict:
    return {"location": {"latLng": {"latitude": lat, "longitude": lng}}}


def _parse_duration_seconds(value: str | int | float | None) -> int | None:
    """Routes API의 `duration`은 `"1234s"` 형태 문자열이다."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.endswith("s"):
        text = text[:-1]
    try:
        return int(float(text))
    except ValueError:
        logger.warning("duration 파싱 실패: %r", value)
        return None


def _fare_from_route(route: dict) -> tuple[float | None, str | None]:
    fare = route.get("travelAdvisory", {}).get("transitFare")
    if not isinstance(fare, dict):
        return None, None
    units = fare.get("units")
    nanos = fare.get("nanos", 0)
    currency = fare.get("currencyCode")
    if units is None and not nanos:
        return None, currency
    amount = float(units or 0) + float(nanos or 0) / 1_000_000_000
    return amount, currency


# 캐시 키: (출발 좌표, 도착 좌표, 모드). 같은 구간을 재생성마다 다시 묻지 않는다.
_cache: dict[tuple, TravelEstimate] = {}


def _cache_key(
    origin: tuple[float, float], destination: tuple[float, float], mode_key: str
) -> tuple:
    return (round(origin[0], 5), round(origin[1], 5), round(destination[0], 5), round(destination[1], 5), mode_key)


def estimate_leg(
    origin: tuple[float, float],
    destination: tuple[float, float],
    transport_mode: str,
) -> TravelEstimate:
    """두 지점 사이 이동을 계산한다. 실패해도 예외를 올리지 않는다.

    Routes API가 안 되면 좌표 기반 추정으로 떨어지고, 그 사실을 `source`와
    로그에 남긴다. 일정 생성이 멈추는 것보다 추정값으로라도 만드는 게 낫되,
    추정을 실제 측정값처럼 보이게 하지는 않는다.
    """

    mode_key = geo.normalize_mode(transport_mode)
    if not geo.is_known_mode(transport_mode):
        logger.info(
            "transport_mode %r을 알 수 없어 %s로 처리합니다.", transport_mode, mode_key
        )

    key = _cache_key(origin, destination, mode_key)
    if CONFIG.routes_cache_enabled and key in _cache:
        return _cache[key]

    estimate = _estimate_uncached(origin, destination, transport_mode, mode_key)
    if CONFIG.routes_cache_enabled:
        _cache[key] = estimate
    return estimate


def _estimate_uncached(
    origin: tuple[float, float],
    destination: tuple[float, float],
    transport_mode: str,
    mode_key: str,
) -> TravelEstimate:
    straight_km = geo.haversine_km(origin[0], origin[1], destination[0], destination[1])

    if CONFIG.has_routes_api:
        try:
            return _call_compute_routes(
                origin, destination, transport_mode, mode_key
            )
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            logger.warning(
                "Routes API 호출 실패(%s). 좌표 기반 추정으로 대체합니다: %s",
                type(error).__name__,
                error,
            )
        except (KeyError, ValueError, RuntimeError) as error:
            logger.warning(
                "Routes API 응답 처리 실패(%s). 좌표 기반 추정으로 대체합니다: %s",
                type(error).__name__,
                error,
            )
    else:
        logger.debug("GOOGLE_MAPS_API_KEY 없음. 좌표 기반 추정을 사용합니다.")

    minutes = timecalc.round_up_to_5(geo.estimate_minutes(straight_km, mode_key))
    return TravelEstimate(
        mode_label=transport_mode,
        minutes=minutes,
        distance_km=geo.road_distance_km(straight_km, mode_key),
        source="estimated",
    )


def _call_compute_routes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    transport_mode: str,
    mode_key: str,
) -> TravelEstimate:
    travel_mode = _TRAVEL_MODE.get(mode_key, "TRANSIT")
    body: dict = {
        "origin": _waypoint(*origin),
        "destination": _waypoint(*destination),
        "travelMode": travel_mode,
    }
    # TRANSIT은 routingPreference를 받지 않는다. 다른 모드에만 붙인다.
    if travel_mode == "DRIVE":
        body["routingPreference"] = "TRAFFIC_UNAWARE"

    field_mask = (
        ROUTES_FIELD_MASK_TRANSIT if travel_mode == "TRANSIT" else ROUTES_FIELD_MASK
    )
    payload = _post_json(COMPUTE_ROUTES_URL, body, field_mask)
    if not isinstance(payload, dict):
        raise ValueError("computeRoutes 응답이 객체가 아닙니다")

    routes = payload.get("routes") or []
    if not routes:
        # 경로를 못 찾은 것은 예외 상황이 아니라 정보다. 폴백으로 넘긴다.
        raise ValueError("경로를 찾지 못했습니다")

    route = routes[0]
    seconds = _parse_duration_seconds(route.get("duration"))
    if seconds is None:
        raise ValueError("duration이 없습니다")

    distance_m = route.get("distanceMeters")
    distance_km = (
        float(distance_m) / 1000.0
        if isinstance(distance_m, (int, float))
        else geo.haversine_km(origin[0], origin[1], destination[0], destination[1])
    )
    fare_amount, fare_currency = _fare_from_route(route)

    return TravelEstimate(
        mode_label=transport_mode,
        minutes=timecalc.round_up_to_5(int(round(seconds / 60))),
        distance_km=distance_km,
        source="routes_api",
        fare_amount=fare_amount,
        fare_currency=fare_currency,
    )


def matrix_minutes(
    points: list[tuple[float, float]], transport_mode: str
) -> list[list[int]]:
    """모든 지점 쌍의 이동시간(분). 일자 배치에서 클러스터링 기준으로 쓴다.

    Routes API를 쓸 수 없거나 원소 수 상한을 넘으면 전부 좌표 기반 추정으로
    계산한다. 상한은 TRANSIT 100개, 그 외 625개다.
    """

    size = len(points)
    mode_key = geo.normalize_mode(transport_mode)
    elements = size * size
    limit = (
        MATRIX_MAX_ELEMENTS_TRANSIT
        if _TRAVEL_MODE.get(mode_key) == "TRANSIT"
        else MATRIX_MAX_ELEMENTS
    )

    if CONFIG.has_routes_api and elements <= limit:
        try:
            return _call_matrix(points, transport_mode, mode_key)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as error:
            logger.warning(
                "computeRouteMatrix 실패(%s). 좌표 기반 추정으로 대체합니다: %s",
                type(error).__name__,
                error,
            )
    elif CONFIG.has_routes_api:
        logger.info(
            "행렬 원소 %d개가 상한 %d개를 넘어 좌표 기반 추정을 사용합니다.",
            elements,
            limit,
        )

    return [
        [
            timecalc.round_up_to_5(
                geo.estimate_minutes(
                    geo.haversine_km(a[0], a[1], b[0], b[1]), mode_key
                )
            )
            if index_a != index_b
            else 0
            for index_b, b in enumerate(points)
        ]
        for index_a, a in enumerate(points)
    ]


def _call_matrix(
    points: list[tuple[float, float]], transport_mode: str, mode_key: str
) -> list[list[int]]:
    travel_mode = _TRAVEL_MODE.get(mode_key, "TRANSIT")
    waypoints = [{"waypoint": _waypoint(lat, lng)} for lat, lng in points]
    body: dict = {
        "origins": waypoints,
        "destinations": waypoints,
        "travelMode": travel_mode,
    }
    if travel_mode == "DRIVE":
        body["routingPreference"] = "TRAFFIC_UNAWARE"

    payload = _post_json(COMPUTE_MATRIX_URL, body, MATRIX_FIELD_MASK)
    if not isinstance(payload, list):
        raise ValueError("computeRouteMatrix 응답이 배열이 아닙니다")

    size = len(points)
    result = [[0] * size for _ in range(size)]
    seen = 0
    for element in payload:
        origin_index = element.get("originIndex")
        dest_index = element.get("destinationIndex")
        if origin_index is None or dest_index is None:
            continue
        seconds = _parse_duration_seconds(element.get("duration"))
        if seconds is None:
            continue
        result[origin_index][dest_index] = timecalc.round_up_to_5(
            int(round(seconds / 60))
        )
        seen += 1

    if seen == 0:
        raise ValueError("행렬 응답에 사용할 수 있는 원소가 없습니다")
    return result


def clear_cache() -> None:
    """테스트에서 상태가 새지 않게 한다."""

    _cache.clear()


def cache_size() -> int:
    return len(_cache)


__all__ = [
    "COMPUTE_MATRIX_URL",
    "COMPUTE_ROUTES_URL",
    "MATRIX_MAX_ELEMENTS",
    "MATRIX_MAX_ELEMENTS_TRANSIT",
    "TravelEstimate",
    "cache_size",
    "clear_cache",
    "estimate_leg",
    "matrix_minutes",
]
