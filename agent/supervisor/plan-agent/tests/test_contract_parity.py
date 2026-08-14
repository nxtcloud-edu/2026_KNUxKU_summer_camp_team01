"""계약 동일성 회귀 테스트.

이 파일이 지키는 것은 두 가지다.

1. **왕복 동일성** — 입력을 파싱해 다시 내보내면 한 글자도 달라지지 않는다.
   `conformance.mjs`가 Search→Plan과 Plan→Verification의 `trip_info`를
   deepEqual로 비교하므로, 직렬화가 값을 바꾸면 계약이 깨진다.
   (`datetime.time`을 쓰면 `"09:00"` -> `"09:00:00"`이 되어 여기서 걸린다.)

2. **verification-agent와의 판정 동일성** — `opening_hours` 파싱과 휴무일
   판정이 검증 에이전트와 완전히 같아야 한다. 다르면 Plan Agent가
   "통과할 것"이라 판단한 일정이 검증에서 떨어진다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plan_agent import timecalc
from plan_agent.models import PlanToVerificationInput, SearchToPlanInput

def _find_agent_root() -> Path:
    """`schemas/`와 `fixtures/`를 가진 `agent/` 디렉터리를 위로 올라가며 찾는다.

    디렉터리 깊이를 `parents[N]`으로 세면 폴더를 옮길 때마다 조용히 깨진다.
    실제로 이 프로젝트는 `agent/plan-agent`에서 `agent/supervisor/plan-agent`로
    한 번 옮겨졌다. 그래서 구조를 탐색해서 찾는다.
    """

    for candidate in Path(__file__).resolve().parents:
        if (candidate / "schemas").is_dir() and (candidate / "fixtures").is_dir():
            return candidate
    raise RuntimeError("agent 루트(schemas/ + fixtures/)를 찾지 못했습니다")


AGENT_ROOT = _find_agent_root()
FIXTURES = AGENT_ROOT / "fixtures"

# 검증 에이전트는 다른 담당자의 산출물이다. 이 브랜치에 없을 수 있으므로
# 있을 때만 대조한다(있으면 정규식 표류를 잡아준다).
VERIFICATION_RULES = next(
    (
        path
        for path in AGENT_ROOT.rglob("verification_agent/rules.py")
        if path.is_file()
    ),
    AGENT_ROOT / "supervisor" / "verification-agent" / "src" / "verification_agent" / "rules.py",
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ── 1. 왕복 동일성 ────────────────────────────────────────────


def test_search_to_plan_fixture_roundtrips_byte_identical() -> None:
    raw = _load("search-to-plan.example.json")
    parsed = SearchToPlanInput.model_validate(raw)
    assert parsed.model_dump(mode="json") == raw


def test_plan_to_verification_fixture_roundtrips_byte_identical() -> None:
    raw = _load("plan-to-verification.example.json")
    parsed = PlanToVerificationInput.model_validate(raw)
    assert parsed.model_dump(mode="json") == raw


def test_trip_info_is_shared_between_both_handoffs() -> None:
    """conformance.mjs의 cross-handoff 검사와 같은 조건."""
    search = _load("search-to-plan.example.json")
    plan = _load("plan-to-verification.example.json")
    assert search["trip_info"] == plan["trip_info"]

    # 파싱 후에도 동일해야 한다 (직렬화가 값을 바꾸지 않는다).
    parsed_search = SearchToPlanInput.model_validate(search)
    parsed_plan = PlanToVerificationInput.model_validate(plan)
    assert (
        parsed_search.trip_info.model_dump(mode="json")
        == parsed_plan.trip_info.model_dump(mode="json")
    )


def test_time_fields_never_gain_seconds() -> None:
    """`datetime.time`을 썼다면 실패할 테스트.

    이 프로젝트에서 시각을 `str`로 다루는 이유를 고정한다. 기대값을
    하드코딩하지 않고 fixture 원본과 비교한다 — 정본이 바뀌어도 안 깨진다.
    """
    raw = _load("plan-to-verification.example.json")
    parsed = PlanToVerificationInput.model_validate(raw)
    dumped = parsed.model_dump(mode="json")

    # 왕복 후에도 원본 문자열 그대로여야 한다 (초가 붙으면 실패).
    assert dumped["trip_info"]["day_start_time"] == raw["trip_info"]["day_start_time"]
    assert dumped["trip_info"]["day_end_time"] == raw["trip_info"]["day_end_time"]
    for day in dumped["plan"]["days"]:
        for item in day["items"]:
            assert len(item["start_time"]) == 5, item["start_time"]
            assert len(item["end_time"]) == 5, item["end_time"]
            assert ":" in item["start_time"]


# ── 2. 계약 위반은 조용히 통과하지 않는다 ──────────────────────


def test_extra_field_is_rejected() -> None:
    """`additionalProperties: false`에 대응. 모르는 필드를 조용히 버리지 않는다."""
    raw = _load("search-to-plan.example.json")
    raw["selected"]["places"][0]["unexpected_field"] = "x"
    with pytest.raises(Exception):
        SearchToPlanInput.model_validate(raw)


def test_bad_time_format_is_rejected() -> None:
    raw = _load("plan-to-verification.example.json")
    raw["plan"]["days"][0]["items"][0]["start_time"] = "9:00"
    with pytest.raises(Exception):
        PlanToVerificationInput.model_validate(raw)


def test_bad_item_id_is_rejected() -> None:
    """`^d[1-9]\\d*-[1-9]\\d*$` 패턴. `d0-1`이나 `x1-1`은 계약 위반이다."""
    raw = _load("plan-to-verification.example.json")
    for bad_id in ["d0-1", "d1-0", "x1-1", "d1", "1-1"]:
        raw["plan"]["days"][0]["items"][0]["id"] = bad_id
        with pytest.raises(Exception):
            PlanToVerificationInput.model_validate(raw)


# ── 3. verification-agent와 판정 동일성 ────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("06:00-17:00", (360, 1020)),
        ("09:00~18:00", (540, 1080)),
        ("00:00-24:00", (0, 1440)),
        ("체크인 15:00 이후", (900, 1440)),
        ("15:00 이후", (900, 1440)),
        # 아래는 검증 에이전트가 INVALID_OPENING_HOURS로 fail 판정하는 값들.
        ("6:00-17:00", None),  # 한 자리 시각은 인정되지 않는다
        ("화-일 09:30-17:00", None),  # 요일이 섞인 자유 문자열
        ("상시 개방", None),
        ("", None),
    ],
)
def test_opening_hours_parsing_matches_verification_agent(
    value: str, expected: tuple[int, int] | None
) -> None:
    assert timecalc.parse_opening_hours(value) == expected


def test_weekday_is_computed_from_date_not_hardcoded() -> None:
    """2026-06-15는 실제로 월요일이다."""
    assert timecalc.weekday_ko("2026-06-12") == "금요일"
    assert timecalc.weekday_ko("2026-06-13") == "토요일"
    assert timecalc.weekday_ko("2026-06-14") == "일요일"
    assert timecalc.weekday_ko("2026-06-15") == "월요일"
    assert timecalc.weekday_ko("2026-06-16") == "화요일"


def test_closed_day_detection_matches_verification_agent() -> None:
    assert timecalc.is_closed_on("2026-06-15", ["월요일"]) is True
    assert timecalc.is_closed_on("2026-06-15", ["화요일"]) is False
    assert timecalc.is_closed_on("2026-06-15", []) is False
    # rules.py는 첫 글자만 온 경우도 인정한다.
    assert timecalc.is_closed_on("2026-06-15", ["월"]) is True


def test_stay_opening_hours_synthesis_is_parseable() -> None:
    """숙소 항목의 `opening_hours`는 우리가 합성한다.

    검증 에이전트가 파싱할 수 있는 형식이어야 한다. 파싱 실패는
    `INVALID_OPENING_HOURS` fail로 이어진다.
    """
    synthesized = timecalc.format_open_after("15:00")
    assert synthesized == "체크인 15:00 이후"
    assert timecalc.parse_opening_hours(synthesized) == (900, 1440)


@pytest.mark.skipif(
    not VERIFICATION_RULES.exists(),
    reason=(
        "verification-agent는 다른 담당자 소유이며 이 브랜치에 없다. "
        "브랜치가 합쳐지면 이 테스트가 자동으로 활성화되어 정규식 표류를 잡는다."
    ),
)
def test_rules_py_regexes_are_unchanged() -> None:
    """검증 에이전트의 정규식이 바뀌면 이 테스트가 알려준다.

    `timecalc`는 rules.py의 정규식을 복사한 것이므로, 원본이 바뀌면 함께
    바꿔야 한다. 복사본이 조용히 낡는 것을 막는다.
    """
    source = VERIFICATION_RULES.read_text(encoding="utf-8")
    assert r'r"^\s*(\d{2}):(\d{2})\s*[-~–]\s*(\d{2}):(\d{2})\s*$"' in source, (
        "verification-agent의 OPENING_HOURS_PATTERN이 변경되었습니다. "
        "plan_agent/timecalc.py의 복사본도 함께 갱신하세요."
    )
    assert r'r"^\s*(?:체크인\s*)?([01]\d|2[0-3]):([0-5]\d)\s*이후\s*$"' in source, (
        "verification-agent의 OPEN_AFTER_PATTERN이 변경되었습니다. "
        "plan_agent/timecalc.py의 복사본도 함께 갱신하세요."
    )


# ── 4. 시각 산술 경계 ─────────────────────────────────────────


def test_hhmm_rejects_overflow_instead_of_wrapping() -> None:
    """24:00 이상을 조용히 00:00으로 되돌리면 일정이 오전으로 뒤집힌다."""
    assert timecalc.to_hhmm(1439) == "23:59"
    with pytest.raises(ValueError):
        timecalc.to_hhmm(1440)
    with pytest.raises(ValueError):
        timecalc.to_hhmm(-1)


def test_round_up_never_shortens_travel_time() -> None:
    """내림을 쓰면 INSUFFICIENT_TRAVEL_TIME을 유발할 수 있다."""
    assert timecalc.round_up_to_5(0) == 0
    assert timecalc.round_up_to_5(1) == 5
    assert timecalc.round_up_to_5(31) == 35
    assert timecalc.round_up_to_5(35) == 35


def test_day_count_matches_verification_formula() -> None:
    """rules.py: `(end - start).days + 1`"""
    assert timecalc.day_count("2026-06-15", "2026-06-15") == 1
    assert timecalc.day_count("2026-06-12", "2026-06-16") == 5
