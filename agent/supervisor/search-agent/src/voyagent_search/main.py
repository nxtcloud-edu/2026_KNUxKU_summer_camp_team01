"""Search Agent FastAPI SSE server.

    POST /agent/search   SearchRequest -> SearchToPlanInput

API endpoint의 기본 `hybrid` 모드는 실제 항공·Google Places 결과를 쓰고,
canonical 일정에 필요한 누락 필드는 명시적 [DEMO DATA]로 보강한다.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from math import asin, cos, radians, sin, sqrt
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from .aggregate import build_search_to_plan
from .contracts import SearchRequest, SearchRunResult, SearchSelection
from .env import load_project_environment
from .graph import (
    hybrid_demo_provider_bundle,
    live_provider_bundle,
    mock_provider_bundle,
    run_search,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
load_project_environment()

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

app = FastAPI(title="Voyagent Search Agent", version="0.1.0")


def _strict_facts_enabled() -> bool:
    return os.getenv("STRICT_FACTS", "true").strip().casefold() not in {
        "0",
        "false",
        "off",
        "no",
    }


def _remove_unsupported_live_features(request: SearchRequest) -> SearchRequest:
    """현재 연결된 API로 사실 확인할 수 없는 기능을 요청에서 제외한다.

    숙소 실가격·체크인/체크아웃, 관광지 입장료, 사실 기반 체류시간·활동강도는
    지금 provider만으로 확인할 수 없다. strict 모드에서는 그 값을 만들지 않고
    기능 자체를 끈다.
    """

    if not _strict_facts_enabled():
        return request
    trip = request.trip_info.model_copy(
        update={
            "budget_includes": [
                item for item in request.trip_info.budget_includes if item != "숙소"
            ]
        }
    )
    return request.model_copy(update={"include_stays": False, "trip_info": trip})


class SseEmitter:
    def __init__(self) -> None:
        self.seq = 0
        self.started = time.monotonic()
        self.terminated = False

    def event(self, event_type: str, **fields: Any) -> str:
        payload = {
            "seq": self.seq,
            "at": int((time.monotonic() - self.started) * 1000),
            "type": event_type,
            **fields,
        }
        self.seq += 1
        if event_type in {"done", "error"}:
            self.terminated = True
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _stream(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        status_code=200,
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


_INTENSITY_RANK = {"낮음": 0, "중": 1, "중간": 1, "높음": 2}
_EARTH_RADIUS_KM = 6371.0088


def _distance_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    phi_a, phi_b = radians(a_lat), radians(b_lat)
    d_phi = radians(b_lat - a_lat)
    d_lambda = radians(b_lng - a_lng)
    inner = sin(d_phi / 2) ** 2 + cos(phi_a) * cos(phi_b) * sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(inner))


def _trip_day_count(result: SearchRunResult) -> int:
    start = date.fromisoformat(result.request.trip_info.start_date)
    end = date.fromisoformat(result.request.trip_info.end_date)
    return (end - start).days + 1


def _text_tokens(value: str) -> set[str]:
    return {token for token in value.casefold().replace(",", " ").split() if token}


def _place_score(result: SearchRunResult, candidate: Any, index: int) -> tuple[int, int]:
    """프론트엔드 persona를 Search Agent의 후보 선택 기준으로 바꾼다."""

    place = candidate.place
    persona = result.request.trip_info.persona
    name = place.name.strip().casefold()
    category = place.category.strip().casefold()
    note = place.note.strip().casefold()
    haystack = f"{name} {category} {note}"

    score = 0
    must_visit = {value.strip().casefold() for value in persona.must_visit}
    avoid = {value.strip().casefold() for value in persona.avoid}

    if name in must_visit:
        score += 10_000
    if any(value and value in haystack for value in must_visit):
        score += 3_000
    if any(value and value in haystack for value in avoid):
        score -= 5_000

    if category in {"관광지", "휴식", "쇼핑"} and any(
        keyword in persona.description for keyword in ("역사", "명소", "관광", "놀", "체험")
    ):
        score += 3_000
    if category in {"식사", "카페"} and any(
        keyword in persona.description for keyword in ("맛집", "식사", "현지", "카페")
    ):
        score += 500

    max_rank = _INTENSITY_RANK.get(persona.max_walking_level, 1)
    place_rank = _INTENSITY_RANK.get(place.physical_intensity, 1)
    if place_rank > max_rank:
        score -= 20_000 + (place_rank - max_rank) * 1_000

    description_tokens = _text_tokens(persona.description)
    score += 100 * len(description_tokens & _text_tokens(f"{place.name} {place.category}"))

    if persona.pace == "여유" and place.expected_duration_min <= 90:
        score += 150
    elif persona.pace == "빡빡" and place.expected_duration_min >= 60:
        score += 150

    return score, -index


def _auto_selection(result: SearchRunResult, place_count: int) -> SearchSelection:
    if result.flights.status != "success" or not result.flights.candidates:
        detail = result.flights.error or "; ".join(result.flights.issues) or "후보 없음"
        raise RuntimeError(f"항공 검색에 실패했습니다: {detail}")

    if result.places.status != "success" or not result.places.candidates:
        detail = result.places.error or "; ".join(result.places.issues) or "후보 없음"
        raise RuntimeError(f"장소 검색에 실패했습니다: {detail}")

    ranked_places = sorted(
        enumerate(result.places.candidates),
        key=lambda item: _place_score(result, item[1], item[0]),
        reverse=True,
    )
    selected_candidates: list[Any] = []
    selected_ids: set[str] = set()

    def add_candidate(candidate: Any) -> None:
        if len(selected_candidates) >= place_count:
            return
        if candidate.place.id in selected_ids:
            return
        selected_candidates.append(candidate)
        selected_ids.add(candidate.place.id)

    persona = result.request.trip_info.persona

    def is_must_visit(candidate: Any) -> bool:
        place_name = candidate.place.name.strip().casefold()
        return any(
            required.strip().casefold()
            and (
                required.strip().casefold() in place_name
                or place_name in required.strip().casefold()
            )
            for required in persona.must_visit
        )

    max_rank = _INTENSITY_RANK.get(persona.max_walking_level, 1)

    def is_within_walking_level(candidate: Any) -> bool:
        return _INTENSITY_RANK.get(candidate.place.physical_intensity, 1) <= max_rank

    ranked_comfortable = [
        item for item in ranked_places if is_must_visit(item[1]) or is_within_walking_level(item[1])
    ]

    for _, candidate in ranked_places:
        if is_must_visit(candidate):
            add_candidate(candidate)

    activity_categories = {"관광지", "휴식", "쇼핑"}
    food_categories = {"식사", "카페"}
    activity_target = min(3, max(1, place_count // 2))
    food_target = min(2, max(1, place_count - activity_target))

    for target_categories, target_count in (
        (activity_categories, activity_target),
        (food_categories, food_target),
    ):
        for _, candidate in ranked_comfortable:
            current = sum(
                1 for item in selected_candidates if item.place.category in target_categories
            )
            if current >= target_count:
                break
            if candidate.place.category in target_categories:
                add_candidate(candidate)

    for _, candidate in ranked_comfortable:
        add_candidate(candidate)

    selected_places = [candidate.place for candidate in selected_candidates]
    place_ids = [place.id for place in selected_places]

    stay_id: str | None = None
    if result.request.include_stays:
        if result.stays.status != "success" or not result.stays.candidates:
            detail = result.stays.error or "; ".join(result.stays.issues) or "후보 없음"
            raise RuntimeError(f"숙소 검색에 실패했습니다: {detail}")

        def stay_score(item: Any) -> tuple[float, float, str]:
            stay = item.stay
            if selected_places:
                nearest = min(
                    _distance_km(stay.lat, stay.lng, place.lat, place.lng)
                    for place in selected_places
                )
            else:
                nearest = 999.0
            return nearest, stay.price, stay.name

        stay_id = min(result.stays.candidates, key=stay_score).stay.id

    return SearchSelection(
        flight_id=result.flights.candidates[0].offer.id,
        stay_id=stay_id,
        place_ids=place_ids,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "provider": "hybrid-demo",
        "strict_facts": str(_strict_facts_enabled()).lower(),
    }


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request: Request, _error: RequestValidationError
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        emitter = SseEmitter()
        yield emitter.event(
            "error",
            code="invalid_input",
            message="입력 형식이 올바르지 않아요.",
            retryable=False,
        )

    return _stream(events())


@app.post("/agent/search")
async def search(request: Request) -> StreamingResponse:
    try:
        body = await request.json()
    except Exception:
        async def bad_json() -> AsyncIterator[str]:
            emitter = SseEmitter()
            yield emitter.event(
                "error",
                code="invalid_input",
                message="요청 본문이 JSON이 아니에요.",
                retryable=False,
            )

        return _stream(bad_json())

    async def events() -> AsyncIterator[str]:
        emitter = SseEmitter()
        try:
            yield emitter.event("status", text="검색 조건을 확인하고 있어요")

            place_count = int(body.pop("place_count", 20) or 20)
            provider_mode = str(body.pop("provider_mode", "hybrid") or "hybrid").strip()
            if provider_mode not in {"mock", "hybrid", "hybrid_demo", "live"}:
                yield emitter.event(
                    "error",
                    code="invalid_input",
                    message="provider_mode은 mock, hybrid, hybrid_demo, live 중 하나여야 해요.",
                    retryable=False,
                )
                return
            request_model = SearchRequest.model_validate(body)
            if provider_mode == "hybrid":
                providers = hybrid_demo_provider_bundle()
            elif provider_mode == "live":
                request_model = _remove_unsupported_live_features(request_model)
                providers = live_provider_bundle()
            elif provider_mode == "hybrid_demo":
                providers = hybrid_demo_provider_bundle()
            else:
                providers = mock_provider_bundle()

            yield emitter.event("status", text="항공·숙소·장소 후보를 검색하고 있어요")
            result = await run_search(request_model, providers)

            yield emitter.event("status", text="검색 결과를 Plan Agent 입력으로 정리하고 있어요")
            # 저녁 식사 이후 활동까지 만들려면 1일 2곳 수준으로는 부족하다.
            # 프론트가 낮게 보내더라도 일정 품질 최소치를 위해 하루 3곳까지 자동 확장한다.
            day_count = (date.fromisoformat(request_model.trip_info.end_date) - date.fromisoformat(request_model.trip_info.start_date)).days + 1
            place_count = max(place_count, day_count * 3)
            selection = _auto_selection(
                result, max(1, min(place_count, len(result.places.candidates)))
            )
            handoff = build_search_to_plan(result, selection)

            yield emitter.event(
                "done",
                payload=handoff.model_dump(mode="json"),
                summary="검색 결과를 일정 생성 입력으로 정리했어요.",
            )
        except ValidationError as error:
            logger.warning("search input validation failed: %s", error)
            if not emitter.terminated:
                yield emitter.event(
                    "error",
                    code="invalid_input",
                    message="입력 형식이 SearchRequest 계약과 맞지 않아요.",
                    retryable=False,
                )
        except Exception as error:
            logger.exception("search agent failed")
            if not emitter.terminated:
                yield emitter.event(
                    "error",
                    code="agent_failed",
                    message=str(error)[:200] or "검색을 완료하지 못했어요.",
                    retryable=True,
                )

    return _stream(events())


__all__ = ["app"]
