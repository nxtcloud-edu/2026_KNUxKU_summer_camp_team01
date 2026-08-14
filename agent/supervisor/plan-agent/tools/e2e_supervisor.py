#!/usr/bin/env python
"""Supervisor의 /agent/plan을 실제로 호출해 전체 파이프라인을 검증한다.

`e2e_check.py`가 Plan Agent 단독을 확인했다면, 이 스크립트는 **supervisor가
실제로 Plan Agent를 HTTP로 호출하고, 그 산출물을 직접 수락 검사하고, 결과를
다시 SSE로 내보내는지**를 확인한다. LangGraph 조건부 분기(`_should_replan`,
START 분기)가 실제로 실행되는 첫 지점이다.

Verification Agent(8003)는 아직 없다. 그 상황에서 supervisor가 죽지 않고
"검증은 건너뛰었어요"로 계속되는지를 함께 확인한다.
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


async def main() -> int:
    from dummy_search_output import make_standard_input

    body = make_standard_input()
    url = "http://127.0.0.1:8000/agent/plan"

    print("=" * 66)
    print("Supervisor 실제 파이프라인 호출 (Verification Agent 없음)")
    print("=" * 66)

    events: list[dict] = []
    started = time.monotonic()

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST", url, json=body, headers={"Accept": "text/event-stream"}
        ) as response:
            print(f"HTTP {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type')}")
            print(f"X-Accel-Buffering: {response.headers.get('x-accel-buffering')}")
            print()

            if response.status_code != 200:
                text = await response.aread()
                print(f"FAIL 본문: {text[:300]}")
                return 1

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
                    extra = f"{event.get('code')}: {event.get('message')} retryable={event.get('retryable')}"
                elif kind == "done":
                    extra = event.get("summary", "")
                print(f"  seq={event.get('seq'):>2} {kind:10} {extra}")

    elapsed = time.monotonic() - started
    print()
    print(f"총 {len(events)}개 이벤트, {elapsed:.2f}초")

    problems: list[str] = []
    if not events:
        problems.append("이벤트 없음")
    else:
        if events[0].get("type") != "status":
            problems.append("첫 이벤트가 status가 아님")
        terminal = [e for e in events if e.get("type") in {"done", "error"}]
        if len(terminal) != 1:
            problems.append(f"종료 이벤트 {len(terminal)}개 (1개여야 함)")

        for index, event in enumerate(events):
            if event.get("seq") != index:
                problems.append(f"seq 불연속: 인덱스 {index}, 실제 {event.get('seq')}")

    done_event = next((e for e in events if e.get("type") == "done"), None)
    error_event = next((e for e in events if e.get("type") == "error"), None)

    if done_event:
        payload = done_event.get("payload", {})
        plan = payload.get("plan")
        verification = payload.get("verification")
        acceptance = payload.get("acceptance", [])
        warnings = payload.get("warnings", [])

        print()
        print("done.payload 구조:")
        print(f"  plan 있음: {plan is not None}")
        if plan:
            days = plan.get("plan", {}).get("days", [])
            print(f"  plan.plan.days: {len(days)}일")
        print(f"  verification: {verification}")
        print(f"  acceptance 리포트 {len(acceptance)}건:")
        for report in acceptance:
            mark = "OK" if report.get("ok") else "FAIL"
            print(f"    [{mark}] {report.get('agent')}: {len(report.get('checked', []))}개 검사")
            for failure in report.get("failures", []):
                print(f"          - {failure}")
        print(f"  warnings: {warnings}")

        if plan is None:
            problems.append("done인데 plan이 없음")
        if verification is not None:
            problems.append("Verification Agent가 없는데 verification이 채워짐")

    if error_event:
        print(f"\nerror: {error_event}")

    print()
    for problem in problems:
        print(f"FAIL  {problem}")
    print("결과:", "PASS" if not problems else "FAIL")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
