"""FastAPI SSE 서버 — POST /agent/itineraryGenerate.

verification-agent의 `main.py`와 같은 구조다. 두 서비스의 전송 계층이 같아야
프론트가 한 가지 방법으로 소비할 수 있다.

## 종료 이벤트 보장이 가장 중요하다

스트림이 `done`이나 `error` 없이 끝나면 화면이 **영원히 로딩 상태**로 남는다.
이게 이 계층에서 가장 나쁜 실패다. 그래서 모든 경로를 감싸고, `finally`에서
아직 종료 이벤트가 안 나갔으면 `error`를 보낸다.

## HTTP 상태 코드에 의미를 담지 않는다

입력 검증 실패도 **200 + error 이벤트**로 응답한다. 4xx로 응답하면 프론트의
SSE 소비자가 이벤트를 못 받아 사용자에게 아무 설명 없는 빈 화면이 남는다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse

from .config import CONFIG, describe_capabilities
from .graph import generate_itinerary
from .models import SearchToPlanInput
from .quota import BUDGET
from .sse import SSE_HEADERS, SseEmitter

logging.basicConfig(
    level=getattr(logging, CONFIG.log_level, logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Voyagent Plan Agent", version="0.1.0")


@app.on_event("startup")
async def _log_capabilities() -> None:
    """무엇이 켜져 있고 무엇이 추정으로 대체되는지 기동 시 남긴다."""

    for line in describe_capabilities():
        logger.info(line)
    logger.info(BUDGET.describe())


def _stream(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        status_code=200,
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "routes_api": CONFIG.has_routes_api,
        "gemini": CONFIG.has_gemini,
        "routes_calls_used": BUDGET.total_used,
    }


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request: Request, error: RequestValidationError
) -> StreamingResponse:
    """스키마 위반. 4xx가 아니라 200 + error 이벤트로 알린다."""

    logger.warning("입력 스키마 위반: %s", error.errors()[:3])

    async def events() -> AsyncIterator[str]:
        emitter = SseEmitter()
        yield emitter.error(
            code="invalid_input",
            message="입력 형식이 계약과 맞지 않아요.",
            retryable=False,
        )

    return _stream(events())


@app.post("/agent/itineraryGenerate")
async def itinerary_generate(
    payload: SearchToPlanInput, request: Request
) -> StreamingResponse:
    """선택된 장소를 일자별 일정으로 배치한다."""

    async def events() -> AsyncIterator[str]:
        emitter = SseEmitter()
        try:
            yield emitter.status("여행 조건을 확인하고 있어요")
            yield emitter.progress(0.1)
            await asyncio.sleep(0)

            if await request.is_disconnected():
                return

            yield emitter.status("장소를 날짜별로 배치하고 있어요")
            yield emitter.progress(0.35)

            try:
                # 자기 작업 예산만 본다. Search -> Plan -> Verification 전체
                # 파이프라인의 시간 배분은 supervisor가 관리하며, 여기서는
                # 그중 Plan에 할당된 몫(PLAN_AGENT_TIMEOUT_MS)만 지킨다.
                # 전체 상한(AGENT_HARD_TIMEOUT_MS)을 여기서 쓰면 supervisor와
                # 두 곳에서 같은 예산을 해석해 어긋난다.
                result, diagnostics = await asyncio.wait_for(
                    generate_itinerary(payload),
                    timeout=CONFIG.own_timeout_ms / 1000,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Plan Agent 작업 상한 %dms를 초과했습니다.", CONFIG.own_timeout_ms
                )
                yield emitter.error(
                    code="timeout",
                    message="일정을 만드는 데 예상보다 오래 걸리고 있어요.",
                    retryable=True,
                )
                return

            if await request.is_disconnected():
                return

            if result is None:
                # 결정론 계층이 계약을 지키는 일정을 만들 수 없었다.
                # 왜 못 만들었는지 사용자에게 알린다. 조용히 실패하지 않는다.
                reason = (
                    diagnostics.violations[0].message
                    if diagnostics.violations
                    else "조건에 맞는 일정을 만들 수 없었어요."
                )
                logger.error(
                    "일정 생성 실패: %s",
                    [violation.code for violation in diagnostics.violations],
                )
                yield emitter.error(
                    code="agent_failed",
                    message=reason,
                    retryable=False,
                )
                return

            yield emitter.status("배치 이유를 정리하고 있어요")
            yield emitter.progress(0.8)

            item_count = sum(len(day.items) for day in result.plan.days)
            summary = diagnostics.summary_line(len(result.plan.days), item_count)

            yield emitter.progress(1.0)
            yield emitter.done(
                payload=result.model_dump(mode="json"),
                summary=summary,
            )
            logger.info(
                "일정 생성 완료: %d일 %d항목, %s",
                len(result.plan.days),
                item_count,
                BUDGET.describe(),
            )

        except asyncio.CancelledError:
            # 클라이언트가 끊었다. 이벤트를 더 보내지 않는다.
            raise
        except Exception:
            logger.exception("plan agent 실행 중 예외")
            if not emitter.terminated and not await request.is_disconnected():
                yield emitter.error(
                    code="agent_failed",
                    message="일정을 만들지 못했어요.",
                    retryable=True,
                )
        finally:
            # 어떤 경로로 빠져나가도 종료 이벤트가 하나는 나가야 한다.
            # 이게 없으면 화면이 영원히 로딩 상태로 남는다.
            if not emitter.terminated:
                logger.error("종료 이벤트 없이 스트림이 끝나려 했습니다.")
                yield emitter.error(
                    code="agent_failed",
                    message="일정 생성이 예상치 못하게 중단됐어요.",
                    retryable=True,
                )

    return _stream(events())


__all__ = ["app"]
