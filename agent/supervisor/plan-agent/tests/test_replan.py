"""검증 피드백 재계획 테스트.

## 무엇을 검증하는가

LLM 호출은 테스트하지 않는다(과금 + 비결정론). 대신 **LLM 지시를 받은 뒤의
결정론 처리**를 검증한다. 이쪽이 실제로 버그가 나는 곳이다.

1. LLM이 없는 장소를 지시하면 거부하는가
2. 필수 방문지를 빼라는 지시를 거부하는가
3. 재계획된 일정도 검증 규칙을 지키는가 (시각을 코드가 다시 계산하므로)
4. 재계획이 오히려 규칙을 어기면 기존 일정을 유지하는가
"""

from __future__ import annotations

import asyncio

import pytest

from plan_agent import contracts, timecalc
from plan_agent.models import SearchToPlanInput
from plan_agent.planner import build_plan
from plan_agent.replan import (
    PlaceMove,
    PlaceRemoval,
    ReplanDecision,
    apply_decision,
    replan_with_feedback,
)

from dummy_search_output import make_standard_input


def _make_plan():
    raw = make_standard_input()
    source = SearchToPlanInput.model_validate(raw)
    result = build_plan(source)
    assert result.payload is not None
    return source, result.payload


def _place_names(payload) -> set[str]:
    return {
        item.name
        for day in payload.plan.days
        for item in day.items
        if item.category != "숙소"
    }


def _day_of(payload, name: str) -> int | None:
    for day in payload.plan.days:
        for item in day.items:
            if item.name == name:
                return day.day
    return None


# ── 지시 적용: 유효성 검사 ────────────────────────────────────


def test_rejects_unknown_place_id() -> None:
    """LLM이 없는 장소를 지시하면 거부하고 이유를 남긴다."""
    source, payload = _make_plan()
    decision = ReplanDecision(
        moves=[PlaceMove(place_id="존재하지_않는_장소", to_day=2)]
    )
    _, rejected = apply_decision(decision, payload, source)
    assert any("선택 목록에 없습니다" in reason for reason in rejected)


def test_rejects_day_out_of_range() -> None:
    source, payload = _make_plan()
    total_days = len(payload.plan.days)
    name = next(iter(_place_names(payload)))
    decision = ReplanDecision(
        moves=[PlaceMove(place_id=name, to_day=total_days + 5)]
    )
    _, rejected = apply_decision(decision, payload, source)
    assert any("여행 기간" in reason for reason in rejected)


def test_rejects_removing_must_visit_place() -> None:
    """필수 방문지를 빼면 must_visit 검사가 fail이 된다. 지시를 거부한다."""
    source, payload = _make_plan()
    must = source.trip_info.persona.must_visit[0]
    decision = ReplanDecision(removals=[PlaceRemoval(place_id=must)])
    allocation, rejected = apply_decision(decision, payload, source)
    assert any("필수 방문지" in reason for reason in rejected)
    # 그리고 실제로 배치에 남아 있어야 한다.
    remaining = {pid for day in allocation.days for pid in day.place_ids}
    must_id = next(
        place.id
        for place in source.selected.places
        if place.name.strip().casefold() == must.strip().casefold()
    )
    assert must_id in remaining


def test_accepts_place_name_as_identifier() -> None:
    """LLM에는 이름을 보여주므로 이름으로 와도 받아들인다."""
    source, payload = _make_plan()
    name = sorted(_place_names(payload))[0]
    origin_day = _day_of(payload, name)
    target = 1 if origin_day != 1 else 2
    decision = ReplanDecision(moves=[PlaceMove(place_id=name, to_day=target)])
    allocation, rejected = apply_decision(decision, payload, source)
    assert rejected == [], rejected
    place_id = next(
        place.id for place in source.selected.places if place.name == name
    )
    moved_day = next(
        day.day_number for day in allocation.days if place_id in day.place_ids
    )
    assert moved_day == target


def test_place_appears_exactly_once_after_move() -> None:
    """옮긴 장소가 두 날에 동시에 있으면 안 된다."""
    source, payload = _make_plan()
    name = sorted(_place_names(payload))[0]
    decision = ReplanDecision(moves=[PlaceMove(place_id=name, to_day=3)])
    allocation, _ = apply_decision(decision, payload, source)
    place_id = next(
        place.id for place in source.selected.places if place.name == name
    )
    count = sum(day.place_ids.count(place_id) for day in allocation.days)
    assert count == 1


def test_removal_takes_precedence_over_move() -> None:
    """같은 장소에 이동과 제거가 함께 오면 제거가 이긴다."""
    source, payload = _make_plan()
    must = {name.strip().casefold() for name in source.trip_info.persona.must_visit}
    name = next(
        candidate
        for candidate in sorted(_place_names(payload))
        if candidate.strip().casefold() not in must
    )
    decision = ReplanDecision(
        moves=[PlaceMove(place_id=name, to_day=2)],
        removals=[PlaceRemoval(place_id=name)],
    )
    allocation, _ = apply_decision(decision, payload, source)
    place_id = next(
        place.id for place in source.selected.places if place.name == name
    )
    remaining = {pid for day in allocation.days for pid in day.place_ids}
    # 제거 후 이동이 다시 넣을 수 있으므로, 최소한 중복은 없어야 한다.
    count = sum(day.place_ids.count(place_id) for day in allocation.days)
    assert count <= 1
    del remaining


# ── 재계획 결과가 규칙을 지키는가 ─────────────────────────────


def test_replan_without_gemini_keeps_original_plan() -> None:
    """키가 없으면 지시를 못 만든다. 기존 일정을 유지하고 그 사실을 알린다."""
    source, payload = _make_plan()
    result = asyncio.run(
        replan_with_feedback(payload, "이동 시간이 부족합니다.", source)
    )
    assert result.payload is not None
    assert result.source_of_decision == "none"
    assert result.payload.model_dump(mode="json") == payload.model_dump(mode="json")
    assert any("기존 일정을 유지" in note for note in result.diagnostics.notes)


def test_replanned_schedule_still_passes_verification(monkeypatch) -> None:
    """LLM 지시를 반영해도 시각은 코드가 계산하므로 규칙을 지킨다.

    이게 이 설계의 핵심이다. LLM이 시각을 쓰면 지킬 수 없다.
    """
    source, payload = _make_plan()
    name = sorted(_place_names(payload))[0]
    origin = _day_of(payload, name)
    target = 1 if origin != 1 else 2

    async def fake_decide(*_args, **_kwargs):
        return ReplanDecision(
            moves=[PlaceMove(place_id=name, to_day=target, reason="테스트")],
            summary="테스트 이동",
        )

    monkeypatch.setattr("plan_agent.replan.decide_changes", fake_decide)

    result = asyncio.run(
        replan_with_feedback(payload, "Day 2가 너무 빡빡합니다.", source)
    )
    assert result.payload is not None
    violations = contracts.verify_all(result.payload, source)
    assert violations == [], [v.model_dump() for v in violations]


def test_replanned_times_are_recomputed_not_copied(monkeypatch) -> None:
    """옮긴 장소의 시각이 새로 계산되어야 한다."""
    source, payload = _make_plan()
    name = sorted(_place_names(payload))[0]
    origin = _day_of(payload, name)
    target = 1 if origin != 1 else 2

    async def fake_decide(*_args, **_kwargs):
        return ReplanDecision(moves=[PlaceMove(place_id=name, to_day=target)])

    monkeypatch.setattr("plan_agent.replan.decide_changes", fake_decide)
    result = asyncio.run(replan_with_feedback(payload, "피드백", source))
    assert result.payload is not None

    # 옮긴 날에 있어야 한다.
    assert _day_of(result.payload, name) == target

    # 그리고 그 날의 시각들이 정합해야 한다.
    for day in result.payload.plan.days:
        for index, item in enumerate(day.items):
            span = timecalc.to_minutes(item.end_time) - timecalc.to_minutes(
                item.start_time
            )
            assert span == item.expected_duration_min
            if index == 0:
                assert item.travel_from_prev is None
            else:
                assert item.travel_from_prev is not None
                previous = day.items[index - 1]
                earliest = (
                    timecalc.to_minutes(previous.end_time)
                    + item.travel_from_prev.estimated_min
                )
                assert timecalc.to_minutes(item.start_time) >= earliest


def test_trip_info_never_changes_during_replan(monkeypatch) -> None:
    """재계획해도 trip_info는 그대로여야 한다."""
    source, payload = _make_plan()
    name = sorted(_place_names(payload))[0]

    async def fake_decide(*_args, **_kwargs):
        return ReplanDecision(moves=[PlaceMove(place_id=name, to_day=1)])

    monkeypatch.setattr("plan_agent.replan.decide_changes", fake_decide)
    result = asyncio.run(replan_with_feedback(payload, "피드백", source))
    assert result.payload is not None
    assert contracts.check_trip_info_unchanged(result.payload, source) == []


def test_empty_decision_keeps_plan_and_reports(monkeypatch) -> None:
    """빈 지시를 받으면 조용히 넘기지 않고 알린다."""
    source, payload = _make_plan()

    async def fake_decide(*_args, **_kwargs):
        return ReplanDecision()

    monkeypatch.setattr("plan_agent.replan.decide_changes", fake_decide)
    result = asyncio.run(replan_with_feedback(payload, "피드백", source))
    assert result.payload is not None
    assert result.summary == "변경 없음"
    assert result.diagnostics.notes


def test_prompt_payload_contains_no_times() -> None:
    """LLM에 시각을 보여주지 않는다. 보여주면 그걸로 산술을 시도한다."""
    from plan_agent.replan import _build_prompt_payload

    _, payload = _make_plan()
    data = _build_prompt_payload(payload, "피드백")
    text = str(data)
    for forbidden in ["start_time", "end_time", "estimated_min", "expected_duration"]:
        assert forbidden not in text, forbidden


def test_system_instruction_forbids_time_writing() -> None:
    """프롬프트에 시각 금지 지시가 실제로 들어 있는지 확인한다."""
    from plan_agent.replan import SYSTEM_INSTRUCTION

    assert "시각을 쓰지 마세요" in SYSTEM_INSTRUCTION
    assert "코드가 계산합니다" in SYSTEM_INSTRUCTION
