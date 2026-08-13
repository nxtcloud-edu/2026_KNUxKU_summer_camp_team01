"""Supervisor LangGraph — 하위 에이전트를 순서대로 호출하고 수락 검사한다.

    dispatch_plan ──> accept_plan ──> dispatch_verification ──> accept_verification
                          │                                            │
                     실패 시 재하달(상한 있음)                    실패 시 보고

## supervisor는 직접 일하지 않는다

일정을 만들지도, 검증하지도 않는다. 하는 일은 네 가지다.

1. 하위에 명령을 하달한다
2. 산출물을 **직접** 수락 검사한다 (하위의 자기 보고를 믿지 않는다)
3. 미달이면 재하달한다 (상한 있음)
4. 전체 시간 예산을 배분한다

Search Agent는 아직 다른 담당자가 만들고 있다. 그래서 현재 그래프는
`SearchToPlanInput`을 **입력으로 받는다**. Search가 붙으면 그 앞에
`dispatch_search` 노드를 추가한다.
"""

from __future__ import annotations

import logging
import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .acceptance import (
    AcceptanceReport,
    check_plan_output,
    check_verification_output,
)
from .clients import AgentCallFailed, ProgressCallback, call_agent
from .config import CONFIG

logger = logging.getLogger(__name__)


class SupervisorState(TypedDict):
    """그래프를 흐르는 상태."""

    source: dict  # SearchToPlanInput
    plan: dict | None  # PlanToVerificationInput
    verification: dict | None  # {possible, checks}
    reports: list[AcceptanceReport]
    failures: list[str]
    reissue_count: int
    deadline: float  # time.monotonic() 기준 마감 시각
    on_progress: Any  # ProgressCallback | None


def _remaining_ms(state: SupervisorState) -> int:
    return max(0, int((state["deadline"] - time.monotonic()) * 1000))


def _budget_for(state: SupervisorState, requested_ms: int) -> int:
    """하위 호출에 줄 시간. 남은 전체 예산을 넘지 않는다."""

    return max(1_000, min(requested_ms, _remaining_ms(state)))


async def _dispatch_plan(state: SupervisorState) -> dict:
    """Plan Agent에 일정 생성을 하달한다."""

    if _remaining_ms(state) <= 0:
        return {"failures": state["failures"] + ["전체 시간 예산을 초과했습니다"]}

    try:
        result = await call_agent(
            agent="plan",
            url=f"{CONFIG.plan_url}/agent/itineraryGenerate",
            body=state["source"],
            timeout_ms=_budget_for(state, CONFIG.plan_timeout_ms),
            on_progress=state.get("on_progress"),
        )
    except AgentCallFailed as error:
        logger.error("Plan Agent 호출 실패: %s", error)
        return {"failures": state["failures"] + [f"plan: {error.message}"]}

    return {"plan": result.payload}


def _accept_plan(state: SupervisorState) -> dict:
    """Plan 산출물을 supervisor가 직접 검사한다."""

    if state["plan"] is None:
        return {}

    report = check_plan_output(state["plan"], state["source"])
    logger.info(report.summary())
    for failure in report.failures:
        logger.warning("plan 수락 실패: %s", failure)

    updates: dict = {"reports": state["reports"] + [report]}
    if not report.ok:
        # 수락 실패한 산출물은 다음 단계로 넘기지 않는다. 검증 에이전트에
        # 깨진 입력을 주면 거기서 또 실패해 원인이 흐려진다.
        updates["plan"] = None
        updates["failures"] = state["failures"] + [
            f"plan 산출물 계약 위반 {len(report.failures)}건: {report.failures[0]}"
        ]
    return updates


def _should_reissue(state: SupervisorState) -> str:
    """수락 실패 시 재하달할지 결정한다."""

    if state["plan"] is not None:
        return "verify"
    if state["reissue_count"] < CONFIG.max_reissue and _remaining_ms(state) > 3_000:
        return "reissue"
    return "finish"


def _mark_reissue(state: SupervisorState) -> dict:
    logger.info(
        "Plan Agent에 재하달합니다 (%d/%d)",
        state["reissue_count"] + 1,
        CONFIG.max_reissue,
    )
    return {
        "reissue_count": state["reissue_count"] + 1,
        # 재하달이므로 이전 실패 기록은 남기고 plan만 비운다.
        "failures": state["failures"],
    }


async def _dispatch_verification(state: SupervisorState) -> dict:
    """Verification Agent에 검증을 하달한다.

    검증 에이전트가 없어도 파이프라인은 끝난다. 일정은 이미 만들어졌고,
    검증이 없다는 사실을 보고하면 된다. 여기서 죽으면 사용자는 일정조차
    받지 못한다.
    """

    if state["plan"] is None:
        return {}
    if _remaining_ms(state) <= 1_000:
        return {
            "failures": state["failures"]
            + ["검증할 시간이 남지 않아 건너뛰었습니다"]
        }

    try:
        result = await call_agent(
            agent="verification",
            url=f"{CONFIG.verification_url}/agent/itineraryVerify",
            body=state["plan"],
            timeout_ms=_budget_for(state, CONFIG.verification_timeout_ms),
            on_progress=state.get("on_progress"),
        )
    except AgentCallFailed as error:
        logger.warning("Verification Agent 호출 실패: %s", error)
        return {
            "failures": state["failures"] + [f"verification: {error.message}"]
        }

    return {"verification": result.payload}


def _accept_verification(state: SupervisorState) -> dict:
    if state["verification"] is None:
        return {}

    report = check_verification_output(state["verification"])
    logger.info(report.summary())
    for failure in report.failures:
        logger.warning("verification 수락 실패: %s", failure)

    updates: dict = {"reports": state["reports"] + [report]}
    if not report.ok:
        updates["verification"] = None
        updates["failures"] = state["failures"] + [
            f"verification 산출물 계약 위반: {report.failures[0]}"
        ]
    return updates


def build_supervisor_graph():
    builder = StateGraph(SupervisorState)
    builder.add_node("dispatch_plan", _dispatch_plan)
    builder.add_node("accept_plan", _accept_plan)
    builder.add_node("reissue", _mark_reissue)
    builder.add_node("dispatch_verification", _dispatch_verification)
    builder.add_node("accept_verification", _accept_verification)

    builder.add_edge(START, "dispatch_plan")
    builder.add_edge("dispatch_plan", "accept_plan")
    builder.add_conditional_edges(
        "accept_plan",
        _should_reissue,
        {
            "verify": "dispatch_verification",
            "reissue": "reissue",
            "finish": END,
        },
    )
    builder.add_edge("reissue", "dispatch_plan")
    builder.add_edge("dispatch_verification", "accept_verification")
    builder.add_edge("accept_verification", END)
    return builder.compile()


supervisor_graph = build_supervisor_graph()


async def run_pipeline(
    source: dict, on_progress: ProgressCallback | None = None
) -> SupervisorState:
    """전체 파이프라인을 실행한다. 전체 시간 예산은 여기서만 정한다."""

    deadline = time.monotonic() + CONFIG.hard_timeout_ms / 1000
    state = await supervisor_graph.ainvoke(
        {
            "source": source,
            "plan": None,
            "verification": None,
            "reports": [],
            "failures": [],
            "reissue_count": 0,
            "deadline": deadline,
            "on_progress": on_progress,
        }
    )
    return state


__all__ = [
    "SupervisorState",
    "build_supervisor_graph",
    "run_pipeline",
    "supervisor_graph",
]
