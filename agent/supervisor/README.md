# Voyagent Supervisor

세 하위 에이전트를 총괄하는 오케스트레이션 계층이다. 계약 정본은 한 단계 위인
[`../README.md`](../README.md)와 [`../schemas/`](../schemas/)이며, 이 문서는
**supervisor가 그 계약을 어떻게 이어 붙이는가**만 다룬다.

## 디렉터리 구조

```text
agent/supervisor/
├── README.md              이 문서
├── search-agent/          SearchRequest -> SearchToPlanInput
├── plan-agent/            SearchToPlanInput -> PlanToVerificationInput
└── verification-agent/    PlanToVerificationInput -> VerificationResult
```

`search-agent`, `plan-agent`, `verification-agent`는 같은 계층의 독립 서비스이며,
supervisor는 각 하위 에이전트를 HTTP SSE 호출로 실행합니다.

## 데이터 흐름

```text
프론트엔드 웹사이트                Search Agent
(사용자 선호·조건 수집)            (항공편·장소 정보 수집)
        │                                │
        │ trip_info                      │ selected
        │  (persona 포함)                 │  (flight / stay / places)
        └────────────┬───────────────────┘
        SearchRequest ↓
                 Search Agent
                     ↓ SearchToPlanInput
                 Plan Agent
                     ↓ PlanToVerificationInput
              Verification Agent
                     ↓ { possible, checks, feedback }
```

`SearchToPlanInput`은 **두 출처가 합쳐진 것**이다. 한 에이전트의 산출물이 아니다.

| 블록 | 만드는 곳 | 내용 |
|---|---|---|
| `trip_info` | 프론트엔드 웹사이트 | 목적지·날짜·인원·예산·이동수단·하루 시간대 + `persona` |
| `selected` | Search Agent | 항공편·장소 후보. 현재 strict 로컬 모드에서는 `stay=null` |

사용자에게 선호를 묻는 것은 **프론트엔드의 일**이다. Search Agent는 그 조건을
받아 항공편·여행장소 **정보만** 수집한다.

## 현재 strict 로컬 모드

`.env`의 기본 운영값은 다음 기준을 따른다.

```text
STRICT_FACTS=true
ROUTES_ALLOW_ESTIMATES=false
```

추가 provider 없이는 사실 기반으로 확인할 수 없는 기능은 현재 파이프라인에서
제외되어 있다.

| 제외 기능 | 현재 처리 |
|---|---|
| 숙소 실제 가격·체크인·체크아웃 | Search 결과의 `selected.stay`를 `null`로 둔다 |
| 장소 입장료 | schema 호환용 `price: 0`만 남기고 예산 검증에서 사용하지 않는다 |
| 사실 기반 체류시간 | 일정 슬롯 계산용 기본값만 사용한다 |
| 사실 기반 활동강도 | walking level 검증에서 사용하지 않는다 |
| Google Places가 영업시간을 주지 않는 장소 | `opening_hours: "정보 없음"`으로 보존하고 영업시간 검증에서 제외한다 |

이 값들은 UI에서 사실 데이터처럼 보여주면 안 된다. 필요하면 숙박/티켓/activity
provider를 추가한 뒤 다시 검증 기능으로 켠다.

| 경계 | 정본 스키마 | 예제 |
|---|---|---|
| Search → Plan | [`../schemas/search-to-plan.schema.json`](../schemas/search-to-plan.schema.json) | [`../fixtures/search-to-plan.example.json`](../fixtures/search-to-plan.example.json) |
| Plan → Verification | [`../schemas/plan-to-verification.schema.json`](../schemas/plan-to-verification.schema.json) | [`../fixtures/plan-to-verification.example.json`](../fixtures/plan-to-verification.example.json) |
| SSE 전송 이벤트 | [`../schemas/agent-event.schema.json`](../schemas/agent-event.schema.json) | 런타임 응답으로 검증 |

`trip_info`는 두 경계에서 **완전히 동일해야 한다.** Plan Agent는 받은
`trip_info`를 한 글자도 바꾸지 않고 그대로 넘긴다
(`../tools/conformance.mjs`가 deepEqual로 검사한다).

## 하위 에이전트 엔드포인트

각 에이전트는 자기 HTTP 엔드포인트를 가진 독립 서비스이며, 모두 SSE로 응답한다.

| 에이전트 | 엔드포인트 | 입력 | 출력 payload |
|---|---|---|---|
| search | `POST /agent/search` | `SearchRequest` | `SearchToPlanInput` |
| plan | `POST /agent/itineraryGenerate` | `SearchToPlanInput` | `PlanToVerificationInput` |
| verification | `POST /agent/itineraryVerify` | `PlanToVerificationInput` | `{ possible, checks, feedback }` |

Supervisor의 `POST /agent/plan`은 두 입력을 모두 받을 수 있다.

- `SearchRequest`: Search Agent를 먼저 호출한 뒤 Plan Agent로 넘긴다.
- `SearchToPlanInput`: 이미 검색 결과가 선택된 입력이므로 Plan Agent부터 호출한다.

이벤트는 [`../schemas/agent-event.schema.json`](../schemas/agent-event.schema.json)의
4종(`status` · `progress` · `done` · `error`)만 사용한다. 모든 스트림은
`done` 또는 `error` **정확히 하나**로 끝난다.

## 계약 검사

```powershell
node agent/tools/conformance.mjs
```

## 계약을 어기지 않기 위한 공통 규칙

| # | 규칙 | 이유 |
|---|---|---|
| 1 | 조용한 실패 금지 | 제약을 못 지키면 버리지 말고 위반으로 보고한다 |
| 2 | 창작 금지 | 입력에 없는 장소·가격·시각을 만들지 않는다 |
| 3 | 계산은 결정론 코드로 | 시각·거리·요금 산술을 LLM에 맡기지 않는다 |
| 4 | 종료 이벤트 보장 | 예외가 나도 `error`를 보내고 정상 종료한다 |
| 5 | 계약 외 필드 금지 | 두 스키마 모두 `additionalProperties: false`다 |
