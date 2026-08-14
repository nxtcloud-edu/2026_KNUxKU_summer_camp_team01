"""관광지·식사·카페 후보를 찾고 검증하는 LangGraph subagent."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any

from langgraph.graph import END, START, StateGraph

from ..clients.base import PlaceProvider
from ..contracts import PlaceCandidate, PlaceSearchResult
from ..state import DomainState
from ..tools.place_discovery import normalize_places

EARTH_RADIUS_KM = 6371.0088


def _distance_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    phi_a, phi_b = radians(a_lat), radians(b_lat)
    d_phi = radians(b_lat - a_lat)
    d_lambda = radians(b_lng - a_lng)
    inner = sin(d_phi / 2) ** 2 + cos(phi_a) * cos(phi_b) * sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(inner))


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
        request = state["request"]
        persona = request.trip_info.persona
        must_visit = [value.strip().casefold() for value in persona.must_visit]
        description = persona.description.casefold()
        anchors = [
            item.place
            for item in items
            if any(
                value
                and (
                    value in item.place.name.strip().casefold()
                    or item.place.name.strip().casefold() in value
                )
                for value in must_visit
            )
        ]

        def score(item: PlaceCandidate) -> tuple[float, float, str]:
            place = item.place
            name = place.name.strip().casefold()
            category = place.category.strip()
            value = 0.0
            if any(token and (token in name or name in token) for token in must_visit):
                value += 10_000
            if category in {"관광지", "휴식", "쇼핑"} and any(
                keyword in description for keyword in ("역사", "명소", "관광", "놀", "체험")
            ):
                value += 3_000
            if category in {"식사", "카페"} and any(
                keyword in description for keyword in ("맛집", "식사", "카페", "현지")
            ):
                value += 500
            if anchors and category in {"식사", "카페", "쇼핑", "휴식"}:
                nearest = min(
                    _distance_km(place.lat, place.lng, anchor.lat, anchor.lng)
                    for anchor in anchors
                )
                if nearest <= 1.5:
                    value += 1_500
                elif nearest <= 3.0:
                    value += 600
                elif nearest >= 8.0:
                    value -= 600
            value += (item.rating or 0) * 100
            return value, -(place.price or 0), place.name

        items.sort(key=score, reverse=True)

        limit = state["request"].max_results
        selected: list[PlaceCandidate] = []
        selected_ids: set[str] = set()

        def add(item: PlaceCandidate) -> None:
            if len(selected) >= limit or item.place.id in selected_ids:
                return
            selected.append(item)
            selected_ids.add(item.place.id)

        quotas = (
            ({"관광지", "휴식", "쇼핑"}, max(3, limit // 2)),
            ({"식사", "카페"}, max(2, limit // 3)),
        )
        for categories, target in quotas:
            for item in items:
                if sum(1 for chosen in selected if chosen.place.category in categories) >= target:
                    break
                if item.place.category in categories:
                    add(item)

        for item in items:
            add(item)

        return {"normalized_items": selected}

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
