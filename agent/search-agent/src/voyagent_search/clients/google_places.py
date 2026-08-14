"""Google Places Text Search (New) 기반 숙소·관광지 공급자 어댑터."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from ..contracts import SearchRequest
from ..env import load_project_environment

_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.primaryType",
        "places.types",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.regularOpeningHours",
        "places.googleMapsUri",
        "places.websiteUri",
    )
)


class GooglePlacesClient:
    """Places가 실제 제공하는 필드만 반환하고 가격·일정 값을 임의 생성하지 않는다.

    canonical handoff에 필요한 숙소 가격·체크인 시각, 장소 가격·체류시간·활동강도는
    별도의 신뢰 가능한 공급자가 원문에 보강해야 normalizer 검증을 통과한다.
    """

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Google Places API key가 필요합니다")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._transport = transport
        self._endpoint = "https://places.googleapis.com/v1/places:searchText"

    @classmethod
    def from_env(cls) -> "GooglePlacesClient":
        """.env 또는 시스템의 GOOGLE_PLACES_API_KEY에서 client를 만든다."""

        load_project_environment()
        return cls(os.environ.get("GOOGLE_PLACES_API_KEY", ""))

    async def _search(self, query: str, request: SearchRequest) -> list[dict[str, Any]]:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }
        body = {
            "textQuery": query,
            "pageSize": request.max_results,
            "languageCode": "ko",
        }
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(self._endpoint, headers=headers, json=body)
            response.raise_for_status()
            rows = response.json().get("places", [])

        retrieved_at = datetime.now(timezone.utc).isoformat()
        for row in rows:
            record_id = str(row.get("id", "unknown"))
            row["_source"] = {
                "provider": "google-places",
                "record_id": record_id,
                "title": "Google Places Text Search record",
                "url": row.get("googleMapsUri", self._endpoint),
                "retrieved_at": retrieved_at,
            }
        return rows[: request.max_results]

    async def search_stays(self, request: SearchRequest) -> list[dict[str, Any]]:
        """숙소 Places 원문만 반환하며 객실가와 체크인 시각을 만들지 않는다."""

        return await self._search(f"{request.trip_info.destination} 호텔 숙소", request)

    async def search_places(self, request: SearchRequest) -> list[dict[str, Any]]:
        """장소 Places 원문만 반환하며 입장료·체류시간·활동강도를 만들지 않는다."""

        query = request.place_query or f"{request.trip_info.destination} 관광 명소 맛집"
        return await self._search(query, request)
