"""Supervisor 환경 설정.

plan-agent의 `config.py`와 같은 방식으로 `.env`를 찾아 읽는다. 세 에이전트가
`.env` 한 벌을 공유하므로 파서를 같은 규칙으로 유지한다.

## 시간 예산은 supervisor만 관리한다

전체 파이프라인 상한(`AGENT_HARD_TIMEOUT_MS`)은 **여기서만** 해석한다.
하위 에이전트는 각자 자기 몫(`PLAN_AGENT_TIMEOUT_MS` 등)만 본다. 같은 예산을
두 곳에서 해석하면 어긋나고, 어긋나면 "누가 먼저 끊었는가"를 디버깅하게 된다.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_FILENAME = ".env"


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def load_env_file() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _ENV_FILENAME
        if candidate.is_file():
            for key, value in _parse_env_file(candidate).items():
                os.environ.setdefault(key, value)
            return candidate
    return None


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _get_int(key: str, default: int) -> int:
    raw = _get(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s가 정수가 아닙니다(%r). 기본값 %d.", key, raw, default)
        return default


@dataclass(frozen=True)
class SupervisorConfig:
    port: int
    log_level: str

    # 전체 파이프라인 상한. supervisor만 이 값을 해석한다.
    hard_timeout_ms: int

    # 하위 에이전트 주소
    search_url: str
    plan_url: str
    verification_url: str

    # 하위 호출당 상한
    search_timeout_ms: int
    plan_timeout_ms: int
    verification_timeout_ms: int

    # 수락 검사 실패 시 재하달 횟수 상한.
    # 무한 반송을 막는다. 같은 입력에 같은 결과가 나오면 반복해도 달라지지 않는다.
    max_reissue: int

    @property
    def has_search_agent(self) -> bool:
        return bool(self.search_url)

    @property
    def has_verification_agent(self) -> bool:
        return bool(self.verification_url)


def _build() -> SupervisorConfig:
    plan_port = _get_int("PLAN_AGENT_PORT", 8001)
    search_port = _get_int("SEARCH_AGENT_PORT", 8002)
    verification_port = _get_int("VERIFICATION_AGENT_PORT", 8003)
    return SupervisorConfig(
        port=_get_int("SUPERVISOR_PORT", 8000),
        log_level=_get("LOG_LEVEL", "info").upper(),
        hard_timeout_ms=_get_int("AGENT_HARD_TIMEOUT_MS", 40_000),
        search_url=_get("SEARCH_AGENT_URL", f"http://127.0.0.1:{search_port}"),
        plan_url=_get("PLAN_AGENT_URL", f"http://127.0.0.1:{plan_port}"),
        verification_url=_get(
            "VERIFICATION_AGENT_URL", f"http://127.0.0.1:{verification_port}"
        ),
        search_timeout_ms=_get_int("SEARCH_AGENT_TIMEOUT_MS", 15_000),
        plan_timeout_ms=_get_int("PLAN_AGENT_TIMEOUT_MS", 20_000),
        verification_timeout_ms=_get_int("VERIFICATION_AGENT_TIMEOUT_MS", 15_000),
        max_reissue=_get_int("SUPERVISOR_MAX_REISSUE", 1),
    )


ENV_FILE = load_env_file()
CONFIG = _build()


def describe() -> list[str]:
    return [
        f".env: {ENV_FILE if ENV_FILE else '없음'}",
        f"전체 상한: {CONFIG.hard_timeout_ms}ms",
        f"plan: {CONFIG.plan_url} ({CONFIG.plan_timeout_ms}ms)",
        f"verification: {CONFIG.verification_url} ({CONFIG.verification_timeout_ms}ms)",
        f"search: {CONFIG.search_url} ({CONFIG.search_timeout_ms}ms)",
        f"수락 실패 시 재하달 상한: {CONFIG.max_reissue}회",
    ]


__all__ = ["CONFIG", "ENV_FILE", "SupervisorConfig", "describe", "load_env_file"]
