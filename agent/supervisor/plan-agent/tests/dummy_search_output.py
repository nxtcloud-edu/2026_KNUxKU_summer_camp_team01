"""Plan Agent 입력(`SearchToPlanInput`) 더미 생성기.

실제 Search Agent와 프론트엔드는 다른 담당자가 만들고 있다. 그때까지 Plan
Agent를 테스트하려면 입력을 만들어 줄 무언가가 필요하다.

## 이 입력은 두 곳에서 합쳐진 것이다

`SearchToPlanInput`은 한 에이전트의 산출물이 아니다. 두 출처가 합쳐진다.

| 블록 | 만드는 곳 | 내용 |
|---|---|---|
| `trip_info` | **프론트엔드 웹사이트** | 목적지·날짜·인원·예산·이동수단·하루 시간대, 그리고 `persona`(설명·필수방문·회피·페이스·활동강도) |
| `selected` | **Search Agent** | 항공편·숙소·장소 후보 정보 |

즉 사용자 선호를 묻는 것은 프론트엔드의 일이고, Search Agent는 그 조건을
받아 **항공편·숙소·여행장소 정보만** 수집한다. Plan Agent는 둘을 합쳐 받는다.

이 더미는 그 합쳐진 결과를 한 번에 만든다.

## 이 더미가 지키는 것

`agent/schemas/search-to-plan.schema.json`을 그대로 만족한다. 특히 실제
Search Agent가 지켜야 할 두 가지를 여기서도 지킨다.

1. **`opening_hours`는 검증 에이전트가 파싱할 수 있는 형식만 쓴다.**
   `HH:MM-HH:MM` 또는 `HH:MM 이후`. `화-일 09:30-17:00` 같은 문자열을 주면
   그 장소는 어디에 배치해도 `INVALID_OPENING_HOURS`로 fail이 된다.
2. **좌표가 실제 위치와 맞는다.** 좌표가 틀리면 이동시간과 경로가 전부
   무의미해진다.

## 좌표는 실제 도쿄 명소 값이다

추정 이동시간이 현실적으로 나오는지 보려면 실제 좌표가 필요하다. 임의의
숫자를 쓰면 "지하철 3분" 같은 값이 나와서 검증이 의미를 잃는다.
"""

from __future__ import annotations

from typing import Any

# 실제 도쿄 명소 좌표. (이름, 위도, 경도, 카테고리, 영업시간, 체류분, 요금, 강도)
TOKYO_PLACES: list[tuple[str, float, float, str, str, int, float, str]] = [
    ("센소지", 35.7148, 139.7967, "관광지", "06:00-17:00", 90, 0, "중간"),
    ("도쿄 국립박물관", 35.7188, 139.7765, "관광지", "09:30-17:00", 120, 1000, "낮음"),
    ("우에노 공원", 35.7141, 139.7744, "휴식", "05:00-23:00", 60, 0, "낮음"),
    ("도쿄 스카이트리", 35.7101, 139.8107, "관광지", "10:00-21:00", 90, 2100, "낮음"),
    ("아사쿠사 멘치카츠", 35.7118, 139.7955, "식사", "10:00-19:00", 45, 800, "낮음"),
    ("츠키지 장외시장", 35.6654, 139.7707, "식사", "05:00-14:00", 75, 3000, "중간"),
    ("하마리큐 정원", 35.6603, 139.7630, "휴식", "09:00-17:00", 60, 300, "낮음"),
    ("도쿄 타워", 35.6586, 139.7454, "관광지", "09:00-22:00", 75, 1200, "낮음"),
    ("메이지 신궁", 35.6764, 139.6993, "관광지", "05:00-18:00", 80, 0, "중간"),
    ("시부야 스카이", 35.6580, 139.7016, "관광지", "10:00-22:00", 70, 2200, "낮음"),
    ("타케시타 거리", 35.6716, 139.7031, "쇼핑", "10:00-20:00", 60, 0, "중간"),
    ("신주쿠 교엔", 35.6852, 139.7100, "휴식", "09:00-16:00", 70, 500, "낮음"),
    ("오모테산도 카페", 35.6654, 139.7124, "카페", "08:00-19:00", 45, 900, "낮음"),
    ("긴자 미쓰코시", 35.6717, 139.7650, "쇼핑", "10:00-20:00", 90, 0, "낮음"),
    ("아키하바라 전자상가", 35.6987, 139.7730, "쇼핑", "11:00-20:00", 90, 0, "중간"),
]

DEFAULT_STAY: dict[str, Any] = {
    "id": "stay-gracery-shinjuku",
    "name": "호텔 그레이스리 신주쿠",
    "lat": 35.6955,
    "lng": 139.7009,
    "price": 720000,
    "price_unit": "per_stay",
    "check_in_time": "15:00",
    "check_out_time": "11:00",
    "note": "신주쿠역 도보 5분",
}


def _slug(index: int) -> str:
    """계약의 place id 패턴 `^[A-Za-z0-9][A-Za-z0-9_-]*$`를 지킨다."""

    return f"tokyo-place-{index:02d}"


def make_place(
    index: int,
    *,
    closed_days: list[str] | None = None,
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """더미 장소 하나. `index`는 `TOKYO_PLACES`의 위치."""

    name, lat, lng, category, opening, duration, price, intensity = TOKYO_PLACES[
        index % len(TOKYO_PLACES)
    ]
    place = {
        "id": _slug(index),
        "name": name,
        "category": category,
        "lat": lat,
        "lng": lng,
        "price": price,
        "price_unit": "per_person",
        "opening_hours": opening,
        "closed_days": closed_days or [],
        "expected_duration_min": duration,
        "physical_intensity": intensity,
        "note": "",
    }
    if override:
        place.update(override)
    return place


def make_search_output(
    *,
    start_date: str = "2026-06-15",
    end_date: str = "2026-06-18",
    place_count: int = 8,
    num_travelers: int = 2,
    budget_total: float = 3_000_000,
    budget_currency: str = "KRW",
    budget_includes: list[str] | None = None,
    transport_mode: str = "대중교통",
    day_start_time: str = "09:00",
    day_end_time: str = "22:00",
    pace: str = "보통",
    max_walking_level: str = "중간",
    must_visit: list[str] | None = None,
    avoid: list[str] | None = None,
    description: str = "역사 명소와 맛집을 좋아하는 2인 여행",
    with_stay: bool = True,
    with_flight: bool = False,
    closed_days_map: dict[int, list[str]] | None = None,
    places: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """`SearchToPlanInput` 형태의 더미 결과물을 만든다.

    기본값은 "정상 동작을 확인하기 좋은" 조합이다. 어려운 경우를 보려면
    `place_count`를 줄이거나 `closed_days_map`으로 휴무일을 넣는다.
    """

    closed_map = closed_days_map or {}
    selected_places = places or [
        make_place(index, closed_days=closed_map.get(index))
        for index in range(place_count)
    ]

    output: dict[str, Any] = {
        "schema_version": "1.0",
        "trip_info": {
            "destination": "도쿄",
            "start_date": start_date,
            "end_date": end_date,
            "num_travelers": num_travelers,
            "budget_total": budget_total,
            "budget_currency": budget_currency,
            "budget_includes": budget_includes
            if budget_includes is not None
            else ["숙소", "식사", "관광지", "쇼핑"],
            "transport_mode": transport_mode,
            "day_start_time": day_start_time,
            "day_end_time": day_end_time,
            "persona": {
                "description": description,
                "must_visit": must_visit if must_visit is not None else ["센소지"],
                "avoid": avoid if avoid is not None else ["장시간 도보"],
                "pace": pace,
                "max_walking_level": max_walking_level,
            },
        },
        "selected": {
            "flight": None,
            "stay": dict(DEFAULT_STAY) if with_stay else None,
            "places": selected_places,
        },
    }

    if with_flight:
        output["selected"]["flight"] = {
            "id": "flight-ke001",
            "outbound": {
                "depart_at": f"{start_date}T09:00",
                "arrive_at": f"{start_date}T11:30",
                "duration_min": 150,
            },
            "inbound": {
                "depart_at": f"{end_date}T18:00",
                "arrive_at": f"{end_date}T20:40",
                "duration_min": 160,
            },
            "total_price": {"amount": 900000, "currency": budget_currency},
        }

    return output


# ── 표준 더미 입력 하나 ──────────────────────────────────────
#
# ## 왜 하나인가
#
# 처음에는 `여유/보통/빡빡`처럼 페이스별로 시나리오를 여러 개 두었다. 그건
# 잘못이었다.
#
# `pace` · `max_walking_level` · `must_visit` · `avoid` 는 모두 **프론트엔드
# 웹사이트가 사용자에게서 받아 `trip_info.persona`에 담아 보내는 값**이다.
# Plan Agent는 그걸 받아 반영할 뿐이고, 여러 안을 만들어 고르게 하지 않는다.
# **입력 하나 = 결과 하나**다.
#
# 그래서 더미도 하나만 둔다. 페이스를 바꿔 보고 싶으면 `make_search_output(pace=...)`
# 인자를 바꾸면 되고, 그건 시나리오가 아니라 그냥 다른 입력이다.
#
# ## 이 입력이 담고 있는 것
#
# 실제 사용에 가깝게 한 번에 다 넣었다. 조건이 하나씩 있을 때 통과하는 것과
# 전부 겹쳤을 때 통과하는 것은 다른 문제다.
#
# - 장소 15곳(관광지·식사·카페·쇼핑·휴식 혼합)을 5일에 배치
# - 필수 방문지 3곳
# - 휴무일 2건 (월요일 휴관, 화요일 휴관)
# - 예산 제약
# - 항공·숙소 선택 포함

STANDARD_INPUT: dict[str, Any] = {
    "start_date": "2026-06-15",
    "end_date": "2026-06-19",  # 5일 4박
    "place_count": len(TOKYO_PLACES),  # 15곳 전부
    "num_travelers": 2,
    "budget_total": 1_800_000,
    "pace": "보통",
    "max_walking_level": "중간",
    "must_visit": ["센소지", "도쿄 타워", "츠키지 장외시장"],
    "avoid": ["장시간 도보", "복잡한 환승"],
    "description": "역사 명소와 맛집을 좋아하고 카페에서 쉬는 시간을 챙기는 2인 여행",
    "with_flight": True,
    "with_stay": True,
    # 도쿄 국립박물관(index 1)은 월요일 휴관, 하마리큐 정원(index 6)은 화요일 휴관.
    # 2026-06-15가 월요일, 06-16이 화요일이다.
    "closed_days_map": {1: ["월요일"], 6: ["화요일"]},
    "transport_mode": "대중교통",
}


def make_standard_input(**overrides: Any) -> dict[str, Any]:
    """표준 더미 입력. 필요하면 일부만 덮어쓴다."""

    return make_search_output(**{**STANDARD_INPUT, **overrides})


__all__ = [
    "DEFAULT_STAY",
    "STANDARD_INPUT",
    "TOKYO_PLACES",
    "make_place",
    "make_search_output",
    "make_standard_input",
]
