from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse

from .graph import verify_plan
from .models import PlanToVerificationInput
from .sse import SSE_HEADERS, SseEmitter

logger = logging.getLogger(__name__)

app = FastAPI(title="Voyagent Verification Agent", version="0.1.0")


def _stream(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        status_code=200,
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


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


@app.post("/agent/itineraryVerify")
async def verify_itinerary(
    payload: PlanToVerificationInput, request: Request
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        emitter = SseEmitter()
        yield emitter.event("status", text="일정 가능 여부를 확인하고 있어요.")
        await asyncio.sleep(0)

        if await request.is_disconnected():
            return

        try:
            result = await verify_plan(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("verification agent failed")
            if not await request.is_disconnected():
                yield emitter.event(
                    "error",
                    code="agent_failed",
                    message="일정을 검증하지 못했어요.",
                    retryable=True,
                )
            return

        if await request.is_disconnected():
            return

        summary = (
            "현재 정보로 실행 가능한 일정이에요."
            if result.possible
            else "현재 정보로 실행하기 어려운 일정이에요."
        )
        yield emitter.event(
            "done",
            payload=result.model_dump(mode="json", exclude_none=True),
            summary=summary,
        )

    return _stream(events())
