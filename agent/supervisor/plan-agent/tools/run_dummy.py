#!/usr/bin/env python
"""Search Agent 더미 결과물을 Plan Agent에 넣고 산출물을 보여준다.

실제 Search Agent와 프론트엔드가 붙기 전에 Plan Agent만 단독으로 확인하는
도구다. 외부 API를 호출하지 않는 것이 기본값이므로 과금이 없다.

## 사용법

    # 전체 시나리오 요약
    python agent/supervisor/plan-agent/tools/run_dummy.py

    # 특정 시나리오의 일정 전문
    python agent/supervisor/plan-agent/tools/run_dummy.py --scenario 4일_표준 --json

    # 실제 Google Routes API로 이동시간 계산 (과금 발생)
    python agent/supervisor/plan-agent/tools/run_dummy.py --live

## 무엇을 확인하는가

산출물이 검증 에이전트의 판정을 통과하는지를 본다. 구조만 맞고 규칙을 어기면
사용자에게 "실행하기 어려운 일정"으로 표시되기 때문이다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE.parent / "tests"))


def _configure(live: bool, verbose: bool) -> None:
    """API 사용 여부를 결정한다. 기본은 호출하지 않는다(과금 0)."""

    if not live:
        os.environ["ROUTES_ENABLED"] = "off"
        os.environ["GEMINI_API_KEY"] = ""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="  %(levelname)-7s %(message)s",
    )


def _format_plan(payload) -> str:
    """일정을 사람이 읽는 표로 만든다."""

    lines: list[str] = []
    trip = payload.trip_info
    lines.append(
        f"{trip.destination}  {trip.start_date} ~ {trip.end_date}  "
        f"{trip.num_travelers}인  예산 {trip.budget_total:,.0f}{trip.budget_currency}"
    )
    lines.append(
        f"페이스 {trip.persona.pace} · 최대 활동강도 {trip.persona.max_walking_level} "
        f"· 이동 {trip.transport_mode}"
    )
    if trip.persona.must_visit:
        lines.append(f"필수 방문: {', '.join(trip.persona.must_visit)}")
    lines.append("")

    for day in payload.plan.days:
        weekday = _weekday_ko(day.date)
        lines.append(f"── Day {day.day}  {day.date}({weekday}) " + "─" * 30)
        for item in day.items:
            travel = ""
            if item.travel_from_prev is not None:
                travel = (
                    f"   ↑ {item.travel_from_prev.mode} "
                    f"{item.travel_from_prev.estimated_min}분 "
                    f"({item.travel_from_prev.distance_km}km)"
                )
                lines.append(travel)
            price = f"{item.price:,.0f}" if item.price else "무료"
            unit = "/인" if item.price_unit == "per_person" else "/숙박"
            lines.append(
                f"  {item.start_time}-{item.end_time}  [{item.category}] {item.name}"
                f"  {price}{unit if item.price else ''}"
            )
            if item.note:
                lines.append(f"                    · {item.note}")
        lines.append("")
    return "\n".join(lines)


def _weekday_ko(date_str: str) -> str:
    from plan_agent import timecalc

    return timecalc.weekday_ko(date_str)[0]


async def _run_one(name: str, kwargs: dict, *, show_plan: bool, as_json: bool) -> bool:
    from dummy_search_output import make_search_output
    from plan_agent import budget, contracts
    from plan_agent.graph import generate_itinerary
    from plan_agent.models import SearchToPlanInput
    from plan_agent.quota import BUDGET
    from plan_agent.routing import clear_cache

    clear_cache()
    raw = make_search_output(**kwargs)
    source = SearchToPlanInput.model_validate(raw)

    payload, diagnostics = await generate_itinerary(source)

    if payload is None:
        print(f"  [실패] {name}")
        for violation in diagnostics.violations:
            print(f"          {violation.code}: {violation.message}")
        return False

    violations = contracts.verify_all(payload, source)
    total = budget.estimate_total(payload)
    day_count = len(payload.plan.days)
    item_count = sum(len(day.items) for day in payload.plan.days)
    estimated = diagnostics.estimated_leg_count
    over = total - source.trip_info.budget_total

    status = "통과" if not violations else f"위반 {len(violations)}건"
    print(
        f"  [{status}] {name:12} "
        f"{day_count}일 {item_count}항목  "
        f"비용 {total:>10,.0f}/{source.trip_info.budget_total:,.0f}"
        f"{'  초과 ' + format(over, ',.0f') if over > 0 else ''}"
        f"  추정이동 {estimated}/{diagnostics.total_leg_count}"
    )
    for violation in violations:
        print(f"          {violation.code}: {violation.message}")
    for note in diagnostics.notes:
        print(f"          메모: {note}")
    for item in diagnostics.unassigned:
        print(f"          미배치: {item.place_name} — {item.reason}")

    if as_json:
        print()
        print(json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2))
    elif show_plan:
        print()
        print(_format_plan(payload))

    print(f"          {BUDGET.describe()}")
    return not violations


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Plan Agent 더미 검증")
    parser.add_argument("--scenario", help="특정 시나리오만 실행")
    parser.add_argument("--json", action="store_true", help="산출물 JSON 전문 출력")
    parser.add_argument("--plan", action="store_true", help="일정을 표로 출력")
    parser.add_argument(
        "--live", action="store_true", help="실제 Google Routes / Gemini 호출 (과금)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="로그 표시")
    args = parser.parse_args()

    _configure(args.live, args.verbose)

    from dummy_search_output import SCENARIOS

    if args.live:
        print("!! 실제 API를 호출합니다 (과금 발생)\n")
    else:
        print("외부 API 호출 없음 (좌표 추정 + 템플릿 문장)\n")

    scenarios = (
        {args.scenario: SCENARIOS[args.scenario]}
        if args.scenario
        else SCENARIOS
    )
    if args.scenario and args.scenario not in SCENARIOS:
        print(f"시나리오 '{args.scenario}'가 없습니다. 가능한 값: {list(SCENARIOS)}")
        return 2

    single = len(scenarios) == 1
    results = []
    for name, kwargs in scenarios.items():
        ok = await _run_one(
            name,
            kwargs,
            show_plan=args.plan or single,
            as_json=args.json,
        )
        results.append(ok)

    passed = sum(results)
    print()
    print(f"결과: {passed}/{len(results)} 시나리오 통과")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
