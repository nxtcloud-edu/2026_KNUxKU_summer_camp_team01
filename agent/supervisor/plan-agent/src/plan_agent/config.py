"""환경 설정. 모든 환경변수를 이 한 곳에서만 읽는다.

`.env`를 찾아 읽되 외부 패키지(python-dotenv)에 의존하지 않는다. 의존성을 하나
줄이는 것보다, **설치를 깜빡해도 `.env`가 동작한다**는 점이 중요하다. 키를
넣었는데 조용히 무시되는 상황을 만들고 싶지 않다.

이미 프로세스 환경에 있는 값은 `.env`가 덮어쓰지 않는다(실제 배포 환경 우선).

## 키가 없을 때의 동작

키가 없으면 서버는 **뜬다.** 대신 해당 기능만 비활성화되고 그 사실이 로그와
산출물 진단에 남는다. 검증 에이전트도 `GEMINI_API_KEY`가 없으면 해당 검사만
`skipped`로 두고 계속 진행한다. 같은 방식을 따른다.

| 없는 키 | 결과 |
|---|---|
| `GOOGLE_MAPS_API_KEY` | 이동시간을 좌표 기반으로 추정한다. 로그에 추정임을 남긴다 |
| `GEMINI_API_KEY` | 배치 순서·이유 문장을 결정론 규칙과 템플릿으로 만든다 |
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# `.env`를 찾을 후보 경로. 위에서부터 처음 발견한 것을 쓴다.
# plan-agent 안, supervisor 안, 저장소 루트 순서로 올라간다. 세 에이전트가
# 키를 공유하므로 상위에 한 벌만 두는 것도 가능하게 한다.
_ENV_FILENAME = ".env"


def _candidate_env_paths() -> list[Path]:
    here = Path(__file__).resolve()
    return [parent / _ENV_FILENAME for parent in here.parents]


def _parse_env_file(path: Path) -> dict[str, str]:
    """아주 단순한 `KEY=VALUE` 파서.

    주석(`#`)과 빈 줄을 무시하고, 값 양쪽의 따옴표를 벗긴다. 여러 줄 값이나
    변수 치환은 지원하지 않는다. 지원하는 척하고 조용히 틀리는 것보다 낫다.
    """

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            logger.warning("%s: '=' 없는 줄을 건너뜁니다: %r", path.name, raw_line)
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def load_env_file() -> Path | None:
    """`.env`를 찾아 프로세스 환경에 넣는다. 이미 있는 값은 덮어쓰지 않는다."""

    for path in _candidate_env_paths():
        if not path.is_file():
            continue
        for key, value in _parse_env_file(path).items():
            os.environ.setdefault(key, value)
        return path
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
        logger.warning("%s 값이 정수가 아닙니다(%r). 기본값 %d를 씁니다.", key, raw, default)
        return default


def _get_float(key: str, default: float) -> float:
    raw = _get(key)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s 값이 숫자가 아닙니다(%r). 기본값 %s를 씁니다.", key, raw, default)
        return default


@dataclass(frozen=True)
class Config:
    """import 시점에 한 번 고정된다. 런타임에 바뀌지 않는다."""

    # ── 서버 ──
    port: int
    log_level: str
    # Plan Agent 자신의 작업 상한. 전체 파이프라인
    # (Search -> Plan -> Verification) 예산은 supervisor가 관리하고,
    # 이 값은 그중 Plan에 할당된 몫이다. 두 곳에서 같은 예산을 해석하지
    # 않도록 변수를 분리해 둔다.
    own_timeout_ms: int

    # ── Google Routes API ──
    google_maps_api_key: str
    routes_timeout_s: float
    routes_cache_enabled: bool

    # ── Gemini (검증 에이전트와 같은 변수명을 쓴다) ──
    gemini_api_key: str
    gemini_model: str
    gemini_temperature: float

    @property
    def has_routes_api(self) -> bool:
        return bool(self.google_maps_api_key)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)


def _build_config() -> Config:
    return Config(
        port=_get_int("PLAN_AGENT_PORT", 8001),
        log_level=_get("LOG_LEVEL", "info").upper(),
        own_timeout_ms=_get_int("PLAN_AGENT_TIMEOUT_MS", 20_000),
        google_maps_api_key=_get("GOOGLE_MAPS_API_KEY"),
        routes_timeout_s=_get_float("ROUTES_TIMEOUT_S", 8.0),
        routes_cache_enabled=_get("ROUTES_CACHE", "on").casefold() != "off",
        gemini_api_key=_get("GEMINI_API_KEY"),
        gemini_model=_get("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_temperature=_get_float("GEMINI_TEMPERATURE", 0.2),
    )


ENV_FILE = load_env_file()
CONFIG = _build_config()


def describe_capabilities() -> list[str]:
    """기동 로그용. 무엇이 켜져 있고 무엇이 추정으로 대체되는지 한눈에 보인다."""

    lines = [
        f".env: {ENV_FILE if ENV_FILE else '없음 (프로세스 환경변수만 사용)'}",
        (
            "Google Routes API: 사용"
            if CONFIG.has_routes_api
            else "Google Routes API: 키 없음 → 좌표 기반 추정으로 대체"
        ),
        (
            f"Gemini: 사용 ({CONFIG.gemini_model})"
            if CONFIG.has_gemini
            else "Gemini: 키 없음 → 결정론 배치 + 템플릿 문장으로 대체"
        ),
    ]
    return lines


__all__ = ["CONFIG", "ENV_FILE", "Config", "describe_capabilities", "load_env_file"]
