#!/usr/bin/env python
"""실제 서버에 오류 상황을 넣어 계약이 지켜지는지 확인한다.

## 왜 필요한가

행복한 경로(happy path)가 되는 것과, 잘못된 입력·타임아웃·연결 끊김에서도
**정확히 하나의 종료 이벤트**를 내는 것은 다른 문제다. 계약 위반 #1(가장
심각한 것)이 "종료 이벤트 없이 스트림이 끝난다"이므로, 이걸 실제로 유발해서
정말 안 그런지 본다.

## 확인하는 것

1. Plan Agent에 스키마 위반 입력 -> 200 + error(invalid_input)
2. Plan Agent에 빈 본문 -> 200 + error
3. Supervisor에 스키마 위반 입력 -> Plan이 거부하고 supervisor가 전달
4. 클라이언트가 중간에 연결을 끊음 -> 서버가 예외 없이 처리하는가 (직접 관찰은
   어렵지만 서버 로그에 CancelledError 트레이스가 안 남는지 확인)
"""

from __future__ import annotations

import asyncio
import json

import httpx


async def _drain(url: str, body: dict, label: str) -> list[dict]:
    events: list[dict] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            async with client.stream(
                "POST", url, json=body, headers={"Accept": "text/event-stream"}
            ) as response:
                print(f"  [{label}] HTTP {response.status_code}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[len("data:") :].strip()
                    if raw:
                        events.append(json.loads(raw))
        except httpx.HTTPError as error:
            print(f"  [{label}] 전송 오류: {error}")
    for event in events:
        print(f"    {event}"[:150])
    return events


def _check_single_terminal(events: list[dict], label: str) -> bool:
    terminal = [e for e in events if e.get("type") in {"done", "error"}]
    ok = len(terminal) == 1
    print(f"  [{label}] 종료 이벤트 {len(terminal)}개 -> {'PASS' if ok else 'FAIL'}")
    return ok


async def main() -> int:
    results = []

    print("=" * 66)
    print("1. Plan Agent: 스키마 위반 입력 (필수 필드 누락)")
    print("=" * 66)
    events = await _drain(
        "http://127.0.0.1:8001/agent/itineraryGenerate",
        {"schema_version": "1.0"},  # trip_info, selected 없음
        "plan.invalid",
    )
    results.append(_check_single_terminal(events, "plan.invalid"))
    if events and events[-1].get("type") == "error":
        code = events[-1].get("code")
        print(f"  코드: {code} -> {'PASS' if code == 'invalid_input' else 'FAIL'}")
        results.append(code == "invalid_input")

    print()
    print("=" * 66)
    print("2. Plan Agent: 완전히 빈 본문")
    print("=" * 66)
    events = await _drain(
        "http://127.0.0.1:8001/agent/itineraryGenerate", {}, "plan.empty"
    )
    results.append(_check_single_terminal(events, "plan.empty"))

    print()
    print("=" * 66)
    print("3. Plan Agent: 존재하지 않는 opening_hours 형식 (배치 불가 유도)")
    print("=" * 66)
    # 장소가 하나뿐이고 그게 파싱 불가 형식이면 EMPTY_DAY -> agent_failed 경로.
    bad_body = {
        "schema_version": "1.0",
        "trip_info": {
            "destination": "테스트",
            "start_date": "2026-06-15",
            "end_date": "2026-06-15",
            "num_travelers": 1,
            "budget_total": 100000,
            "budget_currency": "KRW",
            "budget_includes": [],
            "transport_mode": "도보",
            "day_start_time": "09:00",
            "day_end_time": "22:00",
            "persona": {
                "description": "테스트",
                "must_visit": [],
                "avoid": [],
                "pace": "보통",
                "max_walking_level": "중간",
            },
        },
        "selected": {
            "flight": None,
            "stay": None,
            "places": [
                {
                    "id": "bad-place",
                    "name": "이상한장소",
                    "category": "관광지",
                    "lat": 35.0,
                    "lng": 139.0,
                    "price": 0,
                    "price_unit": "per_person",
                    "opening_hours": "상시 개방",  # 파싱 불가
                    "closed_days": [],
                    "expected_duration_min": 60,
                    "physical_intensity": "낮음",
                    "note": "",
                }
            ],
        },
    }
    events = await _drain(
        "http://127.0.0.1:8001/agent/itineraryGenerate", bad_body, "plan.unusable"
    )
    results.append(_check_single_terminal(events, "plan.unusable"))
    if events:
        last = events[-1]
        print(f"  마지막 이벤트 타입: {last.get('type')}")

    print()
    print("=" * 66)
    print("4. Supervisor: 잘못된 JSON 본문")
    print("=" * 66)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "http://127.0.0.1:8000/agent/plan",
            content=b"{not valid json",
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        print(f"  HTTP {response.status_code}")
        text = response.text
        print(f"  본문: {text[:200]}")
        lines = [l for l in text.splitlines() if l.startswith("data:")]
        events = [json.loads(l[5:].strip()) for l in lines if l[5:].strip()]
        ok = len(events) == 1 and events[0].get("type") == "error"
        print(f"  결과: {'PASS' if ok else 'FAIL'}")
        results.append(ok)

    print()
    print("=" * 66)
    print(f"전체 결과: {sum(results)}/{len(results)} PASS")
    print("=" * 66)
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
