"""통합 Search Agent와 도메인 subgraph의 LangGraph state 정의."""

from __future__ import annotations

from typing import Any, TypedDict

from .contracts import (
    CityInfoResult,
    FlightSearchResult,
    PlaceSearchResult,
    SearchRequest,
    SearchRunResult,
    StaySearchResult,
)


class DomainState(TypedDict, total=False):
    request: SearchRequest
    raw_items: list[dict[str, Any]]
    normalized_items: list[Any]
    issues: list[str]
    error: str | None
    result: Any


class SearchState(TypedDict, total=False):
    request: SearchRequest
    flight_result: FlightSearchResult
    stay_result: StaySearchResult
    place_result: PlaceSearchResult
    city_result: CityInfoResult
    result: SearchRunResult
