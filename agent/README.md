# Voyagent Agent Contracts

`agent/`의 메인 계약은 에이전트 사이의 두 handoff입니다.

```text
Search Agent
  └─ SearchToPlanInput
       ↓
Plan Agent
  └─ PlanToVerificationInput
       ↓
Verification Agent
  └─ { possible, checks }
```

모든 에이전트의 오케스트레이션은 LangGraph를 사용합니다.

## Source of truth

| 경계 | Canonical schema | Example fixture |
|---|---|---|
| Search → Plan | [`schemas/search-to-plan.schema.json`](./schemas/search-to-plan.schema.json) | [`fixtures/search-to-plan.example.json`](./fixtures/search-to-plan.example.json) |
| Plan → Verification | [`schemas/plan-to-verification.schema.json`](./schemas/plan-to-verification.schema.json) | [`fixtures/plan-to-verification.example.json`](./fixtures/plan-to-verification.example.json) |
| SSE 전송 이벤트 | [`schemas/agent-event.schema.json`](./schemas/agent-event.schema.json) | 런타임 응답으로 검증 |

`spec.md`는 제품/UI 설계 참고 문서이며 에이전트 handoff의 기계 판독 계약은 위 두 schema가 우선합니다.

## 1. Search → Plan

Search Agent는 검색 후보 전체가 아니라 사용자가 선택한 결과를 전달합니다.

```json
{
  "schema_version": "1.0",
  "trip_info": {},
  "selected": {
    "flight": null,
    "stay": null,
    "places": []
  }
}
```

- `trip_info`: 여행 기간, 인원, 예산, 이동 방식, persona
- `selected.flight`: 선택 항공편 또는 `null`
- `selected.stay`: 선택 숙소 또는 `null`
- `selected.places`: Plan Agent가 배치할 장소

## 2. Plan → Verification

Plan Agent는 같은 `trip_info`와 완성된 일정을 전달합니다.

```json
{
  "schema_version": "1.0",
  "trip_info": {},
  "plan": {
    "days": []
  }
}
```

- `day`는 1부터 연속
- item `id`는 plan 전체에서 고유
- 하루 첫 item의 `travel_from_prev`는 `null`
- 이후 item에는 이전 item에서의 이동 정보가 필요
- `start_time`, `end_time`, `expected_duration_min`은 서로 일치해야 함
- 마지막 여행일 전에는 하루 마지막 item이 `숙소`여야 함

## 공통 값 규칙

- 날짜: `YYYY-MM-DD`
- 시각: `HH:mm`
- 통화: ISO 4217 대문자 3자리
- 카테고리: `관광지`, `식사`, `카페`, `쇼핑`, `휴식`, `숙소`
- 예산 포함 항목도 동일한 카테고리 값 사용
- 페이스: `여유`, `보통`, `빡빡`
- 걷기/활동 강도: `낮음`, `중`, `중간`, `높음`
- 스키마에 없는 필드는 허용하지 않음

두 schema의 `TripInfo`와 `Persona` 정의는 항상 동일하게 유지합니다. 버전이 바뀌면 schema와 fixture를 같은 커밋에서 함께 수정합니다.

## 계약 검사

Node.js 18 이상에서 외부 패키지 없이 실행됩니다.

```powershell
node agent/tools/conformance.mjs
```

검사 항목:

- schema에 맞는 fixture 구조
- Search→Plan과 Plan→Verification의 공통 `trip_info` 일치
- 실제 달력 날짜와 여행 일수
- day 번호와 날짜 연속성
- item ID 중복
- 이동시간 및 체류시간 정합성
- Search 선택 결과가 Plan에서 임의로 바뀌지 않았는지

## Verification Agent

구현 위치:

```text
agent/verification-agent/
```

현재 API:

```http
POST /agent/itineraryVerify
Content-Type: application/json
Accept: text/event-stream
```

입력은 `plan-to-verification.schema.json`과 동일합니다. 출력은 다음 구조입니다.

```json
{
  "possible": true,
  "checks": {
    "physical_feasibility": {},
    "budget": {},
    "operating_hours": {},
    "daily_schedule": {},
    "must_visit": {},
    "avoid": {},
    "pace": {},
    "walking_level": {}
  }
}
```

결정론 규칙은 물리적 시간, 예산, 영업시간, 일정 구조, 필수 방문을 처리합니다. Gemini는 회피 조건, 페이스, 걷기/활동 강도를 처리하며 `GEMINI_API_KEY`가 없으면 해당 체크만 `skipped`가 됩니다.

## 파일 구조

```text
agent/
├── README.md
├── schemas/
│   ├── agent-event.schema.json
│   ├── search-to-plan.schema.json
│   └── plan-to-verification.schema.json
├── fixtures/
│   ├── search-to-plan.example.json
│   └── plan-to-verification.example.json
├── tools/
│   └── conformance.mjs
└── verification-agent/
    ├── pyproject.toml
    └── src/verification_agent/
```
