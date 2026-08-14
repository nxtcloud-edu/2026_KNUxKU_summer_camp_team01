"""Search Agent FastAPI SSE server.

    POST /agent/search   SearchRequest -> SearchToPlanInput

기본 provider는 mock이다. 로컬 통합 테스트와 더미데이터 검증이 API key 없이
돌아가야 하기 때문이다. live/hybrid 검색은 CLI에서 명시적으로 사용한다.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from .aggregate import build_search_to_plan
from .contracts import SearchRequest, SearchRunResult, SearchSelection
from .graph import hybrid_demo_provider_bundle, mock_provider_bundle, run_search

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

app = FastAPI(title="Voyagent Search Agent", version="0.1.0")


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

    max_rank = _INTENSITY_RANK.get(persona.max_walking_level, 1)
    place_rank = _INTENSITY_RANK.get(place.physical_intensity, 1)
    if place_rank > max_rank:
        score -= 2_000 + (place_rank - max_rank) * 500

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

    stay_id: str | None = None
    if result.request.include_stays:
        if result.stays.status != "success" or not result.stays.candidates:
            detail = result.stays.error or "; ".join(result.stays.issues) or "후보 없음"
            raise RuntimeError(f"숙소 검색에 실패했습니다: {detail}")
        stay_id = result.stays.candidates[0].stay.id

    if result.places.status != "success" or not result.places.candidates:
        detail = result.places.error or "; ".join(result.places.issues) or "후보 없음"
        raise RuntimeError(f"장소 검색에 실패했습니다: {detail}")

    ranked_places = sorted(
        enumerate(result.places.candidates),
        key=lambda item: _place_score(result, item[1], item[0]),
        reverse=True,
    )
    place_ids = [candidate.place.id for _, candidate in ranked_places[:place_count]]
    return SearchSelection(
        flight_id=result.flights.candidates[0].offer.id,
        stay_id=stay_id,
        place_ids=place_ids,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "provider": "mock"}


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
            provider_mode = str(body.pop("provider_mode", "mock") or "mock").strip()
            if provider_mode not in {"mock", "hybrid"}:
                yield emitter.event(
                    "error",
                    code="invalid_input",
                    message="provider_mode은 mock 또는 hybrid여야 해요.",
                    retryable=False,
                )
                return
            request_model = SearchRequest.model_validate(body)
            providers = (
                hybrid_demo_provider_bundle()
                if provider_mode == "hybrid"
                else mock_provider_bundle()
            )

            yield emitter.event("status", text="항공·숙소·장소 후보를 검색하고 있어요")
            result = await run_search(request_model, providers)

            yield emitter.event("status", text="검색 결과를 Plan Agent 입력으로 정리하고 있어요")
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
