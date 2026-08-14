import type { AgentEvent, AgentTaskId } from '@/lib/agent/contracts';
import { resolveTask } from '@/lib/agent/service';

type EventWithoutMeta = AgentEvent extends infer Event
  ? Event extends AgentEvent ? Omit<Event, 'seq' | 'at'> : never
  : never;

const TASK_COPY: Record<AgentTaskId, { status: string; thought: string; tool: string; label: string }> = {
  flightSearch: { status: '검색 조건을 정리하고 있어요', thought: '가격과 소요 시간, 도착 시각을 함께 비교합니다.', tool: 'search_flights', label: '항공편 데이터베이스 조회 중' },
  staySearch: { status: '숙소 조건을 확인하고 있어요', thought: '위치와 가격, 평점을 함께 비교합니다.', tool: 'search_stays', label: '숙소 데이터베이스 조회 중' },
  placeDiscovery: { status: '도시의 장소를 살펴보고 있어요', thought: '관심사와 여행 페이스에 맞는 장소를 우선합니다.', tool: 'search_places', label: '장소 정보 수집 중' },
  itineraryGenerate: { status: '일정을 설계하고 있어요', thought: '같은 지역을 묶고 이동 시간을 줄여 일자별로 배치합니다.', tool: 'build_itinerary', label: '일정 후보 계산 중' },
  itineraryVerify: { status: '일정을 검증하고 있어요', thought: '영업시간, 이동, 일정량과 예약 필요 여부를 점검합니다.', tool: 'verify_itinerary', label: '검증 규칙 실행 중' },
};

const wait = (ms: number, signal: AbortSignal) => new Promise<void>((resolve, reject) => {
  if (signal.aborted) return reject(signal.reason);
  const timer = setTimeout(resolve, ms);
  signal.addEventListener('abort', () => {
    clearTimeout(timer);
    reject(signal.reason);
  }, { once: true });
});

export async function* createAgentEvents(task: AgentTaskId, input: unknown, signal: AbortSignal): AsyncGenerator<AgentEvent> {
  const startedAt = Date.now();
  let seq = 0;
  const event = (value: EventWithoutMeta): AgentEvent => ({
    ...value,
    seq: seq++,
    at: Date.now() - startedAt,
  } as AgentEvent);
  const delay = Math.max(0, Math.min(2_000, Number(process.env.AGENT_STREAM_DELAY_MS ?? 180) || 0));
  const copy = TASK_COPY[task];

  try {
    yield event({ type: 'status', text: copy.status });
    await wait(delay, signal);
    yield event({ type: 'thought', id: 'thought-1', text: copy.thought, done: true });
    yield event({ type: 'progress', value: 0.25 });
    await wait(delay, signal);
    yield event({ type: 'tool_call', id: 'tool-1', name: copy.tool, label: copy.label });
    const result = resolveTask(task as never, input as never) as unknown;
    const count = Array.isArray(result) ? result.length : 1;
    await wait(delay, signal);
    yield event({ type: 'tool_result', id: 'tool-1', label: `${count}개 결과 확인`, count, ok: true });
    yield event({ type: 'progress', value: 0.7 });
    if (Array.isArray(result)) {
      for (const item of result.slice(0, 3)) yield event({ type: 'partial', payload: item });
    }
    await wait(delay, signal);
    yield event({ type: 'progress', value: 1 });
    yield event({ type: 'done', payload: result, summary: `${count}개 결과를 준비했어요.` });
  } catch {
    yield event({ type: 'error', code: 'aborted', message: '요청이 취소되었습니다.', retryable: true });
  }
}
