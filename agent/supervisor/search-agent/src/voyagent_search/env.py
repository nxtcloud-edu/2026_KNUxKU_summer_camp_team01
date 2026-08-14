"""Search Agent의 로컬 환경변수 파일 로딩 지원."""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv


def load_project_environment() -> bool:
    """현재 작업 디렉터리의 상위에서 .env를 찾아 기존 환경변수를 보존하며 로드한다."""

    dotenv_path = find_dotenv(filename=".env", usecwd=True)
    if not dotenv_path:
        return False
    return load_dotenv(dotenv_path=dotenv_path, override=False)
