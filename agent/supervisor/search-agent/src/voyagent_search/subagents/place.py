"""관광지·식사·카페 후보를 찾고 검증하는 LangGraph subagent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from ..clients.base import PlaceProvider
from ..contracts import PlaceCandidate, PlaceSearchResult
from ..state import DomainState
from ..tools.place_discovery import normalize_places


def build_place_subgraph(provider: PlaceProvider):
    """fetch → normalize → rank → fact_verify → schema_validate 단계를 구성한다."""

    async def fetch_raw(state: DomainState) -> dict[str, Any]:
        try:
            return {"raw_items": await provider.search_places(state["request"]), "error": None}
        except Exception as error:
            return {"raw_items": [], "error": str(error)}

    def normalize(state: DomainState) -> dict[str, Any]:
        if state.get("error"):
            return {"normalized_items": [], "issues": []}
        items, issues = normalize_places(state.get("raw_items", []), state["request"])
        return {"normalized_items": items, "issues": issues}

    def deterministic_rank(state: DomainState) -> dict[str, Any]:
        items: list[PlaceCandidate] = list(state.get("normalized_items", []))
        items.sort(key=lambda item: (-(item.rating or 0), item.place.price, item.place.name))
        return {"normalized_items": items[: state["request"].max_results]}

    def fact_verify(state: DomainState) -> dict[str, Any]:
        return {"normalized_items": [item for item in state.get("normalized_items", []) if item.verification.accepted]}

    def schema_validate(state: DomainState) -> dict[str, Any]:
        issues = state.get("issues", [])
        if state.get("error"):
            result = PlaceSearchResult(status="error", issues=issues, error=str(state["error"]))
        elif not state.get("normalized_items"):
            result = PlaceSearchResult(status="error", issues=issues, error="검증을 통과한 장소가 없습니다")
        else:
            result = PlaceSearchResult(status="success", candidates=state["normalized_items"], issues=issues)
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
