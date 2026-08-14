#!/usr/bin/env python
"""표준 더미 입력을 Plan Agent에 넣고 산출물을 사람이 읽는 형태로 보여준다.

실제 Search Agent와 프론트엔드가 붙기 전에 Plan Agent만 단독으로 확인하는
도구다. 외부 API를 호출하지 않는 것이 기본값이므로 과금이 없다.

## 사용법

    python agent/supervisor/plan-agent/tools/run_dummy.py
    python agent/supervisor/plan-agent/tools/run_dummy.py --json
    python agent/supervisor/plan-agent/tools/run_dummy.py --pace 빡빡
    python agent/supervisor/plan-agent/tools/run_dummy.py --live   # 과금 발생

## 입력 하나, 결과 하나

`pace` 같은 성향은 프론트엔드 웹사이트가 사용자에게서 받아 `trip_info.persona`에
담아 보내는 값이다. Plan Agent는 그걸 반영해 일정 하나를 만든다. `--pace`는
다른 입력을 넣어 보는 것이지 여러 안을 만드는 것이 아니다.
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


def _format_plan(payload) -> str:
    from plan_agent import timecalc

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
        weekday = timecalc.weekday_ko(day.date)[0]
        place_count = len([i for i in day.items if i.category != "숙소"])
        lines.append(
            f"── Day {day.day}  {day.date}({weekday})  장소 {place_count}곳 "
            + "─" * 24
        )
        for item in day.items:
            if item.travel_from_prev is not None:
                lines.append(
                    f"   ↑ {item.travel_from_prev.mode} "
                    f"{item.travel_from_prev.estimated_min}분 "
                    f"({item.travel_from_prev.distance_km}km)"
                )
            price = f"{item.price:,.0f}" if item.price else "무료"
            unit = ""
            if item.price:
                unit = "/인" if item.price_unit == "per_person" else "/숙박"
            lines.append(
                f"  {item.start_time}-{item.end_time}  [{item.category}] "
                f"{item.name}  {price}{unit}"
            )
            if item.note:
                lines.append(f"                    · {item.note}")
        lines.append("")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Plan Agent 더미 실행")
    parser.add_argument("--json", action="store_true", help="산출물 JSON 전문 출력")
    parser.add_argument("--pace", help="페이스를 바꿔서 실행 (여유/보통/빡빡)")
    parser.add_argument("--days", type=int, help="여행 일수를 바꿔서 실행")
    parser.add_argument(
        "--live", action="store_true", help="실제 Google Routes / Gemini 호출 (과금)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="로그 표시")
    args = parser.parse_args()

    if not args.live:
        os.environ["ROUTES_ENABLED"] = "off"
        os.environ["GEMINI_API_KEY"] = ""
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="  %(levelname)-7s %(message)s",
    )

    from dummy_search_output import STANDARD_INPUT, make_standard_input
    from plan_agent import budget, contracts, timecalc
    from plan_agent.graph import generate_itinerary
    from plan_agent.models import SearchToPlanInput
    from plan_agent.quota import BUDGET

    overrides: dict = {}
    if args.pace:
        overrides["pace"] = args.pace
    if args.days:
        start = STANDARD_INPUT["start_date"]
        overrides["end_date"] = timecalc.add_days(start, args.days - 1)

    print(
        "!! 실제 API를 호출합니다 (과금 발생)"
        if args.live
        else "외부 API 호출 없음 (좌표 추정 + 템플릿 문장)"
    )
    print()

    source_raw = make_standard_input(**overrides)
    source = SearchToPlanInput.model_validate(source_raw)
    payload, diagnostics = await generate_itinerary(source)

    if payload is None:
        print("일정을 만들지 못했습니다:")
        for violation in diagnostics.violations:
            print(f"  {violation.code}: {violation.message}")
        return 1

    violations = contracts.verify_all(payload, source)
    total = budget.estimate_total(payload)
    item_count = sum(len(day.items) for day in payload.plan.days)

    if args.json:
        print(json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(_format_plan(payload))

    print(
        f"검증 {'통과' if not violations else f'위반 {len(violations)}건'}  |  "
        f"{len(payload.plan.days)}일 {item_count}항목  |  "
        f"비용 {total:,.0f}/{source.trip_info.budget_total:,.0f} "
        f"{source.trip_info.budget_currency}  |  "
        f"추정이동 {diagnostics.estimated_leg_count}/{diagnostics.total_leg_count}"
    )
    for violation in violations:
        print(f"  {violation.code}: {violation.message}")
    for note in diagnostics.notes:
        print(f"  메모: {note}")
    for item in diagnostics.unassigned:
        print(f"  미배치: {item.place_name} — {item.reason}")
    print(f"  {BUDGET.describe()}")
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
