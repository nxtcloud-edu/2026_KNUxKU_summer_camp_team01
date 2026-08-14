"""Supervisor FastAPI 서버 — 전체 파이프라인을 하나의 SSE 엔드포인트로 노출한다.

    POST /agent/plan   SearchToPlanInput -> { plan, verification, reports }

하위 에이전트의 진행 상황을 모아 사용자에게 하나의 스트림으로 보여준다.
이벤트는 `agent/schemas/agent-event.schema.json`의 4종만 쓴다.

## 하위 이벤트를 그대로 흘리지 않는다

하위가 보낸 `seq`를 그대로 재발행하면 번호가 겹쳐 계약을 어긴다. supervisor가
자기 번호로 다시 만든다. 하위의 `status` 문구는 내용만 가져온다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse

from .config import CONFIG, describe
from .clients import AgentCallFailed, call_agent
from .graph import run_pipeline
from .sse import SSE_HEADERS, SseEmitter

logging.basicConfig(
    level=getattr(logging, CONFIG.log_level, logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Voyagent Supervisor", version="0.1.0")


@app.on_event("startup")
async def _log_config() -> None:
    for line in describe():
        logger.info(line)


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
        "plan_url": CONFIG.plan_url,
        "verification_url": CONFIG.verification_url,
        "search_url": CONFIG.search_url,
        "hard_timeout_ms": CONFIG.hard_timeout_ms,
    }


@app.post("/agent/search")
async def search_pipeline(request: Request) -> StreamingResponse:
    """Search Agent를 Supervisor의 공개 SSE 계약 뒤에 숨긴다."""

    try:
        source = await request.json()
    except Exception:

        async def bad_json() -> AsyncIterator[str]:
            emitter = SseEmitter()
            yield emitter.error(
                code="invalid_input",
                message="요청 본문이 JSON이 아니에요.",
                retryable=False,
            )

        return _stream(bad_json())

    async def events() -> AsyncIterator[str]:
        emitter = SseEmitter()
        try:
            yield emitter.status("검색 에이전트에 조건을 전달하고 있어요")
            yield emitter.progress(0.05)
            result = await call_agent(
                agent="search",
                url=f"{CONFIG.search_url}/agent/search",
                body=source,
                timeout_ms=CONFIG.search_timeout_ms,
            )
            yield emitter.progress(1.0)
            yield emitter.done(payload=result.payload, summary=result.summary)
        except AgentCallFailed as error:
            yield emitter.error(
                code=error.code, message=error.message, retryable=error.retryable
            )
        except Exception:
            logger.exception("search supervisor 실행 중 예외")
            if not emitter.terminated:
                yield emitter.error(
                    code="agent_failed",
                    message="검색을 완료하지 못했어요.",
                    retryable=True,
                )

    return _stream(events())


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request: Request, error: RequestValidationError
) -> StreamingResponse:
    logger.warning("입력 스키마 위반: %s", error.errors()[:3])

    async def events() -> AsyncIterator[str]:
        emitter = SseEmitter()
        yield emitter.error(
            code="invalid_input",
            message="입력 형식이 계약과 맞지 않아요.",
            retryable=False,
        )

    return _stream(events())


@app.post("/agent/plan")
async def plan_pipeline(request: Request) -> StreamingResponse:
    """Search 결과를 받아 일정 생성과 검증까지 한 번에 수행한다.

    입력 스키마 검증은 Plan Agent가 하므로 여기서는 JSON 파싱만 한다.
    supervisor가 같은 검증을 중복하면 계약이 두 곳에 생긴다.
    """

    try:
        source = await request.json()
    except Exception:

        async def bad_json() -> AsyncIterator[str]:
            emitter = SseEmitter()
            yield emitter.error(
                code="invalid_input",
                message="요청 본문이 JSON이 아니에요.",
                retryable=False,
            )

        return _stream(bad_json())

    async def events() -> AsyncIterator[str]:
        emitter = SseEmitter()
        # 하위 진행 문구를 모았다가 순서대로 내보낸다.
        progress_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        def on_progress(agent: str, text: str) -> None:
            progress_queue.put_nowait((agent, text))

        try:
            yield emitter.status("일정 생성을 준비하고 있어요")
            yield emitter.progress(0.05)

            task = asyncio.create_task(run_pipeline(source, on_progress))

            # 하위 진행 문구를 흘리면서 완료를 기다린다.
            emitted = 0
            while not task.done():
                try:
                    agent, text = await asyncio.wait_for(
                        progress_queue.get(), timeout=0.4
                    )
                except asyncio.TimeoutError:
                    continue
                if text:
                    emitted += 1
                    yield emitter.status(text)
                    # 하위 단계 수에 비례해 대략적인 진행률을 만든다.
                    yield emitter.progress(min(0.9, 0.1 + emitted * 0.1))

            state = await task

            if await request.is_disconnected():
                return

            if state["plan"] is None:
                reason = (
                    state["failures"][0]
                    if state["failures"]
                    else "일정을 만들 수 없었어요."
                )
                logger.error("파이프라인 실패: %s", state["failures"])
                yield emitter.error(code="agent_failed", message=reason, retryable=True)
                return

            day_count = len(state["plan"].get("plan", {}).get("days", []))
            item_count = sum(
                len(day.get("items", []))
                for day in state["plan"].get("plan", {}).get("days", [])
            )
            verification = state["verification"]
            if verification is None:
                verdict = "검증은 건너뛰었어요."
            elif verification.get("possible"):
                verdict = "실행 가능한 일정이에요."
            else:
                verdict = "일부 조건을 다시 살펴봐야 해요."

            summary = f"{day_count}일 {item_count}개 일정을 만들었어요. {verdict}"

            yield emitter.progress(1.0)
            yield emitter.done(
                payload={
                    "plan": state["plan"],
                    "verification": verification,
                    "acceptance": [
                        {
                            "agent": report.agent,
                            "ok": report.ok,
                            "checked": report.checked,
                            "failures": report.failures,
                        }
                        for report in state["reports"]
                    ],
                    "warnings": state["failures"],
                },
                summary=summary,
            )
            logger.info(
                "파이프라인 완료: %d일 %d항목, 재하달 %d회, 경고 %d건",
                day_count,
                item_count,
                state["reissue_count"],
                len(state["failures"]),
            )

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("supervisor 실행 중 예외")
            if not emitter.terminated:
                yield emitter.error(
                    code="agent_failed",
                    message="일정을 만들지 못했어요.",
                    retryable=True,
                )
        finally:
            if not emitter.terminated:
                logger.error("종료 이벤트 없이 스트림이 끝나려 했습니다.")
                yield emitter.error(
                    code="agent_failed",
                    message="일정 생성이 예상치 못하게 중단됐어요.",
                    retryable=True,
                )

    return _stream(events())


__all__ = ["app"]
