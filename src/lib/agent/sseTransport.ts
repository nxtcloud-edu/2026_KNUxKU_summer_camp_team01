'use client';

import type { AgentEvent, AgentTaskId } from '@/lib/agent/contracts';

type ProblemDetails = { detail?: string; title?: string };

export async function* streamAgentEvents(
  task: AgentTaskId,
  input: unknown,
  signal: AbortSignal,
): AsyncGenerator<AgentEvent> {
  const response = await fetch(`/api/agent/${task}`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
    cache: 'no-store',
    signal,
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({})) as ProblemDetails;
    throw new Error(problem.detail ?? problem.title ?? `에이전트 요청에 실패했습니다 (${response.status})`);
  }
  if (!response.body) throw new Error('스트리밍 응답 본문이 없습니다.');

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    buffer += value ?? '';
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      const data = frame.split(/\r?\n/)
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n');
      if (!data) continue;
      yield JSON.parse(data) as AgentEvent;
    }
    if (done) break;
  }
}
