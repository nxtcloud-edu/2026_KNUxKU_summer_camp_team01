"""LangGraph 그래프 — 결정론 배치 → LLM 서술 → 최종 검증.

verification-agent의 `graph.py`와 같은 3단 구조다.

    rule_layer   결정론 계층. 배치·시각·예산을 확정한다 (LLM 없음)
        ↓
    narrate      Gemini가 note 문장만 붙인다 (실패하면 템플릿)
        ↓
    finalize     문장을 반영한 뒤 다시 자기 검증한다

## 왜 finalize에서 또 검증하는가

`narrate` 단계가 `note`만 바꾸므로 이론적으로는 검증이 다시 필요 없다.
그런데 "이론적으로 안전하다"는 가정이 깨지는 것이 실제 버그의 대부분이다.
`apply_notes`에 실수가 생겨 다른 필드를 건드리면 검증 에이전트에서 처음
발견되는데, 그때는 원인이 여기라는 걸 알기 어렵다. 그래서 여기서 다시 본다.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from . import ai, contracts
from .models import PlanToVerificationInput, SearchToPlanInput
from .planner import PlanningDiagnostics, build_plan
from .state import PlanState

logger = logging.getLogger(__name__)


def _rule_layer(state: PlanState) -> dict:
    """결정론 계층. LLM 없이 계약을 만족하는 일정을 만든다."""

    result = build_plan(state["source"])
    return {"payload": result.payload, "diagnostics": result.diagnostics}


async def _narrate(state: PlanState) -> dict:
    """Gemini로 배치 이유 문장을 만든다. 실패해도 결과를 살린다."""

    payload = state["payload"]
    if payload is None:
        # 만들 일정이 없으면 문장도 필요 없다.
        return {"narration": None}
    narration = await ai.narrate_plan(payload)
    return {"narration": narration}


def _finalize(state: PlanState) -> dict:
    """문장을 반영하고 마지막으로 자기 검증한다."""

    payload = state["payload"]
    narration = state["narration"]
    diagnostics = state["diagnostics"] or PlanningDiagnostics()

    if payload is None:
        return {"payload": None, "diagnostics": diagnostics}

    if narration is not None:
        narrated = ai.apply_notes(payload, narration)
        # 문장을 붙인 뒤에도 계약을 지키는지 확인한다. note만 바뀌었어야 한다.
        post_violations = contracts.verify_all(narrated, state["source"])
        if post_violations:
            logger.error(
                "문장을 붙인 뒤 위반이 생겼습니다. 문장을 버리고 원본을 유지합니다: %s",
                [violation.code for violation in post_violations],
            )
            diagnostics.notes.append(
                "LLM 문장 적용 후 계약 위반이 발견되어 원본 문장을 유지했습니다."
            )
        else:
            payload = narrated

    return {"payload": payload, "diagnostics": diagnostics}


def build_plan_graph():
    builder = StateGraph(PlanState)
    builder.add_node("rule_layer", _rule_layer)
    builder.add_node("narrate", _narrate)
    builder.add_node("finalize", _finalize)
    builder.add_edge(START, "rule_layer")
    builder.add_edge("rule_layer", "narrate")
    builder.add_edge("narrate", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile()


plan_graph = build_plan_graph()


async def generate_itinerary(
    source: SearchToPlanInput,
) -> tuple[PlanToVerificationInput | None, PlanningDiagnostics]:
    """`SearchToPlanInput`으로 `PlanToVerificationInput`을 만든다."""

    state = await plan_graph.ainvoke(
        {
            "source": source,
            "payload": None,
            "diagnostics": None,
            "narration": None,
        }
    )
    diagnostics = state["diagnostics"] or PlanningDiagnostics()
    return state["payload"], diagnostics


__all__ = ["build_plan_graph", "generate_itinerary", "plan_graph"]
