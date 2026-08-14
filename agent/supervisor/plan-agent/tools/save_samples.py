#!/usr/bin/env python
"""표준 더미 입력을 Plan Agent에 넣고 입출력 쌍을 `data/sample/`에 저장한다.

## 왜 저장하는가

세 에이전트가 각각 다른 담당자 손에 있고 나중에 합친다. 그때 필요한 것은
**"Plan Agent에 이걸 넣으면 저게 나온다"는 구체적인 예시**다. 말로 설명하는
것보다 실제 JSON 한 쌍이 훨씬 정확하다.

| 쓰는 사람 | 쓰는 방법 |
|---|---|
| Search Agent 담당 | `search-to-plan.input.json`을 목표 출력 형태로 삼는다 |
| Verification Agent 담당 | `plan-to-verification.output.json`을 `POST /agent/itineraryVerify`에 넣는다 |
| 프론트엔드 담당 | 같은 파일로 화면을 그려본다 |

## 입력 하나, 출력 하나

페이스별로 여러 안을 만들지 않는다. `pace`·`must_visit`·`avoid` 같은 성향은
프론트엔드 웹사이트가 사용자에게서 받는 값이고, Search Agent는 항공편·숙소·
장소 후보만 찾는다. Plan Agent는 둘을 합쳐 **일정 하나**를 만든다.

## 사용법

    python agent/supervisor/plan-agent/tools/save_samples.py

외부 API를 호출하지 않으므로 과금이 없고, 같은 입력이면 항상 같은 결과가
나온다(결정론). 그래서 파일을 커밋해도 무의미한 diff가 생기지 않는다.
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


def _repo_root() -> Path:
    """`agent/` 디렉터리를 가진 저장소 루트를 찾는다."""

    for candidate in _HERE.parents:
        if (candidate / "agent" / "schemas").is_dir():
            return candidate
    raise SystemExit("저장소 루트를 찾지 못했습니다")


DEFAULT_OUT = _repo_root() / "data" / "sample"


def _write(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="저장 디렉터리")
    parser.add_argument(
        "--live", action="store_true", help="실제 API 호출 (과금 발생, 결과 비결정론)"
    )
    args = parser.parse_args()

    if not args.live:
        os.environ["ROUTES_ENABLED"] = "off"
        os.environ["GEMINI_API_KEY"] = ""
    logging.basicConfig(level=logging.ERROR, format="  %(levelname)s %(message)s")

    from dummy_search_output import STANDARD_INPUT, make_standard_input
    from plan_agent import budget, contracts
    from plan_agent.graph import generate_itinerary
    from plan_agent.models import SearchToPlanInput
    from plan_agent.routing import clear_cache

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"저장 위치: {out_dir}")
    print(
        "외부 API 호출 없음 (결정론)"
        if not args.live
        else "!! 실제 API 호출 — 결과가 매번 달라질 수 있습니다"
    )
    print()

    clear_cache()
    source_raw = make_standard_input()
    source = SearchToPlanInput.model_validate(source_raw)

    in_path = out_dir / "search-to-plan.input.json"
    _write(in_path, source_raw)
    print(f"  입력  {in_path.name}")
    print(
        f"        {source.trip_info.destination} "
        f"{source.trip_info.start_date}~{source.trip_info.end_date} "
        f"장소 {len(source.selected.places)}곳 "
        f"페이스 {source.trip_info.persona.pace}"
    )

    payload, diagnostics = await generate_itinerary(source)

    if payload is None:
        fail_path = out_dir / "plan-to-verification.failure.json"
        _write(
            fail_path,
            {
                "violations": [
                    {"code": v.code, "message": v.message}
                    for v in diagnostics.violations
                ]
            },
        )
        print(f"  실패  {fail_path.name}")
        for violation in diagnostics.violations:
            print(f"        {violation.code}: {violation.message}")
        return 1

    out_path = out_dir / "plan-to-verification.output.json"
    _write(out_path, payload.model_dump(mode="json"))

    violations = contracts.verify_all(payload, source)
    total = budget.estimate_total(payload)
    item_count = sum(len(day.items) for day in payload.plan.days)
    stay_sum = sum(
        item.price
        for day in payload.plan.days
        for item in day.items
        if item.category == "숙소"
    )
    per_day = [
        len([item for item in day.items if item.category != "숙소"])
        for day in payload.plan.days
    ]

    print(f"  출력  {out_path.name}")
    print(f"        {len(payload.plan.days)}일 {item_count}항목  하루 장소 수 {per_day}")
    print(
        f"        비용 {total:,.0f} / 예산 {payload.trip_info.budget_total:,.0f} "
        f"{payload.trip_info.budget_currency}"
    )
    print(
        f"        숙박비 합계 {stay_sum:,.0f} "
        f"(선택 숙소 총액 {source.selected.stay.price:,.0f})"
        if source.selected.stay
        else ""
    )
    print(
        f"        이동 {diagnostics.total_leg_count}건 "
        f"(좌표 추정 {diagnostics.estimated_leg_count}건)"
    )

    meta_path = out_dir / "meta.json"
    _write(
        meta_path,
        {
            "generated_by": "agent/supervisor/plan-agent/tools/save_samples.py",
            "live_api": args.live,
            "note": (
                "Search Agent 더미 입력과 그에 대한 Plan Agent 산출물. "
                "plan-to-verification.output.json은 Verification Agent의 "
                "POST /agent/itineraryVerify에 그대로 넣을 수 있다."
            ),
            "input_summary": {
                "destination": source.trip_info.destination,
                "date_range": f"{source.trip_info.start_date} ~ {source.trip_info.end_date}",
                "selected_places": len(source.selected.places),
                "pace": source.trip_info.persona.pace,
                "max_walking_level": source.trip_info.persona.max_walking_level,
                "must_visit": source.trip_info.persona.must_visit,
                "transport_mode": source.trip_info.transport_mode,
                "has_flight": source.selected.flight is not None,
                "has_stay": source.selected.stay is not None,
            },
            "output_summary": {
                "day_count": len(payload.plan.days),
                "item_count": item_count,
                "places_per_day": per_day,
                "estimated_total": total,
                "budget_total": payload.trip_info.budget_total,
                "budget_currency": payload.trip_info.budget_currency,
                "stay_price_sum": stay_sum,
                "travel_legs": diagnostics.total_leg_count,
                "estimated_legs": diagnostics.estimated_leg_count,
            },
            "verification": {
                "passed": not violations,
                "violations": [
                    {"code": v.code, "message": v.message} for v in violations
                ],
            },
            "unassigned": [
                {"place": u.place_name, "reason": u.reason}
                for u in diagnostics.unassigned
            ],
            "notes": diagnostics.notes,
        },
    )
    print(f"  요약  {meta_path.name}")

    for note in diagnostics.notes:
        print(f"        메모: {note}")
    for item in diagnostics.unassigned:
        print(f"        미배치: {item.place_name} — {item.reason}")

    print()
    print(f"결과: {'검증 통과' if not violations else f'위반 {len(violations)}건'}")
    for violation in violations:
        print(f"  {violation.code}: {violation.message}")
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
