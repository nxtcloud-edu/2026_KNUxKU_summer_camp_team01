"""Pydantic 모델을 Gemini `response_schema`가 받아들이는 형태로 정제한다.

## 실제로 겪은 버그

`google-genai` SDK에 Pydantic 모델을 `response_schema=MyModel`로 바로 넘기면
SDK가 `MyModel.model_json_schema()`를 그대로 Gemini API에 보낸다. Pydantic
v2는 `model_config = ConfigDict(extra="forbid")`를 쓰면 스키마에
`"additionalProperties": false`를 넣는데, **Gemini의 `response_schema`는
OpenAPI 3.0 서브셋만 받아서 이 키를 모른다.**

실제로 이 문제가 발생하면 API가 400을 던진다.

    google.genai.errors.ClientError: 400 INVALID_ARGUMENT.
    Unknown name "additional_properties" at 'generation_config.response_schema'

이 프로젝트는 예외를 잡아 폴백(템플릿 문장 · 빈 재계획 지시)으로 넘어가므로
화면은 안 깨졌지만, **LLM이 사실상 한 번도 성공적으로 호출되지 않은 채
조용히 항상 폴백만 타고 있었다.** 계약 위반은 아니지만 기능이 죽어 있었다는
점에서 조용한 실패의 한 형태다.

## 해결

`model_json_schema()` 결과에서 `additionalProperties` 키를 재귀적으로 제거한
뒤 dict로 `response_schema`에 넘긴다. Pydantic 모델의 `extra="forbid"`
설정(파싱 시 엄격함)은 그대로 유지되고, Gemini에 보내는 스키마만 정제된다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def _strip_additional_properties(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: _strip_additional_properties(value)
            for key, value in node.items()
            if key != "additionalProperties"
        }
    if isinstance(node, list):
        return [_strip_additional_properties(item) for item in node]
    return node


def gemini_response_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Gemini `response_schema`에 안전하게 넘길 수 있는 dict 스키마.

    `model.model_json_schema()`가 만드는 draft 2020-12 스키마에서 Gemini가
    이해하지 못하는 키만 제거한다. `$defs`/`$ref` 구조는 그대로 두는데,
    Gemini가 이 형태(중첩 정의 + 참조)를 실제로 받아들이는지는 여기서
    최종적으로 실제 API 호출로 검증한다(단위 테스트로는 확인 불가).
    """

    return _strip_additional_properties(model.model_json_schema())


__all__ = ["gemini_response_schema"]
