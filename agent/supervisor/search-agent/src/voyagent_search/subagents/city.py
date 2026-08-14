"""공식 출처 기반 도시 실용정보를 구성·검증하는 LangGraph subagent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from ..clients.base import CityInfoProvider
from ..contracts import CityInfoResult
from ..state import DomainState
from ..tools.city_info import normalize_city_info


def build_city_subgraph(provider: CityInfoProvider):
    """fetch → normalize → rank → fact_verify → schema_validate 단계를 구성한다."""

    async def fetch_raw(state: DomainState) -> dict[str, Any]:
        try:
            return {"raw_items": await provider.search_city_info(state["request"]), "error": None}
        except Exception as error:
            return {"raw_items": [], "error": str(error)}

    def normalize(state: DomainState) -> dict[str, Any]:
        if state.get("error"):
            return {"normalized_items": []}
        return {"normalized_items": [normalize_city_info(state.get("raw_items", []))]}

    def deterministic_rank(state: DomainState) -> dict[str, Any]:
        return {"normalized_items": list(state.get("normalized_items", []))[:1]}

    def fact_verify(state: DomainState) -> dict[str, Any]:
        items: list[CityInfoResult] = list(state.get("normalized_items", []))
        return {"normalized_items": [item for item in items if item.status == "success"]}

    def schema_validate(state: DomainState) -> dict[str, Any]:
        if state.get("error"):
            result = CityInfoResult(status="error", error=str(state["error"]))
        elif state.get("normalized_items"):
            result = state["normalized_items"][0]
        else:
            result = CityInfoResult(status="error", error="검증을 통과한 도시 정보가 없습니다")
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
