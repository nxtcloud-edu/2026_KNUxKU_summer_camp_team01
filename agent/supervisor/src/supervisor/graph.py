"""Supervisor LangGraph — 하위 에이전트를 순서대로 호출하고 수락 검사한다.

    dispatch_search ──> dispatch_plan ──> accept_plan ──> dispatch_verification
                              │                               │
                         실패 시 재하달(상한 있음)        accept_verification

## supervisor는 직접 일하지 않는다

일정을 만들지도, 검증하지도 않는다. 하는 일은 네 가지다.

1. 하위에 명령을 하달한다
2. 산출물을 **직접** 수락 검사한다 (하위의 자기 보고를 믿지 않는다)
3. 미달이면 재하달한다 (상한 있음)
4. 전체 시간 예산을 배분한다

입력에 `selected`가 있으면 이미 SearchToPlanInput으로 보고 Plan부터 시작한다.
`selected`가 없으면 SearchRequest로 보고 Search Agent를 먼저 호출한다.
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

    source: dict  # SearchRequest 또는 SearchToPlanInput
    plan: dict | None  # PlanToVerificationInput
    verification: dict | None  # {possible, checks, feedback}
    reports: list[AcceptanceReport]
    failures: list[str]
    # 계약 위반으로 산출물을 반송한 횟수 (하위 구현 문제)
    reissue_count: int
    # 검증 실패로 자동 재계획한 횟수 (일정 품질 문제)
    replan_count: int
    # 재계획에 사용한 피드백 프롬프트 이력. 사용자에게 무엇을 고쳤는지 보여준다.
    feedback_history: list[str]
    deadline: float  # time.monotonic() 기준 마감 시각
    on_progress: Any  # ProgressCallback | None


def _remaining_ms(state: SupervisorState) -> int:
    return max(0, int((state["deadline"] - time.monotonic()) * 1000))


def _budget_for(state: SupervisorState, requested_ms: int) -> int:
    """하위 호출에 줄 시간. 남은 전체 예산을 넘지 않는다."""

    return max(1_000, min(requested_ms, _remaining_ms(state)))


def _has_selected_source(state: SupervisorState) -> bool:
    return isinstance(state.get("source"), dict) and "selected" in state["source"]


def _should_plan_after_search(state: SupervisorState) -> str:
    return "create" if _has_selected_source(state) else "finish"


async def _dispatch_search(state: SupervisorState) -> dict:
    """Search Agent에 검색과 선택 결과 생성을 하달한다."""

    if _remaining_ms(state) <= 0:
        return {"failures": state["failures"] + ["전체 시간 예산을 초과했습니다"]}

    try:
        result = await call_agent(
            agent="search",
            url=f"{CONFIG.search_url}/agent/search",
            body=state["source"],
            timeout_ms=_budget_for(state, CONFIG.search_timeout_ms),
            on_progress=state.get("on_progress"),
        )
    except AgentCallFailed as error:
        logger.error("Search Agent 호출 실패: %s", error)
        return {"failures": state["failures"] + [f"search: {error.message}"]}

    return {"source": result.payload}


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


def _should_replan(state: SupervisorState) -> str:
    """검증이 실패했으면 자동으로 한 번 다시 계획한다.

    자동 재계획은 1회다. 그 뒤로는 **사용자가 요청할 때만** 다시 한다.

    자동 루프를 여러 번 돌리지 않는 이유는 같은 제약이면 결과가 크게 달라지지
    않는데 시간과 LLM 비용만 쓰기 때문이다. 사용자가 결과를 보고 판단하는 것이
    낫다. 사용자가 수락하면 그대로 넘어가고, 다시 요청하면 또 계획한다.
    """

    verification = state["verification"]
    if state["plan"] is None or verification is None:
        return "finish"
    if verification.get("possible") is not False:
        return "finish"
    if state["replan_count"] >= CONFIG.auto_replan:
        # 자동 재계획 예산을 다 썼다. 사용자 판단에 맡긴다.
        logger.info(
            "자동 재계획 %d회를 마쳤습니다. 사용자 요청 시 다시 계획합니다.",
            state["replan_count"],
        )
        return "finish"
    if _remaining_ms(state) <= 5_000:
        logger.info("재계획할 시간이 남지 않아 현재 일정으로 마칩니다.")
        return "finish"
    return "replan"


async def _replan(state: SupervisorState) -> dict:
    """검증 피드백을 Plan Agent에 프롬프트로 넘겨 다시 계획한다.

    피드백은 자연어 프롬프트다. Plan Agent 안에서 LLM이 **무엇을 바꿀지**만
    정하고 시각은 결정론 코드가 다시 계산한다.
    """

    feedback = _build_feedback_prompt(state["verification"])
    logger.info("재계획 요청 (%d회): %s", state["replan_count"] + 1, feedback[:120])

    body = dict(state["source"])
    body["_feedback"] = feedback
    body["_previous_plan"] = state["plan"]

    try:
        result = await call_agent(
            agent="plan",
            url=f"{CONFIG.plan_url}/agent/itineraryReplan",
            body=body,
            timeout_ms=_budget_for(state, CONFIG.plan_timeout_ms),
            on_progress=state.get("on_progress"),
        )
    except AgentCallFailed as error:
        logger.warning("재계획 실패: %s. 기존 일정을 유지합니다.", error)
        return {
            "replan_count": state["replan_count"] + 1,
            "failures": state["failures"] + [f"replan: {error.message}"],
        }

    report = check_plan_output(result.payload, state["source"])
    if not report.ok:
        logger.warning(
            "재계획 결과가 수락 검사를 통과하지 못해 기존 일정을 유지합니다: %s",
            report.failures[:3],
        )
        return {
            "plan": state["plan"],
            "replan_count": state["replan_count"] + 1,
            "failures": state["failures"]
            + [f"replan 산출물 계약 위반: {report.failures[0]}"],
            "reports": state["reports"] + [report],
        }

    return {
        "plan": result.payload,
        "replan_count": state["replan_count"] + 1,
        "verification": None,  # 새 일정이므로 다시 검증해야 한다
        "feedback_history": state["feedback_history"] + [feedback],
    }


def _build_feedback_prompt(verification: dict | None) -> str:
    """검증 결과를 자연어 프롬프트로 만든다.

    Plan Agent에 넘어가는 것은 이 문장이다. 구조화 데이터를 그대로 넘기지 않고
    문장으로 만드는 이유는, 그쪽 LLM이 읽어 판단하기 때문이다.

    다만 **숫자는 문장에 그대로 담는다.** "3분 부족"처럼 구체적인 값이 있으면
    LLM이 무엇을 해야 할지 훨씬 정확히 판단한다.
    """

    if not verification:
        return "검증 결과를 받지 못했습니다. 일정을 다시 확인해 주세요."

    feedback = verification.get("feedback", {})
    lines: list[str] = []
    labels = {
        "physical_feasibility": "이동·시간",
        "budget": "예산",
        "operating_hours": "영업시간",
        "daily_schedule": "일정 구조",
        "must_visit": "필수 방문",
        "avoid": "회피 조건",
        "pace": "여행 속도",
        "walking_level": "활동 강도",
    }

    for bucket in ("dangers", "cautions"):
        entries = feedback.get(bucket, []) if isinstance(feedback, dict) else []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            where = ""
            if entry.get("day") is not None:
                where = f"Day {entry['day']}"
            if entry.get("item_id"):
                where += f" ({entry['item_id']})"
            label = labels.get(entry.get("check"), entry.get("check", "검증"))
            line = f"- [{entry.get('level', '')}/{label}] {where}: {entry.get('message', '')}".strip()
            if entry.get("attention"):
                line += f" 확인사항: {entry['attention']}"
            lines.append(line)

    if not lines:
        return (
            "검증에서 실행하기 어렵다고 판단했지만 구체적인 이유를 찾지 못했습니다. "
            "하루 일정을 조금 여유롭게 조정해 주세요."
        )

    return (
        "아래 문제를 해결하도록 일정을 조정해 주세요. "
        "시각은 다시 계산되므로 어느 장소를 어느 날로 옮길지, "
        "어떤 장소를 뺄지만 정해 주세요.\n" + "\n".join(lines)
    )


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
    builder.add_node("dispatch_search", _dispatch_search)
    builder.add_node("dispatch_plan", _dispatch_plan)
    builder.add_node("accept_plan", _accept_plan)
    builder.add_node("reissue", _mark_reissue)
    builder.add_node("dispatch_verification", _dispatch_verification)
    builder.add_node("accept_verification", _accept_verification)

    # 사용자 재요청이면 이미 일정이 있으므로 처음부터 만들지 않는다.
    # 기존 일정을 검증부터 다시 시작해 재계획 경로로 들어간다.
    builder.add_conditional_edges(
        START,
        lambda state: (
            "verify"
            if state.get("plan")
            else "create"
            if _has_selected_source(state)
            else "search"
        ),
        {
            "search": "dispatch_search",
            "create": "dispatch_plan",
            "verify": "dispatch_verification",
        },
    )
    builder.add_conditional_edges(
        "dispatch_search",
        _should_plan_after_search,
        {"create": "dispatch_plan", "finish": END},
    )
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

    # 검증이 실패하면 자동으로 한 번 다시 계획한다.
    # 그 뒤로는 사용자가 요청할 때만 다시 한다 (`run_pipeline`을 다시 호출).
    builder.add_node("replan", _replan)
    builder.add_conditional_edges(
        "accept_verification",
        _should_replan,
        {"replan": "replan", "finish": END},
    )
    builder.add_edge("replan", "dispatch_verification")
    return builder.compile()


supervisor_graph = build_supervisor_graph()


async def run_pipeline(
    source: dict,
    on_progress: ProgressCallback | None = None,
    *,
    previous_plan: dict | None = None,
    user_feedback: str | None = None,
) -> SupervisorState:
    """전체 파이프라인을 실행한다. 전체 시간 예산은 여기서만 정한다.

    ## 사용자 재요청

    사용자가 결과를 보고 "다시 해달라"고 하면 `previous_plan`과 함께 다시
    호출한다. 그러면 그 일정을 기준으로 재계획한다. 횟수 제한이 없다 —
    사용자가 원하는 만큼 할 수 있고, 수락하면 그대로 넘어간다.

    `user_feedback`을 주면 검증 결과 대신 그 문장을 사용한다. 사용자가
    "둘째 날이 너무 빡빡해요"처럼 직접 말한 것을 반영하는 경로다.
    """

    deadline = time.monotonic() + CONFIG.hard_timeout_ms / 1000
    state = await supervisor_graph.ainvoke(
        {
            "source": source,
            "plan": previous_plan,
            "verification": None,
            "reports": [],
            "failures": [],
            "reissue_count": 0,
            # 사용자 재요청이면 자동 재계획 예산을 새로 준다.
            "replan_count": 0,
            "feedback_history": [user_feedback] if user_feedback else [],
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
