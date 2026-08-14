"""항공 원문 수집부터 후보 검증까지 수행하는 LangGraph subagent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from ..clients.base import FlightProvider
from ..contracts import FlightCandidate, FlightSearchResult
from ..state import DomainState
from ..tools.flight_search import normalize_flight_offers


def build_flight_subgraph(provider: FlightProvider):
    """fetch → normalize → rank → fact_verify → schema_validate 단계를 구성한다."""

    async def fetch_raw(state: DomainState) -> dict[str, Any]:
        request = state["request"]
        if not request.include_flights:
            return {"raw_items": [], "error": None}
        try:
            return {"raw_items": await provider.search_flights(request), "error": None}
        except Exception as error:  # 공급자 장애는 다른 병렬 subagent를 중단시키지 않는다.
            return {"raw_items": [], "error": str(error)}

    def normalize(state: DomainState) -> dict[str, Any]:
        if state.get("error"):
            return {"normalized_items": [], "issues": []}
        items, issues = normalize_flight_offers(state.get("raw_items", []), state["request"])
        return {"normalized_items": items, "issues": issues}

    def deterministic_rank(state: DomainState) -> dict[str, Any]:
        items: list[FlightCandidate] = list(state.get("normalized_items", []))
        items.sort(key=lambda item: (item.offer.total_price.amount, item.offer.outbound.duration_min))
        return {"normalized_items": items[: state["request"].max_results]}

    def fact_verify(state: DomainState) -> dict[str, Any]:
        return {"normalized_items": [item for item in state.get("normalized_items", []) if item.verification.accepted]}

    def schema_validate(state: DomainState) -> dict[str, Any]:
        issues = state.get("issues", [])
        if not state["request"].include_flights:
            result = FlightSearchResult(status="skipped")
        elif state.get("error"):
            result = FlightSearchResult(status="error", issues=issues, error=str(state["error"]))
        elif not state.get("normalized_items"):
            result = FlightSearchResult(status="error", issues=issues, error="검증을 통과한 항공편이 없습니다")
        else:
            result = FlightSearchResult(status="success", candidates=state["normalized_items"], issues=issues)
        return {"result": result}

    builder = StateGraph(DomainState)
    for name, node in (
        ("fetch_raw", fetch_raw),
        ("normalize", normalize),
        ("deterministic_rank", deterministic_rank),
        ("fact_verify", fact_verify),
        ("schema_validate", schema_validate),
    ):
        builder.add_node(name, node)
    builder.add_edge(START, "fetch_raw")
    builder.add_edge("fetch_raw", "normalize")
    builder.add_edge("normalize", "deterministic_rank")
    builder.add_edge("deterministic_rank", "fact_verify")
    builder.add_edge("fact_verify", "schema_validate")
    builder.add_edge("schema_validate", END)
    return builder.compile()
