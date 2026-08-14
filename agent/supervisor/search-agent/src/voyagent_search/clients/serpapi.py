"""SerpApi Google Flights Results API 비동기 항공 검색 어댑터."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from ..contracts import SearchRequest
from ..env import load_project_environment

_ALLOWED_BASE_URLS = {"https://serpapi.com"}
_MAX_ROUND_TRIP_LOOKUPS = 3
_CARRIER_CODE = re.compile(r"^([A-Z0-9]{2,3})\s*\d")


def _options(body: dict[str, Any]) -> list[dict[str, Any]]:
    """best/other 배열을 순서대로 병합하고 같은 항공편을 중복 제거한다."""

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in ("best_flights", "other_flights"):
        values = body.get(key, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            fingerprint = str(value.get("departure_token") or _fingerprint(value))
            if fingerprint not in seen:
                seen.add(fingerprint)
                merged.append(value)
    return merged


def _fingerprint(value: Any) -> str:
    """provider token이 없을 때도 결과 내용으로 안정적인 식별 해시를 만든다."""

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _local_iso(value: Any) -> str:
    """SerpApi 현지시각을 timezone을 꾸며내지 않고 ISO 형태로 정규화한다."""

    text = str(value or "").strip().replace(" ", "T", 1)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed.isoformat(timespec="seconds")


def _duration(minutes: Any) -> str:
    """SerpApi의 분 단위 총 소요시간을 내부 ISO-8601 duration으로 바꾼다."""

    value = int(minutes)
    if value < 0:
        raise ValueError("항공편 소요시간은 음수일 수 없습니다")
    hours, remaining = divmod(value, 60)
    return f"PT{hours}H{remaining}M"


def _carrier_code(flight_number: Any) -> str | None:
    """편명의 선두 IATA carrier code만 보수적으로 추출한다."""

    match = _CARRIER_CODE.match(str(flight_number or "").strip().upper())
    return match.group(1) if match else None


def _itinerary(option: dict[str, Any]) -> dict[str, Any]:
    """Google Flights option을 provider-neutral 내부 itinerary로 투영한다."""

    flights = option.get("flights")
    if not isinstance(flights, list) or not flights:
        raise ValueError("SerpApi 항공편에 flights가 없습니다")

    segments: list[dict[str, Any]] = []
    for flight in flights:
        if not isinstance(flight, dict):
            raise ValueError("SerpApi flight segment 형식이 올바르지 않습니다")
        departure = flight.get("departure_airport")
        arrival = flight.get("arrival_airport")
        if not isinstance(departure, dict) or not isinstance(arrival, dict):
            raise ValueError("SerpApi flight segment의 공항 정보가 없습니다")

        segment: dict[str, Any] = {
            "departure": {
                "iataCode": str(departure.get("id", "")),
                "at": _local_iso(departure.get("time")),
            },
            "arrival": {
                "iataCode": str(arrival.get("id", "")),
                "at": _local_iso(arrival.get("time")),
            },
        }
        carrier_code = _carrier_code(flight.get("flight_number"))
        if carrier_code:
            segment["carrierCode"] = carrier_code
        segments.append(segment)

    return {
        "duration": _duration(option.get("total_duration")),
        "segments": segments,
    }


def _price(option: dict[str, Any]) -> float:
    """선택된 option에 명시된 유한한 양수 가격만 허용한다."""

    if "price" not in option:
        raise ValueError("SerpApi 항공편에 명시적 가격이 필요합니다")
    amount = float(option["price"])
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("SerpApi 항공권 가격은 유한한 양수여야 합니다")
    return amount


class SerpApiGoogleFlightsClient:
    """Google Flights의 최신 검색가격을 canonical 후보용 내부 원문으로 변환한다."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://serpapi.com",
        timeout_seconds: float = 30.0,
        max_round_trip_lookups: int = _MAX_ROUND_TRIP_LOOKUPS,
        force_fresh: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("SerpApi API key가 필요합니다")
        normalized_base_url = base_url.rstrip("/")
        if normalized_base_url not in _ALLOWED_BASE_URLS:
            raise ValueError("SerpApi base_url은 공식 HTTPS endpoint여야 합니다")
        if not 1 <= max_round_trip_lookups <= 20:
            raise ValueError("SerpApi 왕복 후속 조회 상한은 1~20이어야 합니다")
        self._api_key = api_key
        self._base_url = normalized_base_url
        self._timeout = timeout_seconds
        self._max_round_trip_lookups = max_round_trip_lookups
        self._force_fresh = force_fresh
        self._transport = transport
        self._endpoint = f"{normalized_base_url}/search.json"

    @classmethod
    def from_env(cls) -> "SerpApiGoogleFlightsClient":
        """.env에서 API key와 명시적인 과금·신선도 정책을 읽어 client를 만든다."""

        load_project_environment()
        try:
            max_lookups = int(os.environ.get("SERPAPI_MAX_ROUND_TRIP_LOOKUPS", str(_MAX_ROUND_TRIP_LOOKUPS)))
        except ValueError as error:
            raise ValueError("SERPAPI_MAX_ROUND_TRIP_LOOKUPS는 정수여야 합니다") from error
        fresh_text = os.environ.get("SERPAPI_FORCE_FRESH", "true").strip().lower()
        if fresh_text not in {"true", "false"}:
            raise ValueError("SERPAPI_FORCE_FRESH는 true 또는 false여야 합니다")
        return cls(
            os.environ.get("SERPAPI_API_KEY", ""),
            max_round_trip_lookups=max_lookups,
            force_fresh=fresh_text == "true",
        )

    def _params(self, request: SearchRequest) -> dict[str, Any]:
        """SearchRequest를 Google Flights 검색 파라미터로 변환한다."""

        if not request.origin_iata or not request.destination_iata:
            raise ValueError("항공 검색에는 출발·도착 IATA 코드가 필요합니다")
        is_round_trip = request.flight_trip_type == "round_trip"
        params: dict[str, Any] = {
            "engine": "google_flights",
            "departure_id": request.origin_iata,
            "arrival_id": request.destination_iata,
            "outbound_date": request.trip_info.start_date,
            "currency": request.trip_info.budget_currency,
            "adults": request.trip_info.num_travelers,
            "hl": "ko",
            "gl": "kr",
            "type": 1 if is_round_trip else 2,
        }
        if self._force_fresh:
            params["no_cache"] = "true"
        if is_round_trip:
            params["return_date"] = request.trip_info.end_date
        return params

    async def _fetch(self, client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
        """네트워크·provider 오류에서도 API key가 예외 문자열에 노출되지 않게 한다."""

        response: httpx.Response | None = None
        network_failed = False
        try:
            response = await client.get(self._endpoint, params={**params, "api_key": self._api_key})
        except httpx.RequestError:
            network_failed = True
        if network_failed or response is None:
            raise RuntimeError("SerpApi Google Flights 네트워크 요청에 실패했습니다")
        if response.is_error:
            raise RuntimeError(f"SerpApi Google Flights HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise ValueError("SerpApi Google Flights 응답이 유효한 JSON이 아닙니다") from error
        if not isinstance(body, dict):
            raise ValueError("SerpApi Google Flights 응답이 JSON object가 아닙니다")
        if body.get("error"):
            raise RuntimeError("SerpApi Google Flights 응답에 오류가 포함되었습니다")
        return body

    def _row(
        self,
        outbound: dict[str, Any],
        request: SearchRequest,
        retrieved_at: str,
        inbound: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """출국·선택 귀국편을 기존 내부 flight raw contract로 조립한다."""

        signature = {
            "outbound": outbound.get("departure_token") or outbound.get("flights"),
            "inbound": inbound.get("flights") if inbound else None,
            "price": inbound.get("price") if inbound else outbound.get("price"),
            "currency": request.trip_info.budget_currency,
        }
        record_id = f"serpapi-{_fingerprint(signature)[:20]}"
        itineraries = [_itinerary(outbound)]
        if inbound is not None:
            itineraries.append(_itinerary(inbound))
        amount = _price(inbound) if inbound is not None else _price(outbound)
        return {
            "id": record_id,
            "itineraries": itineraries,
            "price": {
                "grandTotal": str(amount),
                "currency": request.trip_info.budget_currency,
            },
            "_source": {
                "provider": "serpapi-google-flights",
                "record_id": record_id,
                "title": "SerpApi Google Flights Results record",
                "url": self._endpoint,
                "retrieved_at": retrieved_at,
            },
        }

    async def search_flights(self, request: SearchRequest) -> list[dict[str, Any]]:
        """실시간 검색 후 왕복이면 각 출국편의 token으로 최저가 귀국편을 결합한다."""

        params = self._params(request)
        is_round_trip = "return_date" in params
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            initial = await self._fetch(client, params)
            lookup_limit = (
                min(request.max_results, self._max_round_trip_lookups)
                if is_round_trip
                else request.max_results
            )
            outbound_options = _options(initial)[:lookup_limit]
            retrieved_at = datetime.now(timezone.utc).isoformat()

            if not is_round_trip:
                rows: list[dict[str, Any]] = []
                for outbound in outbound_options:
                    try:
                        rows.append(self._row(outbound, request, retrieved_at))
                    except (KeyError, TypeError, ValueError):
                        continue
                return rows

            async def fetch_round_trip(outbound: dict[str, Any]) -> dict[str, Any]:
                token = outbound.get("departure_token")
                if not isinstance(token, str) or not token:
                    raise ValueError("SerpApi 왕복 출국편에 departure_token이 없습니다")
                response = await self._fetch(client, {**params, "departure_token": token})
                inbound_options = _options(response)
                priced: list[tuple[float, dict[str, Any]]] = []
                for inbound in inbound_options:
                    try:
                        priced.append((_price(inbound), inbound))
                    except (TypeError, ValueError):
                        continue
                if not priced:
                    raise ValueError("SerpApi 귀국편에 명시적 가격이 있는 후보가 없습니다")
                _, inbound = min(priced, key=lambda item: item[0])
                return self._row(outbound, request, retrieved_at, inbound)

            rows = await asyncio.gather(*(fetch_round_trip(outbound) for outbound in outbound_options))

        return rows[: request.max_results]
