from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .ai import judge_human_constraints
from .models import PlanToVerificationInput, VerificationChecks, VerificationResult
from .rules import build_rule_checks
from .state import VerificationState


def _run_rule_checks(state: VerificationState) -> dict[str, VerificationChecks]:
    return {"checks": build_rule_checks(state["payload"])}


async def _run_ai_checks(state: VerificationState) -> dict[str, VerificationChecks]:
    checks = state["checks"]
    if checks is None:
        raise RuntimeError("Rule checks must run before AI checks")

    judgement = await judge_human_constraints(state["payload"])
    return {
        "checks": checks.model_copy(
            update={
                "avoid": judgement.avoid,
                "pace": judgement.pace,
                "walking_level": judgement.walking_level,
                "duration_realism": judgement.duration_realism,
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
        checks.duration_realism.status,
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
    return VerificationResult(possible=state["possible"], checks=checks)
