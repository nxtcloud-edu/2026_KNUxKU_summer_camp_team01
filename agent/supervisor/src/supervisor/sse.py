"""Supervisor SSE 이벤트 발행.

`agent/schemas/agent-event.schema.json`의 4종만 쓴다.
plan-agent의 `sse.py`와 같은 구조다. 두 서비스의 이벤트 모양이 같아야
프론트가 한 가지 방법으로 소비할 수 있다.

하위 에이전트가 보낸 `seq`를 그대로 재발행하지 않는다. 번호가 겹치면 계약
위반이므로 supervisor가 자기 번호로 다시 만든다.
"""

from __future__ import annotations

import json
import time
from typing import Any, Literal

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    # 없으면 중간 프록시가 응답을 모아 보내 스트리밍 연출이 사라진다.
    "X-Accel-Buffering": "no",
}

ErrorCode = Literal["invalid_input", "timeout", "rate_limit", "agent_failed"]


class TerminalEventAlreadySent(RuntimeError):
    """`done`/`error`를 두 번 보내려 했다. 계약 위반이다."""


class SseEmitter:
    def __init__(self) -> None:
        self._started_at = time.monotonic()
        self._seq = 0
        self._terminated = False
        self._last_progress = 0.0

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started_at) * 1000)

    @property
    def terminated(self) -> bool:
        return self._terminated

    def _event(self, event_type: str, **fields: Any) -> str:
        payload = {
            "seq": self._seq,
            "at": self.elapsed_ms,
            "type": event_type,
            **fields,
        }
        self._seq += 1
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return f"data: {encoded}\n\n"

    def status(self, text: str) -> str:
        return self._event("status", text=text[:100] or "처리 중이에요")

    def progress(self, value: float) -> str:
        """0~1 진행률. 계약이 단조 증가를 요구하므로 역행을 막는다."""

        clamped = min(1.0, max(0.0, value))
        self._last_progress = max(self._last_progress, clamped)
        return self._event("progress", value=round(self._last_progress, 3))

    def done(self, payload: Any, summary: str | None = None) -> str:
        self._mark_terminated()
        fields: dict[str, Any] = {"payload": payload}
        if summary:
            fields["summary"] = summary[:200]
        return self._event("done", **fields)

    def error(self, code: ErrorCode, message: str, retryable: bool) -> str:
        self._mark_terminated()
        return self._event(
            "error",
            code=code,
            message=message[:200] or "일정을 만들지 못했어요.",
            retryable=retryable,
        )

    def _mark_terminated(self) -> None:
        if self._terminated:
            raise TerminalEventAlreadySent(
                "done 또는 error를 이미 보냈습니다. 종료 이벤트는 정확히 하나입니다."
            )
        self._terminated = True


__all__ = ["ErrorCode", "SSE_HEADERS", "SseEmitter", "TerminalEventAlreadySent"]
