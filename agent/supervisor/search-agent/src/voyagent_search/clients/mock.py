"""API 키 없이 전체 그래프를 실행하는 명시적 DEMO DATA 공급자."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..contracts import SearchRequest

_DEMO = "[DEMO DATA]"
_TOKYO_DESTINATIONS = {"도쿄", "tokyo"}


def _require_tokyo_fixture(request: SearchRequest) -> None:
    """도쿄 fixture가 다른 목적지의 데이터처럼 반환되는 것을 막는다."""

    destination = request.trip_info.destination.strip()
    if destination.casefold() not in _TOKYO_DESTINATIONS:
        raise ValueError("DEMO 숙소·장소 fixture는 도쿄 전용입니다")


def _source(provider: str, record_id: str, title: str, url: str) -> dict[str, Any]:
    """내부 verification에서도 합성 데이터임을 식별할 provenance를 만든다."""

    return {
        "provider": provider,
        "record_id": record_id,
        "title": f"{_DEMO} {title}",
        "url": url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


class MockTravelProvider:
    """도쿄 시연용 합성 후보를 반환하며 네 도메인 Protocol을 모두 구현한다."""

    async def search_flights(self, request: SearchRequest) -> list[dict[str, Any]]:
        """실제 항공 provider가 없는 all-mock mode에만 합성 항공편을 반환한다."""

        start, end = request.trip_info.start_date, request.trip_info.end_date
        currency = request.trip_info.budget_currency
        rows: list[dict[str, Any]] = []
        for index, (carrier, amount, minutes) in enumerate(
            (("KE", 520000, 140), ("OZ", 548000, 145), ("JL", 579000, 135)),
            1,
        ):
            record_id = f"mock-flight-{index}"
            itineraries = [{
                "duration": f"PT{minutes // 60}H{minutes % 60}M",
                "segments": [{
                    "departure": {"iataCode": request.origin_iata, "at": f"{start}T09:00:00+09:00"},
                    "arrival": {
                        "iataCode": request.destination_iata,
                        "at": f"{start}T{11 + (minutes - 120) // 60:02d}:{minutes % 60:02d}:00+09:00",
                    },
                    "carrierCode": carrier,
                }],
            }]
            if request.flight_trip_type == "round_trip":
                itineraries.append({
                    "duration": "PT2H30M",
                    "segments": [{
                        "departure": {
                            "iataCode": request.destination_iata,
                            "at": f"{end}T18:00:00+09:00",
                        },
                        "arrival": {"iataCode": request.origin_iata, "at": f"{end}T20:30:00+09:00"},
                        "carrierCode": carrier,
                    }],
                })
            rows.append({
                "id": record_id,
                "itineraries": itineraries,
                "price": {"grandTotal": str(amount), "currency": currency},
                "_source": _source(
                    "demo-mock-flight",
                    record_id,
                    "Synthetic Flight Search record",
                    "https://example.invalid/demo-flights",
                ),
            })
        return rows[: request.max_results]

    async def search_stays(self, request: SearchRequest) -> list[dict[str, Any]]:
        """가격과 체크인 시각을 포함한 명시적 합성 숙소를 반환한다."""

        _require_tokyo_fixture(request)
        city = request.trip_info.destination
        values = (
            ("stay-gracery-shinjuku", "호텔 그레이스리 신주쿠", 35.6955, 139.7009, 180000, 4.3),
            ("stay-asakusa-view", "아사쿠사 뷰 호텔", 35.7154, 139.7934, 165000, 4.2),
            ("stay-tokyo-station", "도쿄 스테이션 호텔", 35.6813, 139.7658, 320000, 4.7),
        )
        return [
            {
                "id": item_id,
                "displayName": {"text": name},
                "location": {"latitude": lat, "longitude": lng},
                "estimatedPrice": price,
                "currency": request.trip_info.budget_currency,
                "checkInTime": "15:00",
                "checkOutTime": "11:00",
                "rating": rating,
                "formattedAddress": f"{_DEMO} 합성 숙소 정보 · {city} 중심부",
                "googleMapsUri": f"https://maps.google.com/?q={item_id}",
                "_source": _source(
                    "demo-mock-stay",
                    item_id,
                    f"Synthetic stay: {name}",
                    f"https://maps.google.com/?q={item_id}",
                ),
            }
            for item_id, name, lat, lng, price, rating in values[: request.max_results]
        ]

    async def search_places(self, request: SearchRequest) -> list[dict[str, Any]]:
        """가격·체류시간·활동강도를 포함한 명시적 합성 장소를 반환한다."""

        _require_tokyo_fixture(request)
        values = (
            ("tokyo-sensoji", "센소지", "관광지", 35.7148, 139.7967, 0, "06:00-17:00", 90, "중간", 4.5),
            ("tokyo-skytree", "도쿄 스카이트리", "관광지", 35.7101, 139.8107, 21000, "10:00-21:00", 120, "중간", 4.4),
            ("tokyo-ueno-park", "우에노 공원", "휴식", 35.7148, 139.7732, 0, "05:00-23:00", 90, "낮음", 4.3),
            ("tokyo-tsukiji", "쓰키지 장외시장", "식사", 35.6655, 139.7707, 30000, "05:00-14:00", 90, "중간", 4.2),
            ("tokyo-meiji", "메이지 신궁", "관광지", 35.6764, 139.6993, 0, "05:00-18:00", 90, "중간", 4.6),
        )
        return [
            {
                "id": item_id,
                "displayName": {"text": name},
                "primaryCategory": category,
                "location": {"latitude": lat, "longitude": lng},
                "estimatedPrice": price,
                "priceUnit": "per_person",
                "openingHoursText": hours,
                "closedDays": [],
                "expectedDurationMin": duration,
                "physicalIntensity": intensity,
                "rating": rating,
                "formattedAddress": f"{_DEMO} 합성 관광지 정보",
                "googleMapsUri": f"https://maps.google.com/?q={item_id}",
                "_source": _source(
                    "demo-mock-place",
                    item_id,
                    f"Synthetic place: {name}",
                    f"https://maps.google.com/?q={item_id}",
                ),
            }
            for item_id, name, category, lat, lng, price, hours, duration, intensity, rating in values[
                : request.max_results
            ]
        ]

    async def search_city_info(self, request: SearchRequest) -> list[dict[str, Any]]:
        """공식 조회 결과가 아닌 명시적 합성 도시정보를 반환한다."""

        city = request.trip_info.destination
        now = datetime.now(timezone.utc).isoformat()
        return [{
            "city_id": city.lower().replace(" ", "-"),
            "city_name": city,
            "country_name": "일본" if city in {"도쿄", "Tokyo"} else "확인 필요",
            "timezone": "Asia/Tokyo" if city in {"도쿄", "Tokyo"} else "UTC",
            "currency": "JPY" if city in {"도쿄", "Tokyo"} else request.trip_info.budget_currency,
            "languages": ["일본어"] if city in {"도쿄", "Tokyo"} else ["현지어"],
            "overview": f"{_DEMO} {city} 시연용 합성 도시정보입니다.",
            "weather": {
                "summary": f"{_DEMO} 여행 직전 실제 공식 예보를 다시 확인하세요.",
                "packing_tips": ["걷기 편한 신발", "휴대용 우산"],
            },
            "transport": {
                "summary": f"{_DEMO} 대중교통 중심 이동이 편리하다는 시연용 설명입니다.",
                "tips": ["교통카드 준비", "막차 시간 확인"],
            },
            "safety": {
                "summary": f"{_DEMO} 일반적인 여행 안전 수칙을 지키세요.",
                "emergency_numbers": ["110", "119"],
                "tips": ["여권 사본 보관"],
            },
            "etiquette_tips": ["대중교통에서는 조용히 통화하기"],
            "practical_tips": ["현금과 카드를 함께 준비하기"],
            "sources": [{
                "title": f"{_DEMO} Reference placeholder",
                "url": "https://example.invalid/demo-city-source",
                "publisher": "DEMO",
                "retrieved_at": now,
            }],
            "fetched_at": now,
            "_source": _source(
                "demo-mock-city",
                "city-info-1",
                "Synthetic city information",
                "https://example.invalid/demo-city-source",
            ),
        }]
