"""호출 예산이 실제로 과금을 막는지 검증한다.

문서에 "조심하자"라고 쓰는 것으로는 과금을 막을 수 없다. 상한이 코드로
강제되는지, 그리고 상한에 닿았을 때 **예외로 죽지 않고 추정으로 넘어가는지**를
확인한다.

이 테스트는 네트워크에 나가지 않는다. `_post_json`을 가로채 "호출되었는가"만
센다.
"""

from __future__ import annotations

import pytest

from plan_agent import routing
from plan_agent.quota import BUDGET, CallBudget, QuotaExhausted

SENSOJI = (35.7148, 139.7967)
SHINJUKU = (35.6955, 139.7009)
TOKYO_TOWER = (35.6586, 139.7454)


@pytest.fixture
def with_fake_api(monkeypatch):
    """API 키가 있는 것처럼 만들고, 네트워크 대신 호출 횟수를 센다."""

    from plan_agent import config as config_module

    enabled = config_module.CONFIG.__class__(
        **{**vars(config_module.CONFIG), "google_maps_api_key": "test-key"}
    )
    monkeypatch.setattr(routing, "CONFIG", enabled)

    calls: list[str] = []

    def fake_post(url: str, body: dict, field_mask: str):
        calls.append(url)
        return {
            "routes": [{"duration": "1200s", "distanceMeters": 8400}]
        }

    # `_post_json`을 대체하되 예산 차감은 그대로 살린다.
    original = routing._post_json

    def counted(url: str, body: dict, field_mask: str):
        if not BUDGET.try_consume():
            raise QuotaExhausted("예산 초과")
        return fake_post(url, body, field_mask)

    monkeypatch.setattr(routing, "_post_json", counted)
    BUDGET.reset()
    routing.clear_cache()
    yield calls
    BUDGET.reset()
    routing.clear_cache()
    monkeypatch.setattr(routing, "_post_json", original)


# ── 상한이 강제된다 ──────────────────────────────────────────


def test_per_request_limit_stops_calls(monkeypatch, with_fake_api) -> None:
    calls = with_fake_api
    monkeypatch.setenv("ROUTES_MAX_CALLS_PER_REQUEST", "3")
    BUDGET.reload_limits()
    BUDGET.begin_request()

    # 서로 다른 좌표 10쌍을 요청한다(캐시를 우회하려고 좌표를 바꾼다).
    for index in range(10):
        routing.estimate_leg(
            SENSOJI, (35.6 + index * 0.01, 139.7 + index * 0.01), "대중교통"
        )

    assert len(calls) == 3, f"상한 3을 넘어 {len(calls)}번 호출됐습니다"


def test_total_limit_stops_calls(monkeypatch, with_fake_api) -> None:
    calls = with_fake_api
    monkeypatch.setenv("ROUTES_MAX_CALLS_TOTAL", "2")
    monkeypatch.setenv("ROUTES_MAX_CALLS_PER_REQUEST", "100")
    BUDGET.reload_limits()

    for request_index in range(5):
        BUDGET.begin_request()
        for index in range(5):
            routing.estimate_leg(
                SENSOJI,
                (35.6 + request_index * 0.1 + index * 0.01, 139.7 + index * 0.01),
                "대중교통",
            )

    assert len(calls) == 2, f"누적 상한 2를 넘어 {len(calls)}번 호출됐습니다"


def test_disabled_flag_prevents_all_calls(monkeypatch, with_fake_api) -> None:
    """ROUTES_ENABLED=off면 과금이 0이어야 한다."""
    calls = with_fake_api
    monkeypatch.setenv("ROUTES_ENABLED", "off")
    BUDGET.reload_limits()
    BUDGET.begin_request()

    for index in range(5):
        routing.estimate_leg(
            SENSOJI, (35.6 + index * 0.01, 139.7), "대중교통"
        )

    assert calls == []


# ── 상한에 닿아도 죽지 않는다 ────────────────────────────────


def test_exhausted_budget_falls_back_instead_of_raising(
    monkeypatch, with_fake_api
) -> None:
    """예산이 끝나도 일정 생성은 계속되어야 한다."""
    monkeypatch.setenv("ROUTES_MAX_CALLS_PER_REQUEST", "1")
    BUDGET.reload_limits()
    BUDGET.begin_request()

    first = routing.estimate_leg(SENSOJI, SHINJUKU, "대중교통")
    second = routing.estimate_leg(SENSOJI, TOKYO_TOWER, "대중교통")

    assert first.source == "routes_api"
    assert second.source == "estimated"  # 폴백
    assert second.minutes > 0  # 쓸 수 있는 값이 나온다


def test_cache_does_not_consume_budget(monkeypatch, with_fake_api) -> None:
    """같은 구간을 다시 물으면 호출하지 않는다. 과금 절약의 핵심."""
    calls = with_fake_api
    monkeypatch.setenv("ROUTES_MAX_CALLS_PER_REQUEST", "10")
    BUDGET.reload_limits()
    BUDGET.begin_request()

    for _ in range(5):
        routing.estimate_leg(SENSOJI, SHINJUKU, "대중교통")

    assert len(calls) == 1, "캐시가 동작하지 않아 중복 호출됐습니다"
    assert BUDGET.total_used == 1


# ── 카운터와 보고 ────────────────────────────────────────────


def test_budget_counts_blocked_calls() -> None:
    budget = CallBudget()
    budget.reset()
    budget.max_total = 1
    budget.max_per_request = 1
    budget.begin_request()

    assert budget.try_consume() is True
    assert budget.try_consume() is False
    assert budget.total_used == 1
    assert budget.blocked_count == 1


def test_describe_mentions_limits() -> None:
    budget = CallBudget()
    budget.reset()
    text = budget.describe()
    assert "Routes API" in text
    assert str(budget.max_total) in text


def test_begin_request_resets_only_request_counter() -> None:
    budget = CallBudget()
    budget.reset()
    budget.max_total = 100
    budget.max_per_request = 2

    budget.begin_request()
    budget.try_consume()
    budget.try_consume()
    assert budget.try_consume() is False  # 요청 상한

    budget.begin_request()
    assert budget.try_consume() is True  # 새 요청이므로 다시 가능
    assert budget.total_used == 3  # 누적은 유지
