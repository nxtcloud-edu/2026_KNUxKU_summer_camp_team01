from __future__ import annotations

import os

from langgraph.graph import END, START, StateGraph

from .ai import judge_human_constraints
from .models import (
    AvoidCheck,
    PlanToVerificationInput,
    StandardCheck,
    VerificationChecks,
    VerificationFeedback,
    VerificationFinding,
    VerificationResult,
)
from .rules import build_rule_checks
from .state import VerificationState


CAUTION_ATTENTION = {
    "physical_feasibility": "장소 사이 이동시간과 다음 일정 시작 시각을 다시 확인하세요.",
    "operating_hours": "방문 날짜와 실제 영업시간을 다시 확인하세요.",
    "daily_schedule": "하루 시작·종료 범위 안에서 일정 시간을 조정하세요.",
    "pace": "방문지를 줄이거나 일정 사이에 여유 시간을 확보하세요.",
    "walking_level": "도보 구간을 줄이거나 대중교통·택시 이용을 고려하세요.",
}


def _standard_feedback(
    check_name: str,
    check: StandardCheck,
) -> list[VerificationFinding]:
    if check.status not in {"warning", "fail"}:
        return []
    level = "위험" if check.status == "fail" else "주의"
    attention = CAUTION_ATTENTION.get(check_name) if level == "주의" else None
    return [
        VerificationFinding(
            level=level,
            check=check_name,
            code=issue.code,
            message=issue.message,
            attention=attention,
            day=issue.day,
            item_id=issue.item_id,
        )
        for issue in check.issues
    ]


def _build_feedback(checks: VerificationChecks) -> VerificationFeedback:
    items: list[VerificationFinding] = []
    for check_name, check in (
        ("physical_feasibility", checks.physical_feasibility),
        ("operating_hours", checks.operating_hours),
        ("daily_schedule", checks.daily_schedule),
        ("pace", checks.pace),
        ("walking_level", checks.walking_level),
    ):
        items.extend(_standard_feedback(check_name, check))

    if checks.budget.status == "fail":
        items.append(
            VerificationFinding(
                level="위험",
                check="budget",
                code="BUDGET_EXCEEDED",
                message=(
                    f"예상 비용이 예산을 {checks.budget.over_by:g} "
                    f"{checks.budget.currency} 초과합니다."
                ),
            )
        )

    for missing in checks.must_visit.missing:
        items.append(
            VerificationFinding(
                level="위험",
                check="must_visit",
                code="MISSING_MUST_VISIT",
                message=f"필수 방문지 '{missing}'이 일정에 없습니다.",
            )
        )

    if checks.avoid.status in {"warning", "fail"}:
        level = "위험" if checks.avoid.status == "fail" else "주의"
        for match in checks.avoid.matched:
            items.append(
                VerificationFinding(
                    level=level,
                    check="avoid",
                    code="AVOID_CONFLICT",
                    message=match.message,
                    attention=(
                        f"회피 조건 '{match.avoid}'과 충돌할 수 있으니 해당 일정을 확인하세요."
                        if level == "주의"
                        else None
                    ),
                    day=match.day,
                    item_id=match.item_id,
                )
            )

    return VerificationFeedback(
        cautions=[item for item in items if item.level == "주의"],
        dangers=[item for item in items if item.level == "위험"],
    )


def _run_rule_checks(state: VerificationState) -> dict[str, VerificationChecks]:
    return {"checks": build_rule_checks(state["payload"])}


def _prefer_ai(ai_check, rule_check):
    if ai_check.status == "skipped":
        return rule_check
    if isinstance(ai_check, AvoidCheck):
        if ai_check.status in {"warning", "fail"} and not ai_check.matched:
            return rule_check
    if isinstance(ai_check, StandardCheck):
        if ai_check.status in {"warning", "fail"} and not ai_check.issues:
            return rule_check
    return ai_check


def _strict_facts_enabled() -> bool:
    return os.getenv("STRICT_FACTS", "true").strip().casefold() not in {
        "0",
        "false",
        "off",
        "no",
    }


async def _run_ai_checks(state: VerificationState) -> dict[str, VerificationChecks]:
    checks = state["checks"]
    if checks is None:
        raise RuntimeError("Rule checks must run before AI checks")

    if _strict_facts_enabled():
        return {"checks": checks}

    judgement = await judge_human_constraints(state["payload"])
    return {
        "checks": checks.model_copy(
            update={
                "avoid": _prefer_ai(judgement.avoid, checks.avoid),
                "pace": _prefer_ai(judgement.pace, checks.pace),
                "walking_level": _prefer_ai(
                    judgement.walking_level, checks.walking_level
                ),
            },
            deep=True,
        )
    }


def _finalize(state: VerificationState) -> dict[str, bool]:
    checks = state["checks"]
    if checks is None:
        raise RuntimeError("Checks are missing at finalization")

    statuses = (
        checks.physical_feasibility.status,
        checks.budget.status,
        checks.operating_hours.status,
        checks.daily_schedule.status,
        checks.must_visit.status,
        checks.avoid.status,
        checks.pace.status,
        checks.walking_level.status,
    )
    return {"possible": "fail" not in statuses}


def build_verification_graph():
    builder = StateGraph(VerificationState)
    builder.add_node("rule_checks", _run_rule_checks)
    builder.add_node("ai_checks", _run_ai_checks)
    builder.add_node("finalize", _finalize)

    builder.add_edge(START, "rule_checks")
    builder.add_edge("rule_checks", "ai_checks")
    builder.add_edge("ai_checks", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile()


verification_graph = build_verification_graph()


async def verify_plan(payload: PlanToVerificationInput) -> VerificationResult:
    state = await verification_graph.ainvoke(
        {"payload": payload, "checks": None, "possible": True}
    )
    checks = state["checks"]
    if checks is None:
        raise RuntimeError("Verification graph returned no checks")
    return VerificationResult(
        possible=state["possible"],
        checks=checks,
        feedback=_build_feedback(checks),
    )
