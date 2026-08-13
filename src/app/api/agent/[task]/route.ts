import { createAgentEvents } from '@/lib/agent/events';
import { isAgentTask } from '@/lib/agent/contracts';
import { AgentInputError, validateTaskInput } from '@/lib/agent/service';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 30;

const encoder = new TextEncoder();
const MAX_BODY_BYTES = 1_000_000;

const problem = (status: number, title: string, detail: string) => Response.json(
  { type: 'about:blank', title, status, detail },
  { status, headers: { 'Cache-Control': 'no-store', 'Content-Type': 'application/problem+json' } },
);

export async function POST(request: Request, context: { params: Promise<{ task: string }> }) {
  const { task } = await context.params;
  if (!isAgentTask(task)) return problem(404, 'Unknown agent task', `지원하지 않는 작업입니다: ${task}`);

  const contentLength = Number(request.headers.get('content-length') ?? 0);
  if (contentLength > MAX_BODY_BYTES) return problem(413, 'Payload too large', '요청 본문은 1MB 이하여야 합니다.');

  let input: unknown;
  try {
    input = await request.json();
    validateTaskInput(task, input);
  } catch (error) {
    const detail = error instanceof AgentInputError ? error.message : '올바른 JSON 요청 본문이 필요합니다.';
    return problem(400, 'Invalid agent input', detail);
  }

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        for await (const event of createAgentEvents(task, input, request.signal)) {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
        }
      } catch (error) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'error', code: 'agent_failed', message: error instanceof Error ? error.message : '에이전트 실행에 실패했습니다.', retryable: true })}\n\n`));
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}

export async function GET(_request: Request, context: { params: Promise<{ task: string }> }) {
  const { task } = await context.params;
  if (!isAgentTask(task)) return problem(404, 'Unknown agent task', `지원하지 않는 작업입니다: ${task}`);
  return Response.json({ task, method: 'POST', contentType: 'application/json', responseType: 'text/event-stream' });
}
