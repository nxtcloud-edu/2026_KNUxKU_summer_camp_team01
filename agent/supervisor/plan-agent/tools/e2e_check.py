#!/usr/bin/env python
"""실행 중인 서버에 실제 HTTP 요청을 보내 SSE 계약을 검증한다.

단위 테스트와 다르다. 단위 테스트는 함수를 직접 부른다. 이 도구는 **실제로
소켓을 열고, 실제 FastAPI 라우터를 거치고, 실제 SSE 프레이밍을 파싱**한다.
"코드가 있다"와 "떠 있는 서버가 계약대로 응답한다"는 다른 주장이고, 이 도구는
후자만 확인한다.

## 확인하는 것

1. HTTP 200 + `text/event-stream`
2. 헤더에 `X-Accel-Buffering: no` (없으면 스트리밍이 프록시에서 사라진다)
3. 첫 이벤트가 `status`
4. `seq`가 0부터 1씩 증가 (건너뛰거나 중복되지 않음)
5. 종료 이벤트가 `done` 또는 `error` 정확히 하나
6. `done.payload`가 실제로 Pydantic 계약을 통과하는가

## 사용법

    python agent/supervisor/plan-agent/tools/e2e_check.py --target plan
    python agent/supervisor/plan-agent/tools/e2e_check.py --target plan --endpoint itineraryReplan
    python agent/supervisor/plan-agent/tools/e2e_check.py --target supervisor
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE.parent / "tests"))


async def stream_and_check(url: str, body: dict, *, label: str) -> tuple[bool, dict | None, list[str]]:
    """SSE 스트림을 실제로 열어 계약을 검사한다.

    반환: (통과 여부, done.payload 또는 None, 문제 목록)
    """

    problems: list[str] = []
    events: list[dict] = []
    started = time.monotonic()
    first_event_at: float | None = None

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST", url, json=body, headers={"Accept": "text/event-stream"}
        ) as response:
            print(f"  [{label}] HTTP {response.status_code}")
            if response.status_code != 200:
                text = await response.aread()
                problems.append(f"HTTP {response.status_code}: {text[:200]}")
                return False, None, problems

            content_type = response.headers.get("content-type", "")
            if "text/event-stream" not in content_type:
                problems.append(f"Content-Type이 SSE가 아님: {content_type!r}")

            buffering = response.headers.get("x-accel-buffering", "")
            if buffering.lower() != "no":
                problems.append(
                    f"X-Accel-Buffering: no 헤더 없음 (실제 {buffering!r}) "
                    "— 중간 프록시에서 스트리밍이 사라질 수 있음"
                )
            else:
                print(f"  [{label}] X-Accel-Buffering: no 확인")

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[len("data:") :].strip()
                if not raw:
                    continue
                if first_event_at is None:
                    first_event_at = time.monotonic()
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    problems.append(f"JSON 파싱 실패: {raw[:100]}")
                    continue
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
                print(f"    seq={event.get('seq'):>2} {kind:10} {extra}"[:100])

    elapsed = time.monotonic() - started
    first_latency_ms = (
        int((first_event_at - started) * 1000) if first_event_at else None
    )

    if not events:
        problems.append("이벤트를 하나도 받지 못함")
        return False, None, problems

    if events[0].get("type") != "status":
        problems.append(f"첫 이벤트가 status가 아님: {events[0].get('type')!r}")

    expected_seq = 0
    for event in events:
        if event.get("seq") != expected_seq:
            problems.append(
                f"seq 불연속: 기대 {expected_seq}, 실제 {event.get('seq')}"
            )
        expected_seq += 1

    terminal_types = [e.get("type") for e in events if e.get("type") in {"done", "error"}]
    if len(terminal_types) != 1:
        problems.append(f"종료 이벤트가 정확히 1개가 아님: {terminal_types}")
    elif terminal_types[0] != events[-1].get("type"):
        problems.append("종료 이벤트가 마지막 이벤트가 아님")

    if first_latency_ms is not None and first_latency_ms > 1000:
        problems.append(f"첫 이벤트까지 {first_latency_ms}ms (권고 1000ms 이내)")

    print(f"  [{label}] 총 {len(events)}개 이벤트, {elapsed:.2f}초, 첫 이벤트 {first_latency_ms}ms")

    done_payload = None
    for event in events:
        if event.get("type") == "done":
            done_payload = event.get("payload")

    return not problems, done_payload, problems


async def check_plan_generate(base_url: str) -> bool:
    from dummy_search_output import make_standard_input

    body = make_standard_input()
    ok, payload, problems = await stream_and_check(
        f"{base_url}/agent/itineraryGenerate", body, label="plan.generate"
    )

    if payload is not None:
        from plan_agent.models import PlanToVerificationInput
        from plan_agent import contracts
        from plan_agent.models import SearchToPlanInput

        try:
            parsed = PlanToVerificationInput.model_validate(payload)
            print(
                f"  [plan.generate] payload 계약 통과: "
                f"{len(parsed.plan.days)}일 "
                f"{sum(len(d.items) for d in parsed.plan.days)}항목"
            )
            source = SearchToPlanInput.model_validate(body)
            violations = contracts.verify_all(parsed, source)
            if violations:
                problems.append(f"검증 위반 {len(violations)}건: {[v.code for v in violations]}")
            else:
                print("  [plan.generate] 자기 검증 통과")
        except Exception as exc:
            problems.append(f"payload가 계약을 통과하지 못함: {exc}")

    for problem in problems:
        print(f"  FAIL  {problem}")
    print(f"  결과: {'PASS' if ok and not problems else 'FAIL'}")
    return ok and not problems and payload is not None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["plan", "supervisor"], default="plan")
    parser.add_argument("--plan-url", default="http://127.0.0.1:8001")
    parser.add_argument("--supervisor-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    print("=" * 66)
    print(f"실제 서버 E2E 검증 대상: {args.target}")
    print("=" * 66)

    if args.target == "plan":
        ok = await check_plan_generate(args.plan_url)
        return 0 if ok else 1

    print("supervisor 검증은 이 스크립트의 다음 단계에서 처리합니다.")
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
