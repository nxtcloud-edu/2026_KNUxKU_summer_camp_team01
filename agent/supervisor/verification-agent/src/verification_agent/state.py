from __future__ import annotations

from typing import TypedDict

from .models import PlanToVerificationInput, VerificationChecks


class VerificationState(TypedDict):
    payload: PlanToVerificationInput
    checks: VerificationChecks | None
    possible: bool
