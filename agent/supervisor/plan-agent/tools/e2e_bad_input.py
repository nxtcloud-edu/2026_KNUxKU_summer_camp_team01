#!/usr/bin/env python
"""일부러 잘못된 더미데이터로 전체 루프를 검증한다.

Plan -> Verification -> (possible:false면) 피드백 프롬프트 -> 재계획 -> 최종 결과물.

## 시나리오

1. `tight_budget`   — 예산을 실제 비용보다 훨씬 낮게 설정 (BUDGET fail 유도)
2. `closed_day`     — 필수 방문지를 그날 휴무로 설정 (CLOSED_DAY fail 유도, 다만
                       Plan Agent가 스케줄링 단계에서 이미 회피하므로 결과를 본다)
3. `impossible_travel` — 장소들을 지리적으로 멀리 떨어뜨려 이동시간 부족 유도
4. `malformed`      — 계약 자체를 어기는 입력 (필수 필드 누락) -> invalid_input 확인

각 시나리오에서 Plan 산출물, Verification 판정, (필요시) 재계획 후 최종
결과물을 순서대로 출력한다.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE.parent / "tests"))


async def call_supervisor(body: dict, label: str) -> tuple[dict | None, dict | None]:
    """(done.payload, error 이벤트) 튜플을 반환한다."""

    events: list[dict] = []
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            "http://127.0.0.1:8000/agent/plan",
            json=body,
            headers={"Accept": "text/event-stream"},
        ) as response:
            print(f"  [{label}] HTTP {response.status_code}")
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[len("data:") :].strip()
                if not raw:
                    continue
                event = json.loads(raw)
                events.append(event)
                kind = event.get("type")
                extra = ""
                if kind == "status":
                    extra = event.get("text", "")
                elif kind == "progress":
                    extra = str(event.get("value"))
                elif kind == "error":
                    extra = f"{event.get('code')}: {event.get('message')}"
                elif kind == "done":
                    extra = event.get("summary", "")
                print(f"    seq={event.get('seq'):>2} {kind:10} {extra}")

    elapsed = time.monotonic() - started
    print(f"  [{label}] {len(events)}개 이벤트, {elapsed:.2f}초")

    done = next((e for e in events if e.get("type") == "done"), None)
    error = next((e for e in events if e.get("type") == "error"), None)
    return (done.get("payload") if done else None), error


def scenario_tight_budget() -> dict:
    from dummy_search_output import make_standard_input

    body = make_standard_input()
    body["trip_info"]["budget_total"] = 30_000  # 실제 추정 비용(~74만원)의 4%
    return body


def scenario_closed_day() -> dict:
    """필수 방문지(센소지)를 여행 기간 내내 휴무로 만든다.

    Plan Agent의 자기 검증(contracts.check_input_usable)이 이걸 미리 잡아야
    하고, 배치 자체가 실패해야 한다.
    """

    from dummy_search_output import make_standard_input

    body = make_standard_input()
    all_week = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    for place in body["selected"]["places"]:
        if place["name"] == "센소지":
            place["closed_days"] = all_week
    return body


def scenario_impossible_travel() -> dict:
    """장소들을 지구 반대편 좌표로 흩어 놓아 이동시간을 극단적으로 늘린다.

    하루 시간대(09:00-22:00, 13시간) 안에 못 들어갈 만큼 먼 거리를 만든다.
    """

    from dummy_search_output import make_standard_input

    body = make_standard_input()
    # 위경도를 교대로 아주 멀게 벌린다 (도쿄 vs 뉴욕 근처 좌표 흉내).
    for index, place in enumerate(body["selected"]["places"]):
        if index % 2 == 1:
            place["lat"] = 40.7128
            place["lng"] = -74.0060
    return body


def scenario_malformed() -> dict:
    """계약 자체를 어기는 입력. trip_info가 없다."""

    return {"schema_version": "1.0", "selected": {"flight": None, "stay": None, "places": []}}


async def run_scenario(name: str, body_factory) -> None:
    print()
    print("=" * 70)
    print(f"시나리오: {name}")
    print("=" * 70)
    body = body_factory()
    payload, error = await call_supervisor(body, name)

    if error is not None:
        print(f"  -> error 이벤트로 종료: {error}")
        return

    if payload is None:
        print("  -> FAIL: done도 error도 없음 (계약 위반)")
        return

    plan = payload.get("plan")
    verification = payload.get("verification")
    acceptance = payload.get("acceptance", [])
    warnings = payload.get("warnings", [])

    if plan is not None:
        days = plan.get("plan", {}).get("days", [])
        item_count = sum(len(d.get("items", [])) for d in days)
        print(f"  최종 일정: {len(days)}일 {item_count}항목")
    else:
        print("  최종 일정: 없음")

    if verification is not None:
        print(f"  verification.possible: {verification.get('possible')}")
        for check_name, check in verification.get("checks", {}).items():
            status = check.get("status")
            if status in {"fail", "warning"}:
                print(f"    - {check_name}: {status}")
    else:
        print("  verification: 없음")

    print(f"  acceptance: {[(r['agent'], r['ok']) for r in acceptance]}")
    print(f"  warnings: {warnings}")


async def main() -> int:
    await run_scenario("1_예산_부족", scenario_tight_budget)
    await run_scenario("2_필수방문지_휴무", scenario_closed_day)
    await run_scenario("3_이동불가_거리", scenario_impossible_travel)
    await run_scenario("4_계약위반_입력", scenario_malformed)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
