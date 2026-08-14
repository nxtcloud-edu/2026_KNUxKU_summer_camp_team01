#!/usr/bin/env python
"""`plan-to-verification.example.json`에서 `search-to-plan.example.json`을 생성한다.

## 왜 생성하는가

`conformance.mjs`가 두 fixture를 교차 검사한다.

- 두 fixture의 `trip_info`가 deepEqual이어야 한다
- plan의 모든 항목 이름이 search의 선택 결과에 있어야 한다
- search의 `must_visit`이 선택 장소에 있어야 한다

사람이 두 파일을 손으로 맞추면 반드시 어긋난다. plan 쪽을 정본으로 두고
search 쪽을 **파생**시키면 어긋날 수 없다.

## 사용법

    python agent/supervisor/plan-agent/tools/sync_search_fixture.py
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _find_agent_root() -> Path:
    for candidate in _HERE.parents:
        if (candidate / "schemas").is_dir() and (candidate / "fixtures").is_dir():
            return candidate
    raise SystemExit("agent 루트를 찾지 못했습니다")


AGENT_ROOT = _find_agent_root()
FIXTURES = AGENT_ROOT / "fixtures"
PLAN_FIXTURE = FIXTURES / "plan-to-verification.example.json"
SEARCH_FIXTURE = FIXTURES / "search-to-plan.example.json"

# 계약의 place id 패턴: ^[A-Za-z0-9][A-Za-z0-9_-]*$
# 한국어 이름을 그대로 쓸 수 없으므로 순번 기반 id를 만든다.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _place_id(index: int) -> str:
    return f"tokyo-place-{index:02d}"


def main() -> int:
    plan = json.loads(PLAN_FIXTURE.read_text("utf-8"))
    trip_info = plan["trip_info"]

    places: list[dict] = []
    stay: dict | None = None
    seen_names: set[str] = set()
    counter = 0

    for day in plan["plan"]["days"]:
        for item in day["items"]:
            name = item["name"]
            if name in seen_names:
                continue
            seen_names.add(name)

            if item["category"] == "숙소":
                # 숙소는 SelectedStay로 옮긴다. Plan Agent가 category와
                # opening_hours를 합성하므로 그 필드는 넘기지 않는다.
                check_in = "15:00"
                match = re.search(r"([01]\d|2[0-3]):([0-5]\d)", item["opening_hours"])
                if match:
                    check_in = match.group(0)
                stay = {
                    "id": "stay-shibuya",
                    "name": name,
                    "lat": item["lat"],
                    "lng": item["lng"],
                    "price": item["price"],
                    "price_unit": "per_stay",
                    "check_in_time": check_in,
                    "check_out_time": "11:00",
                    "note": item["note"],
                }
                continue

            counter += 1
            place = {
                "id": _place_id(counter),
                "name": name,
                "category": item["category"],
                "lat": item["lat"],
                "lng": item["lng"],
                "price": item["price"],
                "price_unit": item["price_unit"],
                "opening_hours": item["opening_hours"],
                "closed_days": list(item["closed_days"]),
                "expected_duration_min": item["expected_duration_min"],
                "physical_intensity": item["physical_intensity"],
                "note": item["note"],
            }
            assert _ID_PATTERN.match(place["id"]), place["id"]
            places.append(place)

    search = {
        "schema_version": "1.0",
        # 그대로 복사한다. 한 글자도 달라지면 cross-handoff 검사가 깨진다.
        "trip_info": trip_info,
        "selected": {
            "flight": None,
            "stay": stay,
            "places": places,
        },
    }

    SEARCH_FIXTURE.write_text(
        json.dumps(search, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"생성: {SEARCH_FIXTURE.relative_to(AGENT_ROOT.parent)}")
    print(f"  장소 {len(places)}곳, 숙소 {'있음' if stay else '없음'}")

    # 교차 검사 조건을 여기서도 확인한다.
    problems: list[str] = []
    available = {place["name"] for place in places}
    if stay:
        available.add(stay["name"])
    for day in plan["plan"]["days"]:
        for item in day["items"]:
            if item["name"] not in available:
                problems.append(f"plan 항목 '{item['name']}'이 선택 결과에 없음")
    for required in trip_info["persona"]["must_visit"]:
        if required not in available:
            problems.append(f"필수 방문지 '{required}'가 선택 결과에 없음")
    if search["trip_info"] != trip_info:
        problems.append("trip_info가 달라짐")

    if problems:
        for problem in problems:
            print(f"  FAIL {problem}")
        return 1
    print("  교차 검사 조건 충족")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
