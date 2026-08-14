"""Pydantic 모델을 Gemini `response_schema`가 받아들이는 형태로 정제한다.

## 실제로 재현·확인한 버그

`google-genai` SDK에 Pydantic 모델을 `response_schema=MyModel`로 바로 넘기면
SDK가 `MyModel.model_json_schema()`를 그대로 Gemini API에 보낸다. `StrictModel`
(`ConfigDict(extra="forbid")`)을 쓰면 스키마에 `"additionalProperties": false`가
들어가는데, **Gemini의 `response_schema`는 OpenAPI 3.0 서브셋만 받아서 이 키를
모른다.** 전체 파이프라인(plan-agent + verification-agent + supervisor)을 실제
서버 3개로 띄워 end-to-end 테스트하는 과정에서 아래 오류로 재현했다.

    google.genai.errors.ClientError: 400 INVALID_ARGUMENT.
    Unknown name "additional_properties" at 'generation_config.response_schema'

예외는 잡혀서 `skipped` 판정으로 폴백되므로 화면은 깨지지 않지만, **AI 판단
(avoid/pace/walking_level)이 키가 있어도 항상 실패해 사실상 죽어 있었다.**

## 해결

`model_json_schema()`에서 `additionalProperties`를 재귀적으로 제거한 dict를
`response_schema`에 넘긴다. 모델의 `extra="forbid"`(입력 파싱 시 엄격함)는
그대로 유지되고, Gemini에 보내는 스키마만 정제된다.
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
    """Gemini `response_schema`에 안전하게 넘길 수 있는 dict 스키마."""

    return _strip_additional_properties(model.model_json_schema())


__all__ = ["gemini_response_schema"]
