"""테스트 공통 설정.

## 테스트는 실제 API를 호출하지 않는다

`.env`에 키가 들어오면 `routing.estimate_leg`가 실제 Google Routes API를 부른다.
테스트에서 그러면 세 가지가 나빠진다.

1. **과금된다.** 테스트를 100번 돌리면 100번 청구된다.
2. **느리고 불안정해진다.** 네트워크가 끊기면 관계없는 테스트가 실패한다.
3. **결과가 흔들린다.** 실제 이동시간은 교통 상황에 따라 달라져서
   "같은 입력이면 같은 출력"을 검증할 수 없다.

그래서 모든 테스트에서 API 키를 지워 좌표 기반 추정 경로로 고정한다.
실제 API 호출은 `test_live_api.py`가 명시적 옵션(`--live-api`)으로만 수행한다.
"""

from __future__ import annotations

import os

import pytest

# `quota.CallBudget.reload_limits()`처럼 os.getenv를 직접 읽는 코드가 있다.
# `_isolate_external_apis`가 `CONFIG` 객체만 패치하면 이런 코드는 영향을 받지
# 않는다. 실제로 이 프로젝트에서 서버를 `ROUTES_ENABLED=off`로 띄운 뒤 같은
# 셀에서 pytest를 돌리면 `test_quota.py`가 7개 실패하는 것으로 확인됐다 —
# 프로세스 환경변수가 셀 사이에 남기 때문이다. 그래서 이 환경변수들도 매 테스트
# 시작 시 스냅샷을 찍고 끝나면 정확히 복원한다.
_ENV_KEYS_TO_ISOLATE = (
    "ROUTES_ENABLED",
    "ROUTES_MAX_CALLS_TOTAL",
    "ROUTES_MAX_CALLS_PER_REQUEST",
    "ROUTES_CACHE",
    "GOOGLE_MAPS_API_KEY",
    "GEMINI_API_KEY",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live-api",
        action="store_true",
        default=False,
        help="실제 Google Routes / Gemini API를 호출하는 테스트를 포함한다 (과금 발생).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "live_api: 실제 외부 API를 호출한다. --live-api 없이는 건너뛴다."
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--live-api"):
        return
    skip = pytest.mark.skip(reason="실제 API 호출. --live-api 로 실행하세요.")
    for item in items:
        if "live_api" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _isolate_external_apis(request: pytest.FixtureRequest, monkeypatch):
    """외부 API를 끈 상태로, 그리고 남은 환경변수 없이 테스트한다.

    `live_api` 표시가 붙은 테스트는 예외로 둔다.
    """

    if "live_api" in request.keywords:
        yield
        return

    # 프로세스 환경변수를 먼저 정리한다. `monkeypatch.delenv`는 테스트가 끝나면
    # 원래 값으로 자동 복원하므로, 실제 서버 기동 등으로 셀에 남은 값이 있어도
    # 이 테스트 실행 동안은 항상 같은 상태에서 출발한다.
    for key in _ENV_KEYS_TO_ISOLATE:
        monkeypatch.delenv(key, raising=False)

    from plan_agent import config as config_module
    from plan_agent import quota as quota_module
    from plan_agent import replan
    from plan_agent import routing

    isolated = config_module.CONFIG.__class__(
        **{
            **vars(config_module.CONFIG),
            "google_maps_api_key": "",
            "gemini_api_key": "",
        }
    )
    monkeypatch.setattr(config_module, "CONFIG", isolated)
    monkeypatch.setattr(replan, "CONFIG", isolated)
    monkeypatch.setattr(routing, "CONFIG", isolated)

    # quota.BUDGET은 import 시점에 한 번 생성된 전역 싱글턴이다. 환경변수를
    # 지운 뒤 기본값으로 다시 맞춘다.
    quota_module.BUDGET.reset()
    routing.clear_cache()
    yield
    quota_module.BUDGET.reset()
    routing.clear_cache()
