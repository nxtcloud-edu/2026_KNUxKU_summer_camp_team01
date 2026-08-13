from __future__ import annotations

import json
import time
from typing import Any

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class SseEmitter:
    def __init__(self) -> None:
        self._started_at = time.monotonic()
        self._seq = 0

    def event(self, event_type: str, **fields: Any) -> str:
        payload = {
            "seq": self._seq,
            "at": int((time.monotonic() - self._started_at) * 1000),
            "type": event_type,
            **fields,
        }
        self._seq += 1
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return f"data: {encoded}\n\n"
