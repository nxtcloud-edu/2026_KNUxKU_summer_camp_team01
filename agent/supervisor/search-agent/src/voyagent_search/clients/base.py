"""검색 공급자를 교체하기 위한 비동기 Protocol과 provider 묶음."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..contracts import SearchRequest


class FlightProvider(Protocol):
    async def search_flights(self, request: SearchRequest) -> list[dict[str, Any]]: ...


class StayProvider(Protocol):
    async def search_stays(self, request: SearchRequest) -> list[dict[str, Any]]: ...


class PlaceProvider(Protocol):
    async def search_places(self, request: SearchRequest) -> list[dict[str, Any]]: ...


class StayPlaceProvider(StayProvider, PlaceProvider, Protocol):
    """숙소와 장소 검색을 모두 제공하는 구조적 provider 계약."""


class CityInfoProvider(Protocol):
    async def search_city_info(self, request: SearchRequest) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class ProviderBundle:
    """도메인별 공급자를 주입해 mock/live를 같은 graph에서 사용한다."""

    flights: FlightProvider
    stays: StayProvider
    places: PlaceProvider
    city: CityInfoProvider
