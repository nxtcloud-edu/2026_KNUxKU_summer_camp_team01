'use client';

import { Brain, Check, Circle, Loader2, Sparkles, Wrench } from 'lucide-react';

export function AgentPanel({ type = '항공권', progress = 62 }: { type?: string; progress?: number }) {
  return (
    <section className="agent-panel" aria-live="polite">
      <header className="agent-panel__header">
        <span><Sparkles size={16} /> {type}을 찾고 있어요</span>
        <button className="text-button">중단</button>
      </header>
      <div className="agent-progress"><span style={{ width: `${progress}%` }} /></div>
      <div className="agent-panel__body">
        <div className="agent-label"><Brain size={15} /> 추론</div>
        <p>여행 날짜와 인원, 선택하신 취향을 함께 살펴보고 있어요.</p>
        <p className="agent-thought">가격과 이동 시간, 일정에 주는 영향을 비교해 가장 균형 잡힌 결과를 고릅니다.<span className="stream-cursor" /></p>
        <div className="tool-card is-done">
          <Wrench size={15} />
          <div><code>search_candidates</code><strong>후보 데이터베이스 조회</strong><small>128개 결과 확인</small></div>
          <Check size={15} />
        </div>
        <div className="tool-card">
          <Wrench size={15} />
          <div><code>apply_constraints</code><strong>여행 조건과 취향 반영 중</strong><small>추천 순위를 계산하고 있어요</small></div>
          <Loader2 className="spin" size={15} />
        </div>
        <div className="agent-mini-steps">
          <span className="done"><Check size={13} /> 조건 분석</span>
          <span className="active"><Loader2 className="spin" size={13} /> 결과 비교</span>
          <span><Circle size={13} /> 추천 정리</span>
        </div>
      </div>
    </section>
  );
}
