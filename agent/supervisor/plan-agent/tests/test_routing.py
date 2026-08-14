"""이동시간 계산 테스트.

키가 없는 환경(CI·로컬 기본)에서도 전부 통과해야 한다. Routes API를 실제로
호출하는 테스트는 넣지 않는다 — 과금이 발생하고 네트워크에 의존해 불안정하다.
대신 **폴백 경로가 정확히 동작하는지**와 **추정 사실이 계약 payload로 새지
않는지**를 확인한다.
"""

from __future__ import annotations

import pytest

from plan_agent import geo, routing, timecalc

# 도쿄 실제 좌표
SENSOJI = (35.7148, 139.7967)
SHINJUKU_HOTEL = (35.6955, 139.7009)
TOKYO_TOWER = (35.6586, 139.7454)


@pytest.fixture(autouse=True)
def _clear_cache():
    routing.clear_cache()
    yield
    routing.clear_cache()


# ── 계약 경계: 내부 진단 정보가 새지 않는다 ────────────────────


def test_contract_payload_has_exactly_three_fields() -> None:
    """`travel_from_prev`는 mode/estimated_min/distance_km 세 개뿐이다.

    스키마가 `additionalProperties: false`이므로 필드가 하나라도 늘면
    검증 에이전트가 입력을 거부한다.
    """
    estimate = routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "대중교통")
    payload = estimate.to_contract().model_dump()
    assert set(payload) == {"mode", "estimated_min", "distance_km"}


def test_estimated_flag_does_not_leak_into_contract() -> None:
    """추정 여부는 로그·내부 객체에만 남고 계약에는 넣지 않는다.

    `mode`에 '(추정)'을 붙이면 검증 에이전트의 Gemini가 그 문자열을 읽어
    판단이 흐려진다. 그래서 mode는 입력 그대로 유지한다.
    """
    estimate = routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "대중교통")
    assert estimate.is_estimated is True  # 키가 없으므로 추정 경로
    payload = estimate.to_contract().model_dump()
    assert payload["mode"] == "대중교통"
    assert "추정" not in payload["mode"]


def test_fare_is_dropped_at_contract_boundary() -> None:
    """요금 정보도 계약에 담을 자리가 없다. 조용히 사라지는 게 아니라 설계다."""
    estimate = routing.TravelEstimate(
        mode_label="대중교통",
        minutes=35,
        distance_km=8.4,
        source="routes_api",
        fare_amount=280.0,
        fare_currency="JPY",
    )
    payload = estimate.to_contract().model_dump()
    assert "fare_amount" not in payload
    assert "fare_currency" not in payload


# ── 폴백 동작 ────────────────────────────────────────────────


def test_falls_back_to_estimate_without_api_key() -> None:
    estimate = routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "대중교통")
    assert estimate.source == "estimated"
    assert estimate.minutes > 0
    assert estimate.distance_km > 0


def test_travel_minutes_are_rounded_up_to_five() -> None:
    """올림을 쓰는 이유: 내림은 INSUFFICIENT_TRAVEL_TIME을 유발할 수 있다."""
    estimate = routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "대중교통")
    assert estimate.minutes % 5 == 0


def test_road_distance_is_longer_than_straight_line() -> None:
    """직선거리를 그대로 쓰면 실제보다 짧아 보인다."""
    straight = geo.haversine_km(*SENSOJI, *SHINJUKU_HOTEL)
    estimate = routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "대중교통")
    assert estimate.distance_km > straight


def test_walking_is_slower_than_transit_for_same_pair() -> None:
    routing.clear_cache()
    walk = routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "도보")
    routing.clear_cache()
    transit = routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "대중교통")
    assert walk.minutes > transit.minutes


def test_unknown_transport_mode_falls_back_to_transit_but_keeps_label() -> None:
    """모드를 못 알아봐도 사용자가 쓴 문자열은 계약에 그대로 남긴다."""
    estimate = routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "우주선")
    assert estimate.to_contract().mode == "우주선"
    assert estimate.minutes > 0


# ── 캐시 ─────────────────────────────────────────────────────


def test_cache_prevents_repeated_computation() -> None:
    assert routing.cache_size() == 0
    routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "대중교통")
    assert routing.cache_size() == 1
    routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "대중교통")
    assert routing.cache_size() == 1


def test_cache_distinguishes_modes() -> None:
    routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "대중교통")
    routing.estimate_leg(SENSOJI, SHINJUKU_HOTEL, "도보")
    assert routing.cache_size() == 2


# ── 행렬 ─────────────────────────────────────────────────────


def test_matrix_is_square_with_zero_diagonal() -> None:
    points = [SENSOJI, SHINJUKU_HOTEL, TOKYO_TOWER]
    matrix = routing.matrix_minutes(points, "대중교통")
    assert len(matrix) == 3
    assert all(len(row) == 3 for row in matrix)
    for index in range(3):
        assert matrix[index][index] == 0


def test_matrix_is_symmetric_in_fallback_mode() -> None:
    """좌표 기반 추정은 방향이 없으므로 대칭이다.

    실제 Routes API는 일방통행·환승 때문에 비대칭일 수 있다. 그래서 이 성질에
    의존하는 코드를 쓰지 않는다.
    """
    points = [SENSOJI, SHINJUKU_HOTEL, TOKYO_TOWER]
    matrix = routing.matrix_minutes(points, "대중교통")
    for i in range(3):
        for j in range(3):
            assert matrix[i][j] == matrix[j][i]


def test_matrix_element_limits_match_documented_values() -> None:
    """검색으로 확인한 Google 문서상 상한.

    TRANSIT은 100개, 그 외는 625개. 이 값을 넘으면 Google이 에러를 준다.
    """
    assert routing.MATRIX_MAX_ELEMENTS == 625
    assert routing.MATRIX_MAX_ELEMENTS_TRANSIT == 100


def test_large_matrix_falls_back_without_error() -> None:
    """상한을 넘는 크기를 줘도 예외 없이 추정으로 처리한다."""
    points = [(35.6 + index * 0.001, 139.7 + index * 0.001) for index in range(15)]
    matrix = routing.matrix_minutes(points, "대중교통")
    assert len(matrix) == 15


# ── 좌표 계산 ────────────────────────────────────────────────


def test_haversine_matches_known_distance() -> None:
    """센소지 - 신주쿠 직선거리는 약 8.9km다."""
    km = geo.haversine_km(*SENSOJI, *SHINJUKU_HOTEL)
    assert 8.5 < km < 9.3


def test_same_point_is_zero_distance() -> None:
    assert geo.haversine_km(*SENSOJI, *SENSOJI) == pytest.approx(0.0, abs=1e-9)


def test_mode_normalization() -> None:
    assert geo.normalize_mode("대중교통") == "transit"
    assert geo.normalize_mode("도보") == "walk"
    assert geo.normalize_mode("택시") == "taxi"
    assert geo.normalize_mode("렌터카") == "car"
    assert geo.normalize_mode("알 수 없는 값") == geo.DEFAULT_MODE
    assert geo.is_known_mode("대중교통") is True
    assert geo.is_known_mode("우주선") is False


def test_duration_parsing_handles_routes_api_format() -> None:
    """Routes API의 duration은 `"1234s"` 형태 문자열이다."""
    assert routing._parse_duration_seconds("1234s") == 1234
    assert routing._parse_duration_seconds("60s") == 60
    assert routing._parse_duration_seconds(90) == 90
    assert routing._parse_duration_seconds(None) is None
    assert routing._parse_duration_seconds("이상한값") is None


def test_five_minute_rounding_never_shortens() -> None:
    for raw in range(0, 60):
        rounded = timecalc.round_up_to_5(raw)
        assert rounded >= raw
        assert rounded % 5 == 0
