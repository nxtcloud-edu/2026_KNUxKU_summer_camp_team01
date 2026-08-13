"""배치 → 시각 확정 파이프라인 테스트.

가장 중요한 것은 **만들어낸 일정이 검증 에이전트의 판정을 통과하는가**다.
그래서 거의 모든 테스트가 `contracts.verify_all()`로 끝난다. 구조만 맞고
규칙을 어기면 사용자에게 "실행하기 어려운 일정"으로 표시되기 때문이다.

다일 여행이 진짜 어려운 경우다. 숙소가 매일 반복되고, 예산이 중복 가산되기
쉽고, 휴무일을 피해야 하고, 마지막 날만 규칙이 다르다.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from plan_agent import budget, contracts, routing, timecalc
from plan_agent.models import SearchToPlanInput
from plan_agent.planner import build_plan


def _find_agent_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "schemas").is_dir() and (candidate / "fixtures").is_dir():
            return candidate
    raise RuntimeError("agent 루트를 찾지 못했습니다")


FIXTURES = _find_agent_root() / "fixtures"


@pytest.fixture(autouse=True)
def _clear_routing_cache():
    routing.clear_cache()
    yield
    routing.clear_cache()


def _base_search() -> dict:
    return json.loads((FIXTURES / "search-to-plan.example.json").read_text("utf-8"))


def _place(
    place_id: str,
    name: str,
    lat: float,
    lng: float,
    *,
    category: str = "관광지",
    opening: str = "09:00-18:00",
    duration: int = 90,
    price: float = 0.0,
    closed: list[str] | None = None,
    intensity: str = "중간",
) -> dict:
    return {
        "id": place_id,
        "name": name,
        "category": category,
        "lat": lat,
        "lng": lng,
        "price": price,
        "price_unit": "per_person",
        "opening_hours": opening,
        "closed_days": closed or [],
        "expected_duration_min": duration,
        "physical_intensity": intensity,
        "note": "",
    }


def _multiday_search(
    *,
    start: str = "2026-06-15",
    end: str = "2026-06-18",
    places: list[dict] | None = None,
    budget_total: float = 2_000_000,
    pace: str = "보통",
    must_visit: list[str] | None = None,
    with_stay: bool = True,
) -> dict:
    raw = _base_search()
    raw["trip_info"]["start_date"] = start
    raw["trip_info"]["end_date"] = end
    raw["trip_info"]["budget_total"] = budget_total
    raw["trip_info"]["persona"]["pace"] = pace
    raw["trip_info"]["persona"]["must_visit"] = (
        must_visit if must_visit is not None else []
    )
    raw["selected"]["places"] = places or [
        _place("p1", "센소지", 35.7148, 139.7967),
        _place("p2", "우에노공원", 35.7148, 139.7737),
        _place("p3", "도쿄타워", 35.6586, 139.7454),
        _place("p4", "메이지신궁", 35.6764, 139.6993),
        _place("p5", "시부야스카이", 35.6580, 139.7016),
        _place("p6", "츠키지시장", 35.6654, 139.7707),
    ]
    if not with_stay:
        raw["selected"]["stay"] = None
    return raw


def _build(raw: dict):
    source = SearchToPlanInput.model_validate(raw)
    return source, build_plan(source)


def _codes(violations) -> set[str]:
    return {violation.code for violation in violations}


# ── 공식 fixture ─────────────────────────────────────────────


def test_official_fixture_produces_valid_plan() -> None:
    source, result = _build(_base_search())
    assert result.payload is not None
    assert contracts.verify_all(result.payload, source) == []


def test_official_fixture_preserves_trip_info_exactly() -> None:
    raw = _base_search()
    source, result = _build(raw)
    assert result.payload is not None
    assert result.payload.trip_info.model_dump(mode="json") == raw["trip_info"]


def test_stay_opening_hours_is_synthesized_parseably() -> None:
    """`SelectedStay`에는 opening_hours가 없어서 우리가 만든다."""
    _, result = _build(_base_search())
    assert result.payload is not None
    stay_items = [
        item
        for day in result.payload.plan.days
        for item in day.items
        if item.category == "숙소"
    ]
    assert stay_items
    for item in stay_items:
        assert timecalc.parse_opening_hours(item.opening_hours) is not None


# ── 다일 여행: 가장 어려운 경우 ────────────────────────────────


def test_multiday_plan_passes_all_verification_rules() -> None:
    source, result = _build(_multiday_search())
    assert result.payload is not None, result.diagnostics.violations
    violations = contracts.verify_all(result.payload, source)
    assert violations == [], [v.model_dump() for v in violations]


def test_multiday_day_count_and_dates_are_continuous() -> None:
    _, result = _build(_multiday_search(start="2026-06-15", end="2026-06-18"))
    assert result.payload is not None
    days = result.payload.plan.days
    assert len(days) == 4
    assert [day.day for day in days] == [1, 2, 3, 4]
    assert [day.date for day in days] == [
        "2026-06-15",
        "2026-06-16",
        "2026-06-17",
        "2026-06-18",
    ]


def test_every_non_last_day_ends_with_stay() -> None:
    """LAST_ITEM_NOT_STAY를 만족해야 한다."""
    _, result = _build(_multiday_search())
    assert result.payload is not None
    days = result.payload.plan.days
    for day in days[:-1]:
        assert day.items[-1].category == "숙소", f"Day {day.day}"


def test_stay_price_is_not_double_counted() -> None:
    """숙소가 매일 반복되지만 합계는 숙박 총액과 같아야 한다."""
    raw = _multiday_search(start="2026-06-15", end="2026-06-19")  # 5일 = 4박
    stay_total = raw["selected"]["stay"]["price"]
    _, result = _build(raw)
    assert result.payload is not None

    stay_sum = sum(
        item.price
        for day in result.payload.plan.days
        for item in day.items
        if item.category == "숙소"
    )
    assert round(stay_sum, 2) == round(stay_total, 2), (
        f"숙박비 합계 {stay_sum}가 총액 {stay_total}와 다릅니다"
    )


def test_stay_occurrence_count_equals_nights() -> None:
    raw = _multiday_search(start="2026-06-15", end="2026-06-19")  # 4박
    _, result = _build(raw)
    assert result.payload is not None
    stay_items = [
        item
        for day in result.payload.plan.days
        for item in day.items
        if item.category == "숙소"
    ]
    assert len(stay_items) == 4


def test_first_item_of_each_day_has_no_travel() -> None:
    _, result = _build(_multiday_search())
    assert result.payload is not None
    for day in result.payload.plan.days:
        assert day.items[0].travel_from_prev is None
        for item in day.items[1:]:
            assert item.travel_from_prev is not None


def test_item_ids_are_unique_and_match_pattern() -> None:
    import re

    _, result = _build(_multiday_search())
    assert result.payload is not None
    pattern = re.compile(r"^d[1-9]\d*-[1-9]\d*$")
    seen: set[str] = set()
    for day in result.payload.plan.days:
        for item in day.items:
            assert pattern.match(item.id), item.id
            assert item.id not in seen
            seen.add(item.id)


def test_times_stay_inside_day_window() -> None:
    raw = _multiday_search()
    _, result = _build(raw)
    assert result.payload is not None
    day_start = timecalc.to_minutes(raw["trip_info"]["day_start_time"])
    day_end = timecalc.to_minutes(raw["trip_info"]["day_end_time"])
    for day in result.payload.plan.days:
        assert timecalc.to_minutes(day.items[0].start_time) >= day_start
        assert timecalc.to_minutes(day.items[-1].end_time) <= day_end


def test_travel_time_is_always_sufficient() -> None:
    _, result = _build(_multiday_search())
    assert result.payload is not None
    for day in result.payload.plan.days:
        for index, item in enumerate(day.items[1:], start=1):
            previous = day.items[index - 1]
            assert item.travel_from_prev is not None
            earliest = (
                timecalc.to_minutes(previous.end_time)
                + item.travel_from_prev.estimated_min
            )
            assert timecalc.to_minutes(item.start_time) >= earliest


def test_duration_always_matches_start_end() -> None:
    _, result = _build(_multiday_search())
    assert result.payload is not None
    for day in result.payload.plan.days:
        for item in day.items:
            span = timecalc.to_minutes(item.end_time) - timecalc.to_minutes(
                item.start_time
            )
            assert span == item.expected_duration_min


# ── 휴무일 회피 ──────────────────────────────────────────────


def test_closed_day_place_is_not_scheduled_on_that_day() -> None:
    """2026-06-15는 월요일이다. 월요일 휴무 장소는 그 날에 오면 안 된다."""
    places = [
        _place("p1", "월요휴관박물관", 35.7188, 139.7765, closed=["월요일"]),
        _place("p2", "센소지", 35.7148, 139.7967),
        _place("p3", "도쿄타워", 35.6586, 139.7454),
    ]
    source, result = _build(
        _multiday_search(start="2026-06-15", end="2026-06-17", places=places)
    )
    assert result.payload is not None
    for day in result.payload.plan.days:
        for item in day.items:
            assert not timecalc.is_closed_on(day.date, list(item.closed_days)), (
                f"{item.name}이 휴무일 {day.date}에 배치됐습니다"
            )
    assert contracts.verify_all(result.payload, source) == []


def test_place_closed_every_day_is_reported_not_dropped_silently() -> None:
    """모든 날 휴무인 장소는 조용히 사라지지 않고 이유와 함께 보고된다."""
    every_day = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    places = [
        _place("p1", "항상휴관", 35.71, 139.79, closed=every_day),
        _place("p2", "센소지", 35.7148, 139.7967),
    ]
    _, result = _build(
        _multiday_search(start="2026-06-15", end="2026-06-16", places=places)
    )
    names = {item.place_name for item in result.diagnostics.unassigned}
    assert "항상휴관" in names


# ── 구조적으로 불가능한 입력 ──────────────────────────────────


def test_multiday_without_stay_is_reported_as_impossible() -> None:
    """숙소 없이 다일 일정은 LAST_ITEM_NOT_STAY를 만족할 수 없다.

    억지로 만들어 검증에서 실패하게 두는 대신, 만들기 전에 이유를 말한다.
    """
    source, result = _build(_multiday_search(with_stay=False))
    assert result.payload is None
    assert "STAY_REQUIRED_FOR_MULTIDAY" in _codes(result.diagnostics.violations)


def test_must_visit_not_in_selection_is_reported() -> None:
    source, result = _build(_multiday_search(must_visit=["존재하지 않는 곳"]))
    assert result.payload is None
    assert "MUST_VISIT_NOT_SELECTED" in _codes(result.diagnostics.violations)


def test_unparseable_opening_hours_place_is_not_scheduled() -> None:
    """검증에서 fail이 될 형식이므로 배치하지 않고 보고한다."""
    places = [
        _place("p1", "센소지", 35.7148, 139.7967),
        _place("p2", "이상한영업시간", 35.70, 139.78, opening="상시 개방"),
    ]
    source, result = _build(
        _multiday_search(start="2026-06-15", end="2026-06-16", places=places)
    )
    assert result.payload is not None
    scheduled = {
        item.name for day in result.payload.plan.days for item in day.items
    }
    assert "이상한영업시간" not in scheduled
    # 그리고 그 사실이 보고되어야 한다.
    reported = {item.place_name for item in result.diagnostics.unassigned}
    assert "이상한영업시간" in reported
    assert contracts.verify_all(result.payload, source) == []


# ── must_visit 보장 ──────────────────────────────────────────


def test_must_visit_place_is_always_scheduled() -> None:
    places = [
        _place("p1", "센소지", 35.7148, 139.7967),
        _place("p2", "도쿄타워", 35.6586, 139.7454),
        _place("p3", "메이지신궁", 35.6764, 139.6993),
        _place("p4", "우에노공원", 35.7148, 139.7737),
        _place("p5", "시부야스카이", 35.6580, 139.7016),
        _place("p6", "츠키지시장", 35.6654, 139.7707),
    ]
    source, result = _build(
        _multiday_search(
            start="2026-06-15", end="2026-06-16", places=places, must_visit=["도쿄타워"]
        )
    )
    assert result.payload is not None
    assert contracts.check_must_visit(result.payload) == []


# ── 예산 ─────────────────────────────────────────────────────


def test_budget_exceeded_is_reported_not_hidden() -> None:
    expensive = [
        _place("p1", "센소지", 35.7148, 139.7967, price=500_000),
        _place("p2", "도쿄타워", 35.6586, 139.7454, price=500_000),
    ]
    _, result = _build(
        _multiday_search(
            start="2026-06-15", end="2026-06-16", places=expensive, budget_total=1000
        )
    )
    assert result.payload is not None
    assert "BUDGET_EXCEEDED" in _codes(result.diagnostics.violations)


def test_estimated_total_matches_verification_formula() -> None:
    """자기 계산과 검증 에이전트 계산이 같아야 한다."""
    raw = _multiday_search()
    _, result = _build(raw)
    assert result.payload is not None
    total = budget.estimate_total(result.payload)
    # per_person은 인원수를 곱하고 per_stay는 곱하지 않는다.
    expected = 0.0
    travelers = raw["trip_info"]["num_travelers"]
    for day in result.payload.plan.days:
        for item in day.items:
            if not budget.is_included_in_budget(
                item.category, raw["trip_info"]["budget_includes"]
            ):
                continue
            expected += item.price * (travelers if item.price_unit == "per_person" else 1)
    assert total == pytest.approx(expected)


# ── 페이스 ───────────────────────────────────────────────────


def test_relaxed_pace_puts_fewer_places_per_day() -> None:
    places = [
        _place(f"p{index}", f"장소{index}", 35.65 + index * 0.005, 139.70 + index * 0.005)
        for index in range(1, 7)
    ]
    _, relaxed = _build(
        _multiday_search(start="2026-06-15", end="2026-06-19", places=places, pace="여유")
    )
    assert relaxed.payload is not None
    counts = [
        len([item for item in day.items if item.category != "숙소"])
        for day in relaxed.payload.plan.days
    ]
    # 여유는 하루 2~3곳이 목표다. 6곳을 5일에 나누면 상한을 넘지 않는다.
    assert max(counts) <= 3, counts


def test_determinism_same_input_same_output() -> None:
    """같은 입력이면 같은 결과. 디버깅과 데모가 가능해야 한다."""
    raw = _multiday_search()
    routing.clear_cache()
    _, first = _build(copy.deepcopy(raw))
    routing.clear_cache()
    _, second = _build(copy.deepcopy(raw))
    assert first.payload is not None and second.payload is not None
    assert first.payload.model_dump(mode="json") == second.payload.model_dump(mode="json")


# ── 진단 정보가 계약으로 새지 않는다 ──────────────────────────


def test_diagnostics_never_appear_in_contract_payload() -> None:
    """추정 여부·미배치 같은 내부 정보는 payload에 들어가지 않는다.

    `estimated_min`은 계약에 정의된 정상 필드이므로 금지어가 아니다.
    금지 대상은 우리가 내부적으로만 쓰는 이름들이다.
    """
    _, result = _build(_multiday_search())
    assert result.payload is not None
    dumped = json.dumps(result.payload.model_dump(mode="json"), ensure_ascii=False)
    for forbidden in ["unassigned", "diagnostic", "overflow", "추정", "estimated_leg"]:
        assert forbidden not in dumped, forbidden

    # 필드 이름을 직접 확인한다. 계약이 허용하는 세 개뿐이어야 한다.
    for day in result.payload.plan.days:
        for item in day.items:
            if item.travel_from_prev is None:
                continue
            assert set(item.travel_from_prev.model_dump()) == {
                "mode",
                "estimated_min",
                "distance_km",
            }


def test_summary_line_respects_contract_length_limit() -> None:
    """`done.summary`는 계약상 200자 이내다."""
    _, result = _build(_multiday_search())
    line = result.diagnostics.summary_line(4, 12)
    assert len(line) <= 200
    assert line
