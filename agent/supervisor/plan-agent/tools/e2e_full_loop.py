#!/usr/bin/env python
"""전체 루프 실제 검증: 더미 -> Plan -> Verification -> 피드백 -> 재계획 -> 최종 결과물.

세 서버(plan:8001, verification:8003, supervisor:8000)가 모두 실제로 떠 있는
상태에서, Verification이 `possible:false`를 내도록 일부러 어려운 입력을 만들어
supervisor의 자동 재계획 경로(`_should_replan` -> `_replan` ->
`itineraryReplan`)를 실제로 통과시킨다.

지금까지 이 경로는 Verification Agent가 없어서 한 번도 실행된 적이 없었다.
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


async def call_supervisor(body: dict, label: str) -> dict | None:
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
    if error:
        print(f"  [{label}] error: {error}")
        return None
    return done.get("payload") if done else None


def make_tight_budget_input() -> dict:
    """예산을 극단적으로 낮게 잡아 verification이 possible:false를 내게 한다."""

    from dummy_search_output import make_standard_input

    body = make_standard_input()
    # 실제 추정 비용(약 74만원)보다 훨�c씬 낮게 잡아 BUDGET fail을 확실히 유도한다.
    body["trip_info"]["budget_total"] = 50_000
    return body


async def main() -> int:
    print("=" * 70)
    print("1단계: 더미 입력 생성 (예산을 일부러 빡빡하게)")
    print("=" * 70)
    body = make_tight_budget_input()
    print(f"  목적지: {body['trip_info']['destination']}")
    print(f"  예산: {body['trip_info']['budget_total']:,.0f} {body['trip_info']['budget_currency']}")
    print(f"  선택 장소: {len(body['selected']['places'])}곳")
    print()

    print("=" * 70)
    print("2단계: Supervisor에 최초 요청 (Plan -> Verification -> 자동 재계획 기대)")
    print("=" * 70)
    payload = await call_supervisor(body, "initial")
    if payload is None:
        print("FAIL: 최초 요청에서 payload를 받지 못함")
        return 1

    plan = payload.get("plan")
    verification = payload.get("verification")
    warnings = payload.get("warnings", [])

    print()
    print("=" * 70)
    print("3단계: 결과 분석")
    print("=" * 70)
    if plan is None:
        print("FAIL: plan이 없음")
        return 1

    days = plan.get("plan", {}).get("days", [])
    item_count = sum(len(d.get("items", [])) for d in days)
    print(f"  최종 일정: {len(days)}일 {item_count}항목")
    print(f"  verification.possible: {verification.get('possible') if verification else None}")
    if verification:
        budget_check = verification.get("checks", {}).get("budget", {})
        print(
            f"  예산 검사: {budget_check.get('status')} "
            f"(추정 {budget_check.get('estimated_total', 0):,.0f} / "
            f"예산 {budget_check.get('budget_total', 0):,.0f}, "
            f"초과 {budget_check.get('over_by', 0):,.0f})"
        )
    print(f"  경고: {warnings}")

    print()
    print("=" * 70)
    print("4단계: 사용자 재요청 시뮬레이션 (previous_plan과 함께 다시 호출)")
    print("=" * 70)
    # supervisor.main은 /agent/plan에서 previous_plan을 받는 경로가 없으므로
    # (현재는 항상 새로 생성), 재계획 자체가 이미 1단계에서 자동으로 시도됐는지
    # 로그로 확인한다. 여기서는 동일 입력으로 한 번 더 호출해 결정론성을 본다.
    payload2 = await call_supervisor(body, "second-call")
    if payload2 is None:
        print("FAIL: 두 번째 호출 실패")
        return 1
    days2 = payload2.get("plan", {}).get("plan", {}).get("days", [])
    print(f"  두 번째 호출 결과: {len(days2)}일, 첫 호출과 동일 구조: {len(days2) == len(days)}")

    print()
    print("=" * 70)
    print("최종 결과물 (plan-to-verification.output.json 형태)")
    print("=" * 70)
    print(json.dumps(plan, ensure_ascii=False, indent=2)[:2000])
    print("... (이하 생략)")

    out_path = _HERE.parent.parent.parent.parent / "data" / "sample" / "e2e-final-result.json"
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print()
    print(f"전체 결과 저장: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
