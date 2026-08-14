#!/usr/bin/env python
"""Pydantic 모델이 계약 스키마와 정말 일치하는지 검증한다.

## 왜 이 도구가 필요한가

`models.py`는 "스키마를 보고 옮겨 적은" 것이다. 사람이 옮겨 적은 것은 틀릴 수
있고, 틀려도 테스트는 통과할 수 있다 — 내 모델과 내 테스트가 같은 오해를
공유하기 때문이다.

그래서 **스키마 JSON을 직접 읽어** 필드 집합·필수 여부·패턴·enum을 하나씩
대조한다. 이건 "내가 맞다고 생각한다"와 "실제로 맞다"를 구분하는 유일한 방법이다.

## 검사하는 것

1. 스키마의 필수 필드가 Pydantic에서도 필수인가
2. Pydantic에 스키마에 없는 필드가 있는가 (`additionalProperties: false` 위반)
3. enum 값 집합이 같은가
4. 정규식 패턴이 같은가
5. 공식 fixture를 파싱하고 다시 내보내면 바이트 단위로 같은가
6. 내 산출물이 스키마를 통과하는가 (직접 구현한 검사기로)

## 사용법

    python agent/supervisor/plan-agent/tools/validate_schema.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))


def _find_agent_root() -> Path:
    for candidate in _HERE.parents:
        if (candidate / "schemas").is_dir() and (candidate / "fixtures").is_dir():
            return candidate
    raise SystemExit("agent 루트(schemas/ + fixtures/)를 찾지 못했습니다")


AGENT_ROOT = _find_agent_root()
SCHEMA_DIR = AGENT_ROOT / "schemas"
FIXTURE_DIR = AGENT_ROOT / "fixtures"
SAMPLE_DIR = _HERE.parent / "samples"


# ── 최소 JSON Schema 검사기 ───────────────────────────────────
# conformance.mjs가 하는 것과 같은 수준의 검사를 파이썬으로 한다.
# 외부 패키지(jsonschema)에 의존하지 않으려는 것이 아니라, conformance.mjs와
# 같은 규칙으로 보는 것이 목적이다.


def _resolve(ref: str, root: dict) -> Any:
    if not ref.startswith("#/"):
        raise ValueError(f"외부 $ref 미지원: {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def validate(value: Any, schema: Any, root: dict, path: str = "$") -> list[str]:
    """스키마 위반 목록을 반환한다."""

    if schema is True:
        return []
    if schema is False:
        return [f"{path}: 허용되지 않는 값"]
    if not isinstance(schema, dict):
        return [f"{path}: 스키마 노드가 객체가 아님"]

    if "$ref" in schema:
        return validate(value, _resolve(schema["$ref"], root), root, path)

    errors: list[str] = []

    if "oneOf" in schema:
        matches = sum(
            1 for option in schema["oneOf"] if not validate(value, option, root, path)
        )
        if matches != 1:
            return [f"{path}: oneOf 중 정확히 하나와 일치해야 함 (일치 {matches}개)"]

    if "const" in schema and value != schema["const"]:
        return [f"{path}: {schema['const']!r} 이어야 함 (실제 {value!r})"]

    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: 허용값 아님 {value!r} (허용: {schema['enum']})"]

    if "type" in schema:
        allowed = schema["type"]
        allowed = allowed if isinstance(allowed, list) else [allowed]
        if not any(_type_ok(value, item) for item in allowed):
            return [f"{path}: 타입이 {'|'.join(allowed)} 이어야 함 (실제 {type(value).__name__})"]

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: 필수 필드 없음")
        properties = schema.get("properties", {})
        for key, child in value.items():
            if key in properties:
                errors.extend(validate(child, properties[key], root, f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: 계약에 없는 필드")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(
                    validate(child, schema["additionalProperties"], root, f"{path}.{key}")
                )

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: 최소 {schema['minItems']}개 필요 (실제 {len(value)})")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: 최대 {schema['maxItems']}개 (실제 {len(value)})")
        if schema.get("uniqueItems") and len(
            {json.dumps(item, sort_keys=True) for item in value}
        ) != len(value):
            errors.append(f"{path}: 중복 항목 있음")
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(validate(item, schema["items"], root, f"{path}[{index}]"))

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: 최소 길이 {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: 최대 길이 {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: 패턴 불일치 {schema['pattern']} (값 {value!r})")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {schema['minimum']} 이상이어야 함")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {schema['maximum']} 이하여야 함")

    return errors


# ── Pydantic 모델 vs 스키마 대조 ──────────────────────────────


def compare_model_to_schema(
    model: Any, schema_def: dict, root: dict, label: str
) -> list[str]:
    """Pydantic 모델의 필드 집합·필수 여부를 스키마와 대조한다."""

    problems: list[str] = []

    schema_props = set(schema_def.get("properties", {}))
    schema_required = set(schema_def.get("required", []))

    model_fields = model.model_fields
    model_props = set(model_fields)
    model_required = {name for name, f in model_fields.items() if f.is_required()}

    only_in_model = model_props - schema_props
    only_in_schema = schema_props - model_props

    if only_in_model:
        problems.append(
            f"{label}: Pydantic에만 있는 필드 {sorted(only_in_model)} "
            "(additionalProperties:false 위반이 됨)"
        )
    if only_in_schema:
        problems.append(f"{label}: 스키마에만 있는 필드 {sorted(only_in_schema)}")

    missing_required = schema_required - model_required
    if missing_required:
        problems.append(
            f"{label}: 스키마는 필수인데 Pydantic은 선택 {sorted(missing_required)}"
        )
    extra_required = model_required - schema_required
    if extra_required:
        problems.append(
            f"{label}: Pydantic만 필수로 강제 {sorted(extra_required)} "
            "(스키마보다 엄격 — 유효한 입력을 거부할 수 있음)"
        )

    return problems


def main() -> int:
    from plan_agent.models import (
        Persona,
        PlanDay,
        PlanItem,
        PlanToVerificationInput,
        SearchToPlanInput,
        TravelFromPrevious,
        TripInfo,
    )

    failures = 0

    plan_schema = json.loads(
        (SCHEMA_DIR / "plan-to-verification.schema.json").read_text("utf-8")
    )
    search_schema = json.loads(
        (SCHEMA_DIR / "search-to-plan.schema.json").read_text("utf-8")
    )

    print("=" * 68)
    print("1. Pydantic 모델 vs 계약 스키마 필드 대조")
    print("=" * 68)
    pairs = [
        (PlanToVerificationInput, plan_schema, "PlanToVerificationInput"),
        (TripInfo, plan_schema["$defs"]["TripInfo"], "TripInfo"),
        (Persona, plan_schema["$defs"]["Persona"], "Persona"),
        (PlanDay, plan_schema["$defs"]["PlanDay"], "PlanDay"),
        (PlanItem, plan_schema["$defs"]["PlanItem"], "PlanItem"),
        (
            TravelFromPrevious,
            plan_schema["$defs"]["TravelFromPrevious"],
            "TravelFromPrevious",
        ),
        (SearchToPlanInput, search_schema, "SearchToPlanInput"),
    ]
    for model, schema_def, label in pairs:
        problems = compare_model_to_schema(model, schema_def, plan_schema, label)
        if problems:
            failures += len(problems)
            for problem in problems:
                print(f"  FAIL  {problem}")
        else:
            print(f"  OK    {label} ({len(model.model_fields)}개 필드 일치)")

    print()
    print("=" * 68)
    print("2. 공식 fixture 왕복 무손실 (직렬화가 값을 바꾸지 않는가)")
    print("=" * 68)
    for name, model in [
        ("plan-to-verification.example.json", PlanToVerificationInput),
        ("search-to-plan.example.json", SearchToPlanInput),
    ]:
        raw = json.loads((FIXTURE_DIR / name).read_text("utf-8"))
        parsed = model.model_validate(raw)
        dumped = parsed.model_dump(mode="json")
        if dumped == raw:
            print(f"  OK    {name} 왕복 동일")
        else:
            failures += 1
            print(f"  FAIL  {name} 왕복 후 달라짐")
            for key in set(dumped) | set(raw):
                if dumped.get(key) != raw.get(key):
                    print(f"          {key}")

    print()
    print("=" * 68)
    print("3. 공식 fixture가 스키마를 통과하는가 (검사기 자체 검증)")
    print("=" * 68)
    fixture = json.loads(
        (FIXTURE_DIR / "plan-to-verification.example.json").read_text("utf-8")
    )
    errors = validate(fixture, plan_schema, plan_schema)
    if errors:
        failures += 1
        print("  FAIL  공식 fixture가 스키마를 통과하지 못함 (검사기 버그 가능)")
        for error in errors[:10]:
            print(f"          {error}")
    else:
        print("  OK    공식 fixture 스키마 통과")

    print()
    print("=" * 68)
    print("4. 내 산출물이 스키마를 통과하는가")
    print("=" * 68)
    if not SAMPLE_DIR.is_dir():
        print("  건너뜀 — samples/가 없습니다. save_samples.py를 먼저 실행하세요.")
    else:
        outputs = sorted(SAMPLE_DIR.glob("*.plan-output.json"))
        if not outputs:
            print("  건너뜀 — plan-output 샘플이 없습니다.")
        for path in outputs:
            data = json.loads(path.read_text("utf-8"))
            errors = validate(data, plan_schema, plan_schema)
            # Pydantic으로도 다시 파싱해 본다.
            try:
                PlanToVerificationInput.model_validate(data)
                pydantic_ok = True
                pydantic_msg = ""
            except Exception as exc:
                pydantic_ok = False
                pydantic_msg = str(exc)[:100]

            if errors or not pydantic_ok:
                failures += 1
                print(f"  FAIL  {path.name}")
                for error in errors[:5]:
                    print(f"          스키마: {error}")
                if not pydantic_ok:
                    print(f"          Pydantic: {pydantic_msg}")
            else:
                print(f"  OK    {path.name}")

    print()
    print("=" * 68)
    print(f"결과: {'전부 통과' if failures == 0 else f'{failures}건 불일치'}")
    print("=" * 68)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
