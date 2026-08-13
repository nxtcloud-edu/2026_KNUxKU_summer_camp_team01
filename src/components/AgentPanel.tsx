'use client';

import { useEffect, useRef, useState } from 'react';
import { Brain, Check, Circle, Loader2, Sparkles, Wrench } from 'lucide-react';

import type { AgentTaskId } from '@/lib/agent/contracts';
import { streamAgentEvents } from '@/lib/agent/sseTransport';

type ToolState = { id: string; name: string; label: string; resultLabel?: string; ok?: boolean };

export function AgentPanel({
  type = '항공권',
  task,
  input,
  onDone,
  onAbort,
}: {
  type?: string;
  task: AgentTaskId;
  input: unknown;
  onDone?: (payload: unknown) => void;
  onAbort?: () => void;
}) {
  const [status, setStatus] = useState(`${type}을 찾고 있어요`);
  const [thought, setThought] = useState('여행 날짜와 인원, 선택하신 취향을 함께 살펴보고 있어요.');
  const [tools, setTools] = useState<ToolState[]>([]);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const onDoneRef = useRef(onDone);
  const onAbortRef = useRef(onAbort);
  const inputKey = JSON.stringify(input);

  useEffect(() => {
    onDoneRef.current = onDone;
    onAbortRef.current = onAbort;
  }, [onAbort, onDone]);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    const consume = async () => {
      try {
        for await (const event of streamAgentEvents(task, JSON.parse(inputKey) as unknown, controller.signal)) {
          if (event.type === 'status') setStatus(event.text);
          if (event.type === 'thought') setThought(event.text);
          if (event.type === 'progress') setProgress(Math.round(event.value * 100));
          if (event.type === 'tool_call') setTools((current) => [...current, { id: event.id, name: event.name, label: event.label }]);
          if (event.type === 'tool_result') setTools((current) => current.map((tool) => tool.id === event.id ? { ...tool, resultLabel: event.label, ok: event.ok } : tool));
          if (event.type === 'error' && event.code !== 'aborted') setError(event.message);
          if (event.type === 'done') onDoneRef.current?.(event.payload);
        }
      } catch (streamError) {
        if (!controller.signal.aborted) setError(streamError instanceof Error ? streamError.message : '에이전트 연결에 실패했습니다.');
      }
    };
    void consume();
    return () => controller.abort();
  }, [inputKey, retryKey, task]);

  const abort = () => {
    abortRef.current?.abort();
    onAbortRef.current?.();
  };

  const retry = () => {
    setError(null);
    setTools([]);
    setProgress(0);
    setRetryKey((current) => current + 1);
  };

  return (
    <section className="agent-panel" aria-live="polite">
      <header className="agent-panel__header">
        <span><Sparkles size={16} /> {status}</span>
        <button className="text-button" type="button" onClick={abort}>중단</button>
      </header>
      <div className="agent-progress"><span style={{ width: `${progress}%` }} /></div>
      <div className="agent-panel__body">
        <div className="agent-label"><Brain size={15} /> 추론</div>
        <p className="agent-thought">{thought}<span className="stream-cursor" /></p>
        {error && <p role="alert">{error} <button className="text-button" type="button" onClick={retry}>다시 시도</button></p>}
        {tools.map((tool) => (
          <div className={`tool-card ${tool.resultLabel ? 'is-done' : ''}`} key={tool.id}>
            <Wrench size={15} />
            <div><code>{tool.name}</code><strong>{tool.label}</strong><small>{tool.resultLabel ?? '실행하고 있어요'}</small></div>
            {tool.resultLabel ? <Check size={15} /> : <Loader2 className="spin" size={15} />}
          </div>
        ))}
        <div className="agent-mini-steps">
          <span className={progress >= 25 ? 'done' : 'active'}>{progress >= 25 ? <Check size={13} /> : <Loader2 className="spin" size={13} />} 조건 분석</span>
          <span className={progress >= 70 ? 'done' : progress >= 25 ? 'active' : ''}>{progress >= 70 ? <Check size={13} /> : progress >= 25 ? <Loader2 className="spin" size={13} /> : <Circle size={13} />} 결과 비교</span>
          <span className={progress >= 100 ? 'done' : progress >= 70 ? 'active' : ''}>{progress >= 100 ? <Check size={13} /> : progress >= 70 ? <Loader2 className="spin" size={13} /> : <Circle size={13} />} 추천 정리</span>
        </div>
      </div>
    </section>
  );
}
