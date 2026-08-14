"""4개 검색 subagent를 병렬 실행하고 결과를 취합하는 LangGraph Search Agent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from .aggregate import build_search_to_plan
from .clients.base import CityInfoProvider, FlightProvider, ProviderBundle, StayPlaceProvider
from .clients.demo_enrichment import DemoEnrichedGooglePlacesProvider
from .clients.mock import MockTravelProvider
from .clients.serpapi import SerpApiGoogleFlightsClient
from .clients.web_city import web_city_provider_from_env
from .contracts import SearchRequest, SearchRunResult, SearchSelection, SearchToPlanInput
from .state import SearchState
from .subagents.city import build_city_subgraph
from .subagents.flight import build_flight_subgraph
from .subagents.place import build_place_subgraph
from .subagents.stay import build_stay_subgraph


def mock_provider_bundle() -> ProviderBundle:
    """테스트·데모에서 명시적으로만 사용하는 결정론적 mock bundle을 만든다."""

    provider = MockTravelProvider()
    return ProviderBundle(flights=provider, stays=provider, places=provider, city=provider)


def hybrid_demo_provider_bundle(
    flights: FlightProvider | None = None,
    enriched_places: StayPlaceProvider | None = None,
    city: CityInfoProvider | None = None,
) -> ProviderBundle:
    """실제 항공·Google Places·웹 도시조사와 명시적 DEMO 보강을 결합한다.

    credential 또는 설정 오류를 mock으로 숨기지 않는다. 숙소·장소의 이름, 좌표,
    주소, 평점과 Google 제공 영업시간은 실제 Places 결과를 유지하고 canonical 필수
    누락값만 별도 provider가 ``[DEMO DATA]``로 보강한다. cityInfo는 Gemini agent가
    Google Search grounding으로 인터넷을 조사하고 citation을 포함해 구성한다.
    """

    live_flights = flights if flights is not None else SerpApiGoogleFlightsClient.from_env()
    google_demo = (
        enriched_places
        if enriched_places is not None
        else DemoEnrichedGooglePlacesProvider.from_env()
    )
    web_city = city if city is not None else web_city_provider_from_env()
    return ProviderBundle(
        flights=live_flights,
        stays=google_demo,
        places=google_demo,
        city=web_city,
    )


def build_search_graph(providers: ProviderBundle | None = None):
    """START에서 4개 subgraph를 fan-out하고 aggregate에서 fan-in한다.

    공급자를 생략하면 합성 결과가 실데이터처럼 전달될 수 있으므로 fail-closed한다.
    테스트·데모는 mock_provider_bundle()을 호출자가 명시적으로 주입해야 한다.
    """

    if providers is None:
        raise ValueError("ProviderBundle이 필요합니다. 테스트에서는 mock_provider_bundle()을 명시적으로 전달하세요")
    flight_graph = build_flight_subgraph(providers.flights)
    stay_graph = build_stay_subgraph(providers.stays)
    place_graph = build_place_subgraph(providers.places)
    city_graph = build_city_subgraph(providers.city)

    async def run_flight(state: SearchState) -> dict[str, Any]:
        output = await flight_graph.ainvoke({"request": state["request"]})
        return {"flight_result": output["result"]}

    async def run_stay(state: SearchState) -> dict[str, Any]:
        output = await stay_graph.ainvoke({"request": state["request"]})
        return {"stay_result": output["result"]}

    async def run_place(state: SearchState) -> dict[str, Any]:
        output = await place_graph.ainvoke({"request": state["request"]})
        return {"place_result": output["result"]}

    async def run_city(state: SearchState) -> dict[str, Any]:
        output = await city_graph.ainvoke({"request": state["request"]})
        return {"city_result": output["result"]}

    def aggregate(state: SearchState) -> dict[str, SearchRunResult]:
        return {
            "result": SearchRunResult(
                request=state["request"],
                flights=state["flight_result"],
                stays=state["stay_result"],
                places=state["place_result"],
                city=state["city_result"],
            )
        }

    builder = StateGraph(SearchState)
    builder.add_node("flight_subagent", run_flight)
    builder.add_node("stay_subagent", run_stay)
    builder.add_node("place_subagent", run_place)
    builder.add_node("city_subagent", run_city)
    builder.add_node("aggregate", aggregate)
    for node in ("flight_subagent", "stay_subagent", "place_subagent", "city_subagent"):
        builder.add_edge(START, node)
    builder.add_edge(
        ["flight_subagent", "stay_subagent", "place_subagent", "city_subagent"],
        "aggregate",
    )
    builder.add_edge("aggregate", END)
    return builder.compile()


async def run_search(request: SearchRequest, providers: ProviderBundle | None = None) -> SearchRunResult:
    """주입된 공급자로 병렬 검색해 검증 후보와 내부 cityInfo를 반환한다."""

    state = await build_search_graph(providers).ainvoke({"request": request})
    return state["result"]


async def run_search_to_plan(
    request: SearchRequest,
    selection: SearchSelection,
    providers: ProviderBundle | None = None,
) -> SearchToPlanInput:
    """검색 후 사용자 선택을 canonical Search→Plan handoff로 변환한다."""

    result = await run_search(request, providers)
    return build_search_to_plan(result, selection)
