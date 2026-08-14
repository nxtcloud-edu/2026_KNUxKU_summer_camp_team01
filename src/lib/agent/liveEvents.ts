import type { AgentErrorCode, AgentEvent, AgentTaskId, AgentTaskInput } from '@/lib/agent/contracts';
import {
  fromSupervisorPayload,
  fromSearchPayload,
  fromVerificationPayload,
  SupervisorContractError,
  toSupervisorInput,
  toSearchInput,
  toVerificationInput,
} from '@/lib/agent/supervisor';

type UpstreamEvent = Record<string, unknown> & { type?: unknown };
type EventWithoutMeta = AgentEvent extends infer Event
  ? Event extends AgentEvent ? Omit<Event, 'seq' | 'at'> : never
  : never;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const normalizeErrorCode = (value: unknown): AgentErrorCode => {
  if (value === 'invalid_input' || value === 'timeout' || value === 'rate_limit' || value === 'agent_failed') return value;
  return 'agent_failed';
};

async function* parseSse(response: Response): AsyncGenerator<UpstreamEvent> {
  if (!response.body) throw new Error('에이전트 SSE 응답 본문이 없습니다.');
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
      const parsed = JSON.parse(data) as unknown;
      if (isRecord(parsed)) yield parsed;
    }
    if (done) break;
  }
}

export const liveAgentEnabled = () => process.env.AGENT_MODE === 'live';
export const demoAgentEnabled = () => process.env.AGENT_MODE === 'demo';

export async function* createLiveAgentEvents(
  task: AgentTaskId,
  input: AgentTaskInput[typeof task],
  requestSignal: AbortSignal,
): AsyncGenerator<AgentEvent> {
  const startedAt = Date.now();
  let seq = 0;
  let terminated = false;
  const event = (value: EventWithoutMeta): AgentEvent => ({
    ...value,
    seq: seq++,
    at: Date.now() - startedAt,
  } as AgentEvent);

  try {
    const trip = input.trip;
    const isGenerate = task === 'itineraryGenerate';
    const isVerify = task === 'itineraryVerify';
    const baseUrl = isVerify
      ? process.env.VERIFICATION_AGENT_URL ?? 'http://127.0.0.1:8003'
      : process.env.SUPERVISOR_AGENT_URL ?? 'http://127.0.0.1:8000';
    const path = isGenerate ? '/agent/plan' : isVerify ? '/agent/itineraryVerify' : '/agent/search';
    const body = isGenerate ? toSupervisorInput(trip) : isVerify ? toVerificationInput(trip) : toSearchInput(trip);
    const timeoutMs = Math.max(1_000, Number(process.env.AGENT_HARD_TIMEOUT_MS ?? 45_000) || 45_000);
    const signal = AbortSignal.any([requestSignal, AbortSignal.timeout(timeoutMs)]);
    const response = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
      method: 'POST',
      headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      signal,
    });
    if (!response.ok) throw new Error(`에이전트가 HTTP ${response.status}로 응답했습니다.`);
    if (!response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('에이전트 응답이 SSE가 아닙니다.');

    for await (const upstream of parseSse(response)) {
      if (upstream.type === 'status' && typeof upstream.text === 'string') yield event({ type: 'status', text: upstream.text });
      if (upstream.type === 'progress' && typeof upstream.value === 'number') yield event({ type: 'progress', value: upstream.value });
      if (upstream.type === 'done') {
        terminated = true;
        const payload = isGenerate
          ? fromSupervisorPayload(trip, upstream.payload)
          : isVerify
            ? { verification: fromVerificationPayload(upstream.payload) }
            : { search: fromSearchPayload(trip, upstream.payload) };
        yield event({ type: 'done', payload, summary: typeof upstream.summary === 'string' ? upstream.summary : undefined });
        return;
      }
      if (upstream.type === 'error') {
        terminated = true;
        yield event({
          type: 'error',
          code: normalizeErrorCode(upstream.code),
          message: typeof upstream.message === 'string' ? upstream.message : '에이전트 실행에 실패했습니다.',
          retryable: Boolean(upstream.retryable),
        });
        return;
      }
    }
    if (!terminated) yield event({ type: 'error', code: 'agent_failed', message: '에이전트 스트림이 완료 이벤트 없이 종료됐습니다.', retryable: true });
  } catch (error) {
    if (requestSignal.aborted) return;
    const invalidInput = error instanceof SupervisorContractError;
    yield event({
      type: 'error',
      code: invalidInput ? 'invalid_input' : error instanceof DOMException && error.name === 'TimeoutError' ? 'timeout' : 'network',
      message: error instanceof Error ? error.message : 'Supervisor 연결에 실패했습니다.',
      retryable: !invalidInput,
    });
  }
}
