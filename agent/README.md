# Voyagent — 에이전트 개발 문서

> **에이전트 개발을 맡은 팀원이 가장 먼저 읽는 문서다.**
> 상위 문서: [`../spec.md`](../spec.md) 프론트엔드 명세 · [`../design.md`](../design.md) 디자인 프롬프트

---

## 5분 요약

**만들어야 하는 것은 HTTP 엔드포인트 5개다.**

```
POST /agent/flightSearch        항공권 후보를 찾는다
POST /agent/staySearch          숙소 후보를 찾는다
POST /agent/placeDiscovery      관광지 40곳을 큐레이션한다
POST /agent/itineraryGenerate   선택된 장소를 일자별로 배치한다
POST /agent/itineraryVerify      완성된 일정을 10개 규칙으로 검증한다
```

각 엔드포인트는 JSON을 받아 **SSE 이벤트 스트림**을 돌려준다. 결과만 주는 게 아니라 **작업 과정을 실시간으로** 보낸다.

```
data: {"seq":0,"at":18,"type":"status","text":"검색 조건을 정리하고 있어요"}

data: {"seq":1,"at":520,"type":"thought","id":"t1","text":"인천(ICN) → 도쿄","done":false}

data: {"seq":4,"at":1180,"type":"tool_call","id":"c1","name":"search_flights","label":"항공편 데이터베이스 조회 중"}

data: {"seq":5,"at":2760,"type":"tool_result","id":"c1","label":"128개 항공편 확인","count":128,"ok":true}

data: {"seq":17,"at":6520,"type":"partial","payload":{"id":"f-001", ...}}

data: {"seq":21,"at":8380,"type":"done","payload":[...],"summary":"2개 항공권을 찾았어요."}
```

### 왜 스트리밍인가

이 제품의 핵심 가치 두 번째가 **"AI 작업을 눈으로 보여준다"** 다 (`spec.md` 1.2).

> 검색·생성·검증 모든 단계에서 에이전트의 추론 과정을 실시간으로 노출해 **"기다리는 시간"을 "신뢰가 쌓이는 시간"으로** 바꾼다.

즉, **추론 과정 자체가 기능**이다. 결과를 다 만든 뒤 한 번에 보내면 계약은 지켜지지만 제품이 망가진다.

### 지금 프론트는 어떻게 동작하나

프론트엔드는 이미 **목(mock) 스트리밍 계층**으로 완전히 동작한다. 스크립트가 가짜 이벤트를 만들어 같은 UX를 재현한다(`spec.md` 6.6). 당신이 만드는 서버는 **그 목을 대체**하는 것이고, 교체 지점은 환경 변수 하나다.

```
NEXT_PUBLIC_AGENT_MODE=mock   →   MockTransport (스크립트)
NEXT_PUBLIC_AGENT_MODE=live   →   SseTransport  →  당신의 서버
```

**화면 코드는 한 줄도 바뀌지 않는다.** 그래서 프론트를 기다릴 필요 없이 지금 바로 시작할 수 있다.

### 자유로운 것 / 지켜야 하는 것

| 완전히 자유 | 반드시 지킨다 |
|---|---|
| 언어·프레임워크 (Python/TS/Go…) | 이벤트 스트림의 모양 ([`contract.md`](./contract.md)) |
| LLM 선택·모델·프롬프트 | 필수 필드와 형식 |
| 오케스트레이션 구조 (LangGraph 등) | 종료 이벤트 보장 |
| 도구를 몇 개로 나눌지 | 한국어 카피 톤 |
| 데이터 소스 | 목표 소요 시간 |

---

## 문서 지도

| 문서 | 내용 | 언제 읽나 |
|---|---|---|
| **[`contract.md`](./contract.md)** | **계약서.** SSE 전송 계층, 이벤트 9종, 작업별 입출력, 필수 필드, 불변식, 에러 | **가장 먼저.** 구현 중 계속 참조 |
| [`behavior.md`](./behavior.md) | 행동 명세. 무엇을 근거로 판단하는가. 추론 노출 원칙, 한국어 카피 규칙, 작업별 필터·순위 기준, 검증 규칙 구현 메모, 품질 루브릭 | 계약을 이해한 다음 |
| [`integration.md`](./integration.md) | 연동 가이드. 로컬 환경, 환경 변수, 점진 전환, 계약 테스트, 관측성, 트러블슈팅 | 서버를 처음 띄울 때 · 문제가 생길 때 |
| [`collaboration.md`](./collaboration.md) | 협업 규칙. 역할 경계, 계약 변경 절차, DoD, 마일스톤, **결정 대기 목록** | 킥오프에서 함께 |
| [`schemas/`](./schemas/) | 기계 판독 계약. `agent-event.schema.json` · `task-io.schema.json` | 검증 코드를 붙일 때 |
| [`fixtures/inputs.json`](./fixtures/inputs.json) | 작업별 입력 픽스처 + 골든 케이스 G1~G5 | 테스트할 때 |
| [`fixtures/golden.flightSearch.jsonl`](./fixtures/golden.flightSearch.jsonl) | 계약을 만족하는 이벤트 스트림 정답 예시 | 형식을 눈으로 익힐 때 |
| [`tools/conformance.mjs`](./tools/conformance.mjs) | 계약 테스트 러너 (의존성 없음) | 매 커밋 |

### 상위 문서에서 볼 것

| 위치 | 내용 |
|---|---|
| [`../spec.md`](../spec.md) 1장 | 제품 개요·사용자 여정. **전체 맥락을 위해 반드시 읽는다** |
| [`../spec.md`](../spec.md) 5장 | 전체 데이터 모델. 필드 정의의 **원본** |
| [`../spec.md`](../spec.md) 6.6 | 목 스크립트. **이벤트 리듬의 가장 좋은 참고 자료** |
| [`../spec.md`](../spec.md) 6.10 | 완전히 채워진 `Place` 샘플. 골든 샘플로 그대로 쓴다 |
| [`../spec.md`](../spec.md) 9장 | 검증 규칙 V1~V10 판정 로직의 **원본** |
| [`../spec.md`](../spec.md) 7장 | 화면 명세. 내 출력이 어디에 어떻게 표시되는지 |

---

## 읽는 순서

**에이전트 개발 담당**

```
이 문서 → spec.md 1장 (제품 맥락)
        → contract.md 전체
        → behavior.md 1절 (공통 요구사항)
        → spec.md 6.6 (목 스크립트로 리듬 익히기)
        → integration.md 2절 (서버 띄우기)
        → 담당 작업의 behavior.md 절 + spec.md 9장(검증 담당이면)
```

**프론트엔드 담당**

```
contract.md 1·3·4절 (경계와 이벤트)
        → contract.md 6절 (내가 요구하는 필수 필드)
        → integration.md 1·3·4절 (프록시·환경변수·전환)
        → collaboration.md 7절 (내가 결정해야 하는 것)
```

**팀 리드 · 기획**

```
이 문서 5분 요약 → collaboration.md 6절(마일스톤) · 7절(결정 대기) · 9절(리스크)
```

---

## 지금 바로 시작하기

### 1. 형식을 눈으로 익힌다 (5분)

```bash
# 계약을 만족하는 스트림이 어떻게 생겼는지 본다
cat agent/fixtures/golden.flightSearch.jsonl | head -6

# 그게 정말 계약을 통과하는지 확인한다
node agent/tools/conformance.mjs --file agent/fixtures/golden.flightSearch.jsonl flightSearch
```

```
○ flightSearch
  통과 38 · 실패 0 · 경고 0
계약 통과 — 1개 작업, 경고 0건
```

### 2. 스텁 서버를 만든다 (M0 · 반나절)

**결과 품질은 0점이어도 좋다. 계약만 지킨다.** 목 데이터를 그대로 되돌려주면서 이벤트 순서만 맞춘다.

```bash
# 서버를 8000 포트에 띄운 뒤
node agent/tools/conformance.mjs http://localhost:8000
```

5개 작업이 전부 통과하면 M0 완료다. 이 시점에 프론트는 이미 `live` 모드로 붙여볼 수 있고, **전송 계층 문제(SSE 버퍼링·취소·타임아웃)를 품질 문제와 분리해서** 잡을 수 있다.

> M0를 건너뛰고 바로 실제 구현에 들어가면, 문제가 생겼을 때 그게 전송 문제인지 오케스트레이션 문제인지 알 수 없다. [`collaboration.md` §6.1](./collaboration.md#61-m0을-먼저-하는-이유)

### 3. `placeDiscovery`부터 실제로 만든다 (M1)

| 왜 먼저인가 | 이유 |
|---|---|
| 입력이 가장 단순 | `cityId` + `persona` + `dayCount`. 앞 단계 결과에 의존하지 않는다 |
| 뒤 단계의 입력을 만든다 | 여기 출력이 `itineraryGenerate`의 입력이다 |
| 우회 불가 | 항공·숙소는 설문에서 건너뛸 수 있지만 장소는 필수 경로다 |
| 임팩트가 가장 크다 | "AI가 나를 위해 골랐다"는 인상이 여기서 만들어진다 |

읽을 것: [`behavior.md` §4](./behavior.md#4-placediscovery) · [`contract.md` §5.3](./contract.md#53-placediscovery)

### 4. 매 커밋마다 확인한다

```bash
node agent/tools/conformance.mjs http://localhost:8000 placeDiscovery
```

---

## 가장 흔한 실수 5개

구현 전에 알아두면 시간을 아낀다. 전체 목록은 [`contract.md` §9](./contract.md#9-계약-위반-목록)와 [`integration.md` §9.2](./integration.md#92-자주-하는-설계-실수).

| # | 실수 | 결과 | 올바른 방식 |
|---|---|---|---|
| 1 | 종료 이벤트 없이 스트림 종료 (예외가 그냥 터짐) | **화면이 영원히 로딩** | 모든 경로를 `try/except`로 감싸 `done` 또는 `error`를 보장 |
| 2 | `thought`를 델타로 보냄 | 문장이 `인천인천(ICN)…`으로 뭉친다 | **누적 전체 텍스트**를 보낸다 |
| 3 | `X-Accel-Buffering: no` 누락 | 스트리밍이 사라지고 결과가 한 번에 나온다 | 응답 헤더에 추가 |
| 4 | 날짜·거리 계산을 LLM에게 맡김 | 검증 기능 전체의 신뢰가 무너진다 | 계산은 결정론적 코드로 |
| 5 | `ISODateTime`에 타임존(`Z`) 포함 | 모든 시각이 9시간 밀린다 | `2026-06-12T09:05` — 타임존 없이 현지 시각 |

---

## 시작 전 확인할 것

[`collaboration.md` §7 결정 대기 목록](./collaboration.md#7-결정-대기-목록)에 아직 정해지지 않은 항목이 있다. 그중 두 개는 **구현에 착수하기 전에** 정해야 한다.

| # | 항목 | 왜 먼저인가 |
|---|---|---|
| 4 | **목 데이터 소유권과 `Place.id` 안정성** | 나중에 발견하면 목 데이터 전체를 다시 만들어야 한다. [`collaboration.md` §9.1](./collaboration.md#91-가장-위험한-것) |
| 11 | 저장소 구조 (단일 vs 분리) | 계약 문서 동기화 방식이 여기서 갈린다 |

---

## 용어

`spec.md` 0.5의 용어 사전을 따른다. 에이전트 측에서 자주 쓰는 것만 추린다.

| 한국어 | 코드 식별자 | 의미 |
|---|---|---|
| 작업 | `AgentTaskId` | 5개 엔드포인트 각각 |
| 에이전트 이벤트 | `AgentEvent` | 스트림으로 내려가는 단위 메시지 |
| 페르소나 | `Persona` | 사용자의 여행 성향·조건 응답 묶음 |
| 후보 장소 | `candidatePlaces` | `placeDiscovery`가 발견한 장소들 |
| 선택 장소 | `selectedPlaces` | 사용자가 체크한 곳. `itineraryGenerate`의 입력 |
| 일정 | `Itinerary` | 날짜별로 배치된 최종 계획 |
| 일자 | `ItineraryDay` | 일정의 하루. `dayIndex` 0부터, 화면 표기는 `Day 1`부터 |
| 일정 항목 | `ItineraryItem` | 하루 안의 방문 블록 하나 |
| 이동 구간 | `TravelLeg` | 항목 사이의 이동 |
| 검증 항목 | `VerificationCheck` | 규칙 1건의 실행 결과 (V1~V10) |
| 이슈 | `VerificationIssue` | 주의·충돌로 판정된 건 |
| 자동 수정 | `AutoFixProposal` | 이슈를 해결하는 일정 변경 제안 |
| 불변식 | `I-*` | 계약이 요구하는 구조적 조건. `contract.md` §5 |

**표기 규칙** (계약 문서 전체 공통)

- ✅ **확정** — `spec.md`에 근거가 있다. 구현해도 안전하다
- 🔶 **제안** — 합의 전 잠정. [`collaboration.md` §7](./collaboration.md#7-결정-대기-목록)에서 추적
- ⛔ **금지** — 계약 위반. 프론트가 깨진다

---

## 파일 구조

```
agent/
├── README.md                        이 문서
├── contract.md                      계약서 (v1.0-draft)
├── behavior.md                      행동 명세
├── integration.md                   연동 가이드
├── collaboration.md                 협업 규칙
├── schemas/
│   ├── agent-event.schema.json      이벤트 스키마
│   └── task-io.schema.json          작업 입출력 · 도메인 타입 스키마
├── fixtures/
│   ├── inputs.json                  작업별 입력 + 골든 케이스 G1~G5
│   └── golden.flightSearch.jsonl    계약 통과 스트림 정답 예시
└── tools/
    └── conformance.mjs              계약 테스트 러너
```

---

**다음** → [`contract.md`](./contract.md)
