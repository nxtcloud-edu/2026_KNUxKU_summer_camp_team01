"""프로세스 환경에 `.env`를 채워 넣는다.

## 실제로 겪은 버그

이 서비스를 실제 서버로 띄워 전체 파이프라인을 검증하는 과정에서
`GEMINI_API_KEY`가 저장소 루트 `.env`에 실제로 존재하는데도
`judge_human_constraints`가 항상 `AI_NOT_CONFIGURED`(키 없음)로 skip됐다.

원인은 이 서비스가 `os.getenv`만 쓰고 `.env` 파일을 읽는 코드가 없었기
때문이다. plan-agent는 상위 디렉터리를 탐색해 `.env`를 읽는 로더가 있는데
verification-agent에는 없어서, **키가 있어도 "없다"고 판단하는 조용한
실패**였다.

plan-agent의 `config.py`와 같은 규칙으로 상위 디렉터리를 탐색한다. 이미 있는
환경변수는 덮어쓰지 않는다(실제 배포 환경이 우선한다).
"""

from __future__ import annotations

import logging
import os
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
    """`.env`를 찾아 프로세스 환경에 넣는다. 이미 있는 값은 덮어쓰지 않는다."""

    for parent in Path(__file__).resolve().parents:
        candidate = parent / _ENV_FILENAME
        if candidate.is_file():
            for key, value in _parse_env_file(candidate).items():
                os.environ.setdefault(key, value)
            return candidate
    return None


ENV_FILE = load_env_file()

__all__ = ["ENV_FILE", "load_env_file"]
