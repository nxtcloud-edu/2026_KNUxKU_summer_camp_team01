#!/usr/bin/env python
"""더미 시나리오의 입력·출력을 파일로 저장한다.

## 왜 저장하는가

세 에이전트가 각각 다른 담당자 손에 있고 나중에 합친다. 그때 필요한 것은
**"Plan Agent에 이걸 넣으면 저게 나온다"는 구체적인 예시**다. 말로 설명하는
것보다 실제 JSON 한 쌍이 훨씬 정확하다.

| 쓰는 사람 | 쓰는 방법 |
|---|---|
| Search Agent 담당 | `*.search-input.json`을 목표 출력 형태로 삼는다 |
| Verification Agent 담당 | `*.plan-output.json`을 `POST /agent/itineraryVerify`에 그대로 넣는다 |
| 프론트엔드 담당 | `*.plan-output.json`으로 화면을 그려본다 |
| Plan Agent (나) | 회귀 테스트 기준값으로 쓴다 |

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

DEFAULT_OUT = _HERE.parent / "samples"


def _write(path: Path, data: object) -> int:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", default=str(DEFAULT_OUT), help="저장 디렉터리"
    )
    parser.add_argument(
        "--live", action="store_true", help="실제 API 호출 (과금 발생, 결과 비결정론)"
    )
    args = parser.parse_args()

    if not args.live:
        os.environ["ROUTES_ENABLED"] = "off"
        os.environ["GEMINI_API_KEY"] = ""
    logging.basicConfig(level=logging.ERROR, format="  %(levelname)s %(message)s")

    from dummy_search_output import SCENARIOS, make_search_output
    from plan_agent import budget, contracts
    from plan_agent.graph import generate_itinerary
    from plan_agent.models import SearchToPlanInput
    from plan_agent.routing import clear_cache

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    index: list[dict] = []
    failures = 0

    print(f"저장 위치: {out_dir}")
    print(
        "외부 API 호출 없음 (결정론)"
        if not args.live
        else "!! 실제 API 호출 — 결과가 매번 달라질 수 있습니다"
    )
    print()

    for name, kwargs in SCENARIOS.items():
        clear_cache()
        source_raw = make_search_output(**kwargs)
        source = SearchToPlanInput.model_validate(source_raw)

        payload, diagnostics = await generate_itinerary(source)

        stem = name.replace(" ", "_")
        in_path = out_dir / f"{stem}.search-input.json"
        _write(in_path, source_raw)

        entry: dict = {
            "scenario": name,
            "search_input": in_path.name,
            "date_range": f"{source_raw['trip_info']['start_date']} ~ "
            f"{source_raw['trip_info']['end_date']}",
            "selected_places": len(source_raw["selected"]["places"]),
            "pace": source_raw["trip_info"]["persona"]["pace"],
            "transport_mode": source_raw["trip_info"]["transport_mode"],
        }

        if payload is None:
            failures += 1
            reason = [
                {"code": v.code, "message": v.message}
                for v in diagnostics.violations
            ]
            fail_path = out_dir / f"{stem}.plan-failure.json"
            _write(fail_path, {"scenario": name, "violations": reason})
            entry.update(
                {"result": "failure", "plan_output": None, "detail": fail_path.name}
            )
            index.append(entry)
            print(f"  실패  {name:12} -> {fail_path.name}")
            continue

        handoff = payload.model_dump(mode="json")
        out_path = out_dir / f"{stem}.plan-output.json"
        _write(out_path, handoff)

        violations = contracts.verify_all(payload, source)
        total = budget.estimate_total(payload)
        item_count = sum(len(day.items) for day in payload.plan.days)
        stay_sum = sum(
            item.price
            for day in payload.plan.days
            for item in day.items
            if item.category == "숙소"
        )

        entry.update(
            {
                "result": "pass" if not violations else "violations",
                "plan_output": out_path.name,
                "day_count": len(payload.plan.days),
                "item_count": item_count,
                "estimated_total": total,
                "budget_total": payload.trip_info.budget_total,
                "stay_price_sum": stay_sum,
                "travel_legs": diagnostics.total_leg_count,
                "estimated_legs": diagnostics.estimated_leg_count,
                "violations": [
                    {"code": v.code, "message": v.message} for v in violations
                ],
                "unassigned": [
                    {"place": u.place_name, "reason": u.reason}
                    for u in diagnostics.unassigned
                ],
                "notes": diagnostics.notes,
            }
        )
        index.append(entry)
        if violations:
            failures += 1
        mark = "통과" if not violations else f"위반{len(violations)}"
        print(
            f"  {mark:6} {name:12} {len(payload.plan.days)}일 {item_count:2}항목 "
            f"-> {out_path.name}"
        )

    index_path = out_dir / "index.json"
    _write(
        index_path,
        {
            "generated_by": "agent/supervisor/plan-agent/tools/save_samples.py",
            "live_api": args.live,
            "note": (
                "Search Agent 더미 입력과 그에 대한 Plan Agent 산출물 쌍. "
                "plan-output.json은 Verification Agent의 "
                "POST /agent/itineraryVerify에 그대로 넣을 수 있다."
            ),
            "scenarios": index,
        },
    )

    print()
    print(f"  목록  index.json ({len(index)}개 시나리오)")
    print(f"결과: {len(index) - failures}/{len(index)} 통과")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
