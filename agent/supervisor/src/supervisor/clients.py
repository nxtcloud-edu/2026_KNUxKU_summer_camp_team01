"""하위 에이전트 호출 — SSE 스트림을 소비해 결과를 꺼낸다.

세 에이전트는 모두 `text/event-stream`으로 응답한다. supervisor는 그 스트림을
읽어 종료 이벤트(`done` 또는 `error`)를 찾아 결과를 얻는다.

## 종료 이벤트가 없으면 실패로 본다

하위가 `done`/`error` 없이 스트림을 끝내면 그건 하위의 계약 위반이다. 그때
`None`을 돌려주고 조용히 넘어가면 supervisor가 "결과가 없다"와 "빈 결과다"를
구분할 수 없다. 그래서 `AgentCallFailed`를 던져 명확히 실패로 만든다.

## 진행 이벤트는 그대로 위로 흘린다

하위의 `status`/`progress`를 콜백으로 넘겨, supervisor가 사용자에게 전체
진행 상황을 보여줄 수 있게 한다. 하위 이벤트를 그대로 재발행하지는 않는다
(`seq`가 겹치기 때문). supervisor가 자기 번호로 다시 만든다.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str], None]
"""(단계 이름, 진행 문구) -> None"""


class AgentCallFailed(RuntimeError):
    """하위 에이전트 호출이 실패했다.

    `code`는 하위가 보낸 `error.code`이거나, 전송 자체가 실패했으면
    `transport`다.
    """

    def __init__(self, agent: str, code: str, message: str, retryable: bool) -> None:
        super().__init__(f"{agent}: [{code}] {message}")
        self.agent = agent
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass
class AgentResult:
    payload: Any
    summary: str | None
    event_count: int


async def call_agent(
    *,
    agent: str,
    url: str,
    body: dict,
    timeout_ms: int,
    on_progress: ProgressCallback | None = None,
) -> AgentResult:
    """하위 에이전트를 호출하고 `done.payload`를 반환한다.

    실패하면 `AgentCallFailed`를 던진다. 조용히 None을 돌려주지 않는다.
    """

    timeout = httpx.Timeout(timeout_ms / 1000, connect=5.0)
    event_count = 0

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                url,
                json=body,
                headers={"Accept": "text/event-stream"},
            ) as response:
                if response.status_code != 200:
                    body_text = (await response.aread()).decode("utf-8", "replace")
                    raise AgentCallFailed(
                        agent,
                        "transport",
                        f"HTTP {response.status_code}: {body_text[:200]}",
                        retryable=response.status_code >= 500,
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[len("data:") :].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("%s: JSON이 아닌 이벤트를 건너뜁니다.", agent)
                        continue

                    event_count += 1
                    event_type = event.get("type")

                    if event_type == "status" and on_progress is not None:
                        on_progress(agent, str(event.get("text", "")))
                    elif event_type == "done":
                        return AgentResult(
                            payload=event.get("payload"),
                            summary=event.get("summary"),
                            event_count=event_count,
                        )
                    elif event_type == "error":
                        raise AgentCallFailed(
                            agent,
                            str(event.get("code", "agent_failed")),
                            str(event.get("message", "알 수 없는 오류")),
                            retryable=bool(event.get("retryable", False)),
                        )

    except httpx.TimeoutException as error:
        raise AgentCallFailed(
            agent, "timeout", f"{timeout_ms}ms 안에 응답하지 않았습니다", retryable=True
        ) from error
    except httpx.HTTPError as error:
        raise AgentCallFailed(
            agent, "transport", f"연결 실패: {error}", retryable=True
        ) from error

    # 스트림이 종료 이벤트 없이 끝났다. 하위의 계약 위반이다.
    raise AgentCallFailed(
        agent,
        "agent_failed",
        f"종료 이벤트 없이 스트림이 끝났습니다 (이벤트 {event_count}건)",
        retryable=True,
    )


__all__ = ["AgentCallFailed", "AgentResult", "ProgressCallback", "call_agent"]
