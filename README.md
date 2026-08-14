# 2026_KNUxKU_summer_camp_team01

강원대x고려대 Summer Agentic AI 심화 몰입 캠프 1팀 레포지토리입니다.

## JustGO — AI 여행 플래너

> 도시와 날짜만 정하면, AI 에이전트가 항공권·숙소·관광지를 찾아 **검증된 여행 일정표**까지 만들어 주는 웹앱.

사용자가 확정하는 것은 **목적지와 날짜 두 개**뿐이다. 이후 여행 스타일 설문을 거치면 에이전트가 항공권과 숙소를 찾아 주고, 관심사에 맞는 관광지를 큐레이션해 보여주며, 선택한 장소로 일자별 일정을 짠 뒤 물리적 시간·휴관일·예산은 결정론 규칙으로, 페이스·걷기 수준은 AI로 점검한다.

## 현재 상태

**프론트엔드 UI/UX 설계 완료.** 코드 구현 착수 전 단계다.
백엔드와 에이전트는 목(mock)으로 가정하되, 실제 에이전트로 교체할 수 있는 계약까지 정의되어 있다.

## 문서

| 문서 | 내용 | 주 독자 |
|---|---|---|
| [`spec.md`](./spec.md) | 프론트엔드 UI/UX 전체 명세 (15장). 화면 10개의 와이어프레임·컴포넌트 규격·인터랙션·상태·한국어 카피, 전체 TypeScript 타입, 목 데이터와 에이전트 스트리밍 계약, 검증 규칙 10개, 테스트 전략, 구현 로드맵 | 전원 |
| [`design.md`](./design.md) | 위 명세를 v0 / Figma AI / Cursor 등 AI 디자인 도구용 프롬프트로 변환한 세트. 공통 시스템 프롬프트 + 화면별 10개 + 컴포넌트 8개 + 교정용 프롬프트 | 디자인 · FE |
| [`agent/`](./agent/README.md) | **AI 에이전트 계약.** Search→Plan 및 Plan→Verification canonical schema, fixture, 계약 검사 도구와 검증 에이전트 구현 | 에이전트 · FE |

**처음 보는 사람은** `spec.md`의 0장(문서 개요)과 1장(제품 개요)만 읽으면 전체를 파악할 수 있다.
**바로 만들어 보려면** `design.md`의 B절(공통 시스템 프롬프트)과 C-1(홈 화면)을 v0에 붙여넣는다.
**에이전트를 만든다면** [`agent/README.md`](./agent/README.md)의 5분 요약부터 읽는다.

### `agent/` 폴더 안내

| 파일 | 내용 |
|---|---|
| [`agent/README.md`](./agent/README.md) | 두 handoff 계약과 검증 에이전트 워크플로 |
| [`agent/schemas/search-to-plan.schema.json`](./agent/schemas/search-to-plan.schema.json) | Search Agent → Plan Agent 입력 계약 |
| [`agent/schemas/plan-to-verification.schema.json`](./agent/schemas/plan-to-verification.schema.json) | Plan Agent → Verification Agent 입력 계약 |
| `agent/fixtures/` | 각 handoff와 1:1로 대응하는 예제 |
| [`agent/tools/conformance.mjs`](./agent/tools/conformance.mjs) | schema·fixture·단계 간 연속성 검사 |

```powershell
node agent/tools/conformance.mjs
```

## 계획된 스택

| 레이어 | 채택 |
|---|---|
| 프레임워크 | Next.js 15 (App Router) + TypeScript |
| 스타일 | Tailwind CSS + shadcn/ui, OKLCH 토큰 |
| 상태 | Zustand (+ localStorage 지속화) + TanStack Query |
| 지도 | Google Maps JavaScript API (`@react-google-maps/api`, **API 키 필요** — `.env.example` 참고) |
| 드래그&드롭 | dnd-kit |
| 에이전트 | 목 스트리밍 계층 → `MockTransport` ↔ `SseTransport` 교체 가능 |
| 배포 | Vercel |

자세한 근거와 의존성 목록은 [`spec.md` 2장](./spec.md#2-기술-스택과-프로젝트-구조)에 있다.

## 화면 흐름

```
홈 → 도시·날짜 → 여행 스타일 → (항공권) → (숙소) → 가고 싶은 곳 → 일정 → 검증 → 공유·인쇄
```

괄호로 묶인 두 단계는 사용자가 "함께 찾아드릴까요?"에 **아니요**라고 답하면 건너뛴다.

## 다음 단계

**프론트엔드** — [`spec.md` 14장 구현 로드맵](./spec.md#14-구현-로드맵)의 26단계를 순서대로 진행한다.
시간이 부족할 때의 최소 데모 경로는 [14.3](./spec.md#143-최소-데모-경로-시간이-부족할-때)에 정리되어 있다.

## 백엔드 API

백엔드는 Next.js App Router의 서버 라우트로 실행되며, live 모드에서는 로컬 Supervisor를 통해 Search → Plan → Verification 파이프라인을 호출한다.

```bash
npm ci
npm run dev

# 상태 확인
curl http://localhost:3000/api/health

# SSE 에이전트 호출
curl -N -X POST http://localhost:3000/api/agent/flightSearch \
  -H "Content-Type: application/json" \
  -d '{"originId":"seoul","destinationId":"tokyo"}'
```

지원 작업은 `flightSearch`, `staySearch`, `placeDiscovery`, `itineraryGenerate`, `itineraryVerify`다. 응답은 `text/event-stream`이며 각 프레임은 명세 6.3의 `AgentEvent` JSON을 `data:` 필드에 담는다. `GET /api/health`는 배포 후 헬스 체크에 사용한다.

전체 검증은 `npm run check`로 실행한다. SSE 연출 속도는 선택적으로 `AGENT_STREAM_DELAY_MS`(0~2000ms)로 조절할 수 있다.

**에이전트** — [`agent/README.md`](./agent/README.md)의 Search→Plan→Verification handoff를 기준으로 구현하고, 변경 시 schema와 fixture를 함께 갱신한다.

```powershell
node agent/tools/conformance.mjs
```
