"""Google Routes API 호출 예산 — 과금을 코드 레벨에서 막는다.

## 왜 코드로 막는가

문서에 "조심해서 쓰자"라고 적는 것만으로는 과금을 막을 수 없다. 루프 한 번
잘못 돌면 수천 번 호출된다. 그래서 **호출 횟수 상한을 코드가 강제**하고,
상한에 닿으면 예외 대신 좌표 기반 추정으로 조용히가 아니라 **로그를 남기고**
넘어간다.

## 세 겹으로 막는다

1. **프로세스 누적 상한** (`ROUTES_MAX_CALLS_TOTAL`)
   서버가 살아있는 동안의 총 호출 수. 무한 루프의 최후 방어선이다.
2. **요청당 상한** (`ROUTES_MAX_CALLS_PER_REQUEST`)
   일정 하나를 만들 때 쓸 수 있는 호출 수. 5일 일정이면 이동 구간이
   20개쯤이므로 기본값 30이면 충분하다.
3. **캐시** (`routing` 모듈)
   같은 구간을 재생성마다 다시 묻지 않는다.

## 기본값을 왜 이렇게 잡았나

Routes API는 월 무료 크레딧이 있고 그 안에서 쓰는 것이 목표다. 기본
`ROUTES_MAX_CALLS_TOTAL=200`은 개발 중 하루 작업량으로는 넉넉하고, 사고가
났을 때 피해는 작은 수준이다. 더 필요하면 `.env`에서 올린다.

`ROUTES_ENABLED=off`로 두면 호출을 아예 하지 않는다. 과금이 전혀 없어야 하는
상황(발표 리허설, CI)에서 쓴다.
"""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s가 정수가 아닙니다(%r). 기본값 %d를 씁니다.", key, raw, default)
        return default


class QuotaExhausted(RuntimeError):
    """호출 상한에 도달했다. 호출부는 추정 폴백으로 넘어가야 한다."""


class CallBudget:
    """Routes API 호출 횟수를 세고 상한을 강제한다. 스레드 안전하다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_used = 0
        self._request_used = 0
        self._blocked_count = 0
        self.reload_limits()

    def reload_limits(self) -> None:
        """`.env` 값을 다시 읽는다. 테스트에서 상한을 바꿀 때도 쓴다."""

        self.enabled = os.getenv("ROUTES_ENABLED", "on").strip().casefold() != "off"
        self.max_total = _env_int("ROUTES_MAX_CALLS_TOTAL", 200)
        self.max_per_request = _env_int("ROUTES_MAX_CALLS_PER_REQUEST", 30)

    # ── 요청 경계 ────────────────────────────────────────────

    def begin_request(self) -> None:
        """일정 생성 요청 하나가 시작될 때 호출한다."""

        with self._lock:
            self._request_used = 0

    def try_consume(self) -> bool:
        """호출 1회를 예산에서 차감한다. 불가능하면 False.

        예외를 던지지 않는 이유: 호출부가 폴백으로 계속 진행해야 하고,
        예산 소진은 오류가 아니라 정상적인 운영 상태다.
        """

        with self._lock:
            if not self.enabled:
                self._blocked_count += 1
                return False
            if self._total_used >= self.max_total:
                self._blocked_count += 1
                if self._blocked_count == 1 or self._blocked_count % 50 == 0:
                    logger.warning(
                        "Routes API 누적 호출 상한(%d)에 도달했습니다. "
                        "이후 이동시간은 좌표 기반 추정을 씁니다. "
                        "필요하면 .env의 ROUTES_MAX_CALLS_TOTAL을 올리세요.",
                        self.max_total,
                    )
                return False
            if self._request_used >= self.max_per_request:
                self._blocked_count += 1
                logger.warning(
                    "이번 요청의 Routes API 호출 상한(%d)에 도달했습니다. "
                    "남은 구간은 좌표 기반 추정을 씁니다.",
                    self.max_per_request,
                )
                return False
            self._total_used += 1
            self._request_used += 1
            return True

    # ── 관측 ─────────────────────────────────────────────────

    @property
    def total_used(self) -> int:
        return self._total_used

    @property
    def request_used(self) -> int:
        return self._request_used

    @property
    def blocked_count(self) -> int:
        return self._blocked_count

    def describe(self) -> str:
        if not self.enabled:
            return "Routes API 호출: 비활성 (ROUTES_ENABLED=off) — 전부 좌표 추정"
        return (
            f"Routes API 호출: 누적 {self._total_used}/{self.max_total}, "
            f"이번 요청 {self._request_used}/{self.max_per_request}, "
            f"예산으로 막힌 호출 {self._blocked_count}건"
        )

    def reset(self) -> None:
        """테스트용. 프로세스 누적까지 초기화한다."""

        with self._lock:
            self._total_used = 0
            self._request_used = 0
            self._blocked_count = 0
        self.reload_limits()


BUDGET = CallBudget()

__all__ = ["BUDGET", "CallBudget", "QuotaExhausted"]
