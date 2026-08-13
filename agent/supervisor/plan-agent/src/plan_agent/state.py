"""LangGraph 상태. verification-agent의 `state.py`와 같은 형태를 따른다."""

from __future__ import annotations

from typing import TypedDict

from .ai import PlanNarration
from .models import PlanToVerificationInput, SearchToPlanInput
from .planner import PlanningDiagnostics


class PlanState(TypedDict):
    """그래프를 흐르는 상태.

    `payload`가 None이면 결정론 계층이 계약을 지키는 일정을 만들 수 없었다는
    뜻이고, 그 이유는 `diagnostics.violations`에 담긴다.
    """

    source: SearchToPlanInput
    payload: PlanToVerificationInput | None
    diagnostics: PlanningDiagnostics | None
    narration: PlanNarration | None


__all__ = ["PlanState"]
