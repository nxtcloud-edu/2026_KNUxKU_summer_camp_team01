"""canonical JSON Schema를 source tree와 설치 package 양쪽에서 로드한다."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .contracts import SearchToPlanInput

_REPOSITORY_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas"


@lru_cache(maxsize=4)
def load_schema(name: str) -> dict[str, Any]:
    """개발 중에는 저장소 원본을, wheel 설치 후에는 package resource를 읽는다."""

    repository_path = _REPOSITORY_SCHEMA_DIR / name
    if repository_path.is_file():
        with repository_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    resource = files("voyagent_search").joinpath("schemas", name)
    with resource.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_search_to_plan(payload: SearchToPlanInput | dict[str, Any]) -> dict[str, Any]:
    """Pydantic 객체를 wire JSON으로 바꾼 뒤 canonical schema 위반 시 예외를 낸다."""

    data = payload.model_dump(mode="json") if isinstance(payload, SearchToPlanInput) else payload
    validator = Draft202012Validator(load_schema("search-to-plan.schema.json"))
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.absolute_path))
    if errors:
        detail = "; ".join(f"{'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}" for error in errors)
        raise ValueError(f"SearchToPlanInput schema validation failed: {detail}")
    return data
