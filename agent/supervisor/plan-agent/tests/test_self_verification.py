"""자기 검증기가 검증 에이전트와 같은 판정을 내리는지 확인한다.

정상 fixture를 통과시키는 것만으로는 부족하다. **일부러 위반을 심어서 실제로
잡히는지**까지 확인해야 검증기가 살아있다고 말할 수 있다. 통과만 확인하면
`return []`으로 바꿔도 테스트가 녹색이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plan_agent import budget, contracts
from plan_agent.models import PlanToVerificationInput, SearchToPlanInput


def _find_agent_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "schemas").is_dir() and (candidate / "fixtures").is_dir():
            return candidate
    raise RuntimeError("agent 루트를 찾지 못했습니다")


FIXTURES = _find_agent_root() / "fixtures"


def _search() -> dict:
    return json.loads((FIXTURES / "search-to-plan.example.json").read_text("utf-8"))


def _plan() -> dict:
    return json.loads(
        (FIXTURES / "plan-to-verification.example.json").read_text("utf-8")
    )


def _verify(plan_raw: dict, search_raw: dict | None = None):
    payload = PlanToVerificationInput.model_validate(plan_raw)
    source = SearchToPlanInput.model_validate(search_raw) if search_raw else None
    return contracts.verify_all(payload, source)


def _codes(violations) -> set[str]:
    return {violation.code for violation in violations}


# ── 정상 fixture는 통과한다 ────────────────────────────────────


def test_official_fixture_passes_all_checks() -> None:
    violations = _verify(_plan(), _search())
    assert violations == [], [v.model_dump() for v in violations]


def test_input_fixture_is_usable() -> None:
    payload = SearchToPlanInput.model_validate(_search())
    assert contracts.check_input_usable(payload) == []


# ── 각 규칙이 실제로 위반을 잡는다 ────────────────────────────


def test_detects_duration_mismatch() -> None:
    raw = _plan()
    first = raw["plan"]["days"][0]["items"][0]
    # 실제 시간과 다른 값을 넣는다. fixture 값에 의존하지 않는다.
    first["expected_duration_min"] = first["expected_duration_min"] + 15
    assert "DURATION_MISMATCH" in _codes(_verify(raw))


def test_detects_insufficient_travel_time() -> None:
    raw = _plan()
    # 두 번째 항목의 시작을 이전 종료 시각과 같게 만들고 이동시간을 크게 준다.
    day = raw["plan"]["days"][0]
    previous, item = day["items"][0], day["items"][1]
    item["travel_from_prev"] = {
        "mode": "지하철",
        "estimated_min": 60,
        "distance_km": 10.0,
    }
    item["start_time"] = previous["end_time"]
    start_h, start_m = map(int, previous["end_time"].split(":"))
    end_minutes = start_h * 60 + start_m + item["expected_duration_min"]
    item["end_time"] = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
    assert "INSUFFICIENT_TRAVEL_TIME" in _codes(_verify(raw))


def test_detects_first_item_with_travel() -> None:
    raw = _plan()
    raw["plan"]["days"][0]["items"][0]["travel_from_prev"] = {
        "mode": "대중교통",
        "estimated_min": 10,
        "distance_km": 1.0,
    }
    assert "INVALID_FIRST_TRAVEL" in _codes(_verify(raw))


def test_detects_missing_travel_on_later_item() -> None:
    raw = _plan()
    raw["plan"]["days"][0]["items"][1]["travel_from_prev"] = None
    assert "MISSING_TRAVEL" in _codes(_verify(raw))


def test_detects_closed_day() -> None:
    """그 날짜의 실제 요일을 계산해 휴무일로 심는다.

    요일을 하드코딩하면 fixture 날짜가 바뀔 때 조용히 무의미해진다.
    """
    from plan_agent import timecalc

    raw = _plan()
    day = raw["plan"]["days"][0]
    day["items"][0]["closed_days"] = [timecalc.weekday_ko(day["date"])]
    assert "CLOSED_DAY" in _codes(_verify(raw))


def test_detects_unparseable_opening_hours() -> None:
    raw = _plan()
    raw["plan"]["days"][0]["items"][0]["opening_hours"] = "화-일 09:30-17:00"
    assert "INVALID_OPENING_HOURS" in _codes(_verify(raw))


def test_detects_before_opening() -> None:
    raw = _plan()
    item = raw["plan"]["days"][0]["items"][0]
    item["opening_hours"] = "10:00-17:00"  # 09:00 시작이므로 위반
    assert "BEFORE_OPENING" in _codes(_verify(raw))


def test_detects_after_closing() -> None:
    raw = _plan()
    item = raw["plan"]["days"][0]["items"][0]
    item["opening_hours"] = "06:00-10:00"  # 10:30 종료이므로 위반
    assert "AFTER_CLOSING" in _codes(_verify(raw))


def test_detects_before_day_start() -> None:
    raw = _plan()
    item = raw["plan"]["days"][0]["items"][0]
    item["start_time"] = "08:00"  # day_start_time 09:00
    item["end_time"] = "09:30"
    assert "BEFORE_DAY_START" in _codes(_verify(raw))


def test_detects_after_day_end() -> None:
    raw = _plan()
    item = raw["plan"]["days"][0]["items"][-1]
    item["start_time"] = "22:00"  # day_end_time 22:00
    item["end_time"] = "22:30"
    item["expected_duration_min"] = 30
    assert "AFTER_DAY_END" in _codes(_verify(raw))


def test_detects_duplicate_item_id() -> None:
    raw = _plan()
    raw["plan"]["days"][0]["items"][1]["id"] = raw["plan"]["days"][0]["items"][0]["id"]
    assert "DUPLICATE_ITEM_ID" in _codes(_verify(raw))


def test_detects_day_count_mismatch() -> None:
    """days 개수와 날짜 범위가 어긋나면 잡는다."""
    from plan_agent import timecalc

    raw = _plan()
    # 종료일을 하루 늘리면 days가 하나 부족해진다.
    raw["trip_info"]["end_date"] = timecalc.add_days(raw["trip_info"]["end_date"], 1)
    assert "DAY_COUNT_MISMATCH" in _codes(_verify(raw))


def test_detects_missing_must_visit() -> None:
    """일정에 없는 이름을 필수 방문지로 넣으면 잡힌다.

    실제 장소 이름을 쓰면 fixture에 그 장소가 생겼을 때 조용히 무의미해진다.
    그래서 절대 존재하지 않는 이름을 쓴다.
    """
    raw = _plan()
    raw["trip_info"]["persona"]["must_visit"] = ["존재하지_않는_장소_XYZ"]
    assert "MUST_VISIT_MISSING" in _codes(_verify(raw))


def test_detects_budget_exceeded() -> None:
    raw = _plan()
    raw["trip_info"]["budget_total"] = 1000
    assert "BUDGET_EXCEEDED" in _codes(_verify(raw))


def test_detects_ungrounded_item_name() -> None:
    """Plan Agent가 장소를 창작하면 잡힌다."""
    raw = _plan()
    raw["plan"]["days"][0]["items"][0]["name"] = "존재하지 않는 장소"
    codes = _codes(_verify(raw, _search()))
    assert "UNGROUNDED_ITEM_NAME" in codes


def test_detects_mutated_trip_info() -> None:
    """trip_info를 바꾸면 conformance의 cross-handoff 검사가 깨진다."""
    raw = _plan()
    raw["trip_info"]["destination"] = "오사카"
    assert "TRIP_INFO_MUTATED" in _codes(_verify(raw, _search()))


def test_detects_last_item_not_stay_on_multiday_trip() -> None:
    """마지막 여행일이 아닌 날의 마지막 항목은 숙소여야 한다.

    공식 fixture는 이미 다일 일정이므로, 첫날 마지막 항목의 카테고리만
    바꿔서 규칙이 실제로 동작하는지 본다.
    """
    raw = _plan()
    assert len(raw["plan"]["days"]) >= 2, "다일 fixture가 필요합니다"
    # 첫날(=마지막 날이 아닌 날)의 마지막 항목을 숙소가 아닌 것으로 바꾼다.
    raw["plan"]["days"][0]["items"][-1]["category"] = "관광지"
    assert "LAST_ITEM_NOT_STAY" in _codes(_verify(raw))


# ── 입력 단계 검사 ────────────────────────────────────────────


def test_input_check_rejects_unparseable_opening_hours() -> None:
    """배치를 시작하기 전에 알아야 한다. 뒤에서 실패하면 원인을 찾기 어렵다."""
    raw = _search()
    raw["selected"]["places"][0]["opening_hours"] = "상시 개방"
    payload = SearchToPlanInput.model_validate(raw)
    assert "INVALID_OPENING_HOURS" in _codes(contracts.check_input_usable(payload))


def test_input_check_rejects_must_visit_not_in_selection() -> None:
    """Plan Agent는 장소를 만들 수 없으므로 이건 Search 단계의 문제다."""
    raw = _search()
    raw["trip_info"]["persona"]["must_visit"] = ["존재하지_않는_장소_XYZ"]
    payload = SearchToPlanInput.model_validate(raw)
    assert "MUST_VISIT_NOT_SELECTED" in _codes(contracts.check_input_usable(payload))


# ── 숙박비 분배 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("total", "nights"),
    [(180000, 4), (100000, 3), (99999, 7), (1, 3), (0, 5), (250000, 1)],
)
def test_stay_price_distribution_sums_exactly(total: float, nights: int) -> None:
    """반올림 때문에 합이 총액과 어긋나면 예산 판정이 틀어진다."""
    amounts = budget.distribute_stay_price(total, nights)
    assert len(amounts) == nights
    assert round(sum(amounts), 2) == round(total, 2)


def test_stay_price_distribution_is_empty_for_zero_nights() -> None:
    assert budget.distribute_stay_price(180000, 0) == []


def test_budget_treats_empty_includes_as_everything() -> None:
    """rules.py `_is_included_in_budget`: 빈 배열은 '전부 포함'이다."""
    assert budget.is_included_in_budget("숙소", []) is True
    assert budget.is_included_in_budget("관광지", []) is True


def test_budget_alias_matching() -> None:
    assert budget.is_included_in_budget("관광지", ["관광"]) is True
    assert budget.is_included_in_budget("관광지", ["activity"]) is True
    assert budget.is_included_in_budget("카페", ["숙소", "식사"]) is False


def test_budget_multiplier_matches_rules() -> None:
    assert budget.price_multiplier("per_person", 2) == 2
    assert budget.price_multiplier("per_stay", 2) == 1
