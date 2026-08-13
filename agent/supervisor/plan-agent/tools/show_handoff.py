#!/usr/bin/env python
"""Plan Agent가 Verification Agent에게 넘기는 데이터를 그대로 보여준다.

`PlanToVerificationInput` 전문을 출력하고, 그 데이터가 검증 에이전트의
결정론 규칙을 통과하는지 함께 확인한다. 통과 여부를 같이 보여주는 이유는,
JSON이 예쁘게 나오는 것과 검증을 통과하는 것은 다른 문제이기 때문이다.

## 사용법

    python agent/supervisor/plan-agent/tools/show_handoff.py
    python agent/supervisor/plan-agent/tools/show_handoff.py --scenario 5일_빡빡
    python agent/supervisor/plan-agent/tools/show_handoff.py --save handoff.json

외부 API를 호출하지 않는 것이 기본값이다(과금 0).
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


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", help="JSON을 파일로 저장한다")
    parser.add_argument("--live", action="store_true", help="실제 API 호출 (과금)")
    args = parser.parse_args()

    if not args.live:
        os.environ["ROUTES_ENABLED"] = "off"
        os.environ["GEMINI_API_KEY"] = ""
    logging.basicConfig(level=logging.WARNING, format="  %(levelname)s %(message)s")

    from dummy_search_output import make_standard_input
    from plan_agent import budget, contracts
    from plan_agent.graph import generate_itinerary
    from plan_agent.models import SearchToPlanInput

    source_raw = make_standard_input()
    source = SearchToPlanInput.model_validate(source_raw)

    payload, diagnostics = await generate_itinerary(source)
    if payload is None:
        print("일정을 만들지 못했습니다:")
        for violation in diagnostics.violations:
            print(f"  {violation.code}: {violation.message}")
        return 1

    handoff = payload.model_dump(mode="json")

    print("=" * 70)
    print("Search Agent 더미 입력")
    print("=" * 70)
    selected = source_raw["selected"]
    print(f"  선택 장소 {len(selected['places'])}곳")
    for place in selected["places"]:
        print(
            f"    - {place['name']} ({place['category']}, "
            f"{place['opening_hours']}, {place['expected_duration_min']}분)"
        )
    stay = selected.get("stay")
    print(
        f"  숙소: {stay['name']} (체크인 {stay['check_in_time']}, "
        f"{stay['price']:,.0f} {source_raw['trip_info']['budget_currency']})"
        if stay
        else "  숙소: 없음"
    )
    print()

    print("=" * 70)
    print("Plan Agent -> Verification Agent 로 넘기는 데이터")
    print("=" * 70)
    print(json.dumps(handoff, ensure_ascii=False, indent=2))
    print()

    print("=" * 70)
    print("이 데이터가 검증을 통과하는가")
    print("=" * 70)
    violations = contracts.verify_all(payload, source)
    checks = [
        ("daily_schedule   (일수·날짜·숙소·시각 창)", contracts.check_daily_schedule(payload)),
        ("physical_feasibility (시간·이동 정합)", contracts.check_physical_feasibility(payload)),
        ("operating_hours   (휴무일·영업시간)", contracts.check_operating_hours(payload)),
        ("must_visit        (필수 방문지)", contracts.check_must_visit(payload)),
        ("budget            (예산)", budget.check_budget(payload)),
        ("grounding         (이름 창작 여부)", contracts.check_names_are_grounded(payload, source)),
        ("trip_info         (원본 불변)", contracts.check_trip_info_unchanged(payload, source)),
    ]
    for label, found in checks:
        mark = "pass" if not found else f"FAIL ({len(found)}건)"
        print(f"  {label:42} {mark}")
        for violation in found:
            print(f"       - {violation.code}: {violation.message}")

    total = budget.estimate_total(payload)
    trip = payload.trip_info
    stay_sum = sum(
        item.price
        for day in payload.plan.days
        for item in day.items
        if item.category == "숙소"
    )
    print()
    print(f"  예상 비용 합계   {total:>12,.0f} {trip.budget_currency}")
    print(f"  예산            {trip.budget_total:>12,.0f} {trip.budget_currency}")
    print(f"  숙박비 합계      {stay_sum:>12,.0f} {trip.budget_currency}"
          f"  (선택 숙소 총액 {stay['price']:,.0f})" if stay else "")
    print(f"  이동 구간        {diagnostics.total_leg_count}건 "
          f"(좌표 추정 {diagnostics.estimated_leg_count}건)")
    print()
    print(f"  최종: {'검증 통과' if not violations else f'위반 {len(violations)}건'}")

    if args.save:
        Path(args.save).write_text(
            json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  저장: {args.save}")

    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
