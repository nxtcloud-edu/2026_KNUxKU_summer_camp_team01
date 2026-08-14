# Supervisor Backend 사용 가이드

## 바로 필요한 정보

| 구분 | 포트 번호 | 기본 URL | Endpoint |
|---|---:|---|---|
| Supervisor | `8000` | `http://127.0.0.1:8000` | `GET /health`, `POST /agent/plan` |
| Search Agent | `8002` | `http://127.0.0.1:8002` | `GET /health`, `POST /agent/search` |
| Plan Agent | `8001` | `http://127.0.0.1:8001` | `POST /agent/itineraryGenerate`, `POST /agent/itineraryReplan` |
| Verification Agent | `8003` | `http://127.0.0.1:8003` | `POST /agent/itineraryVerify` |

### 핵심 호출 URL

```text
Supervisor 상태 확인
GET http://127.0.0.1:8000/health

최초 일정 생성
POST http://127.0.0.1:8000/agent/plan

Search Agent 단독 호출
POST http://127.0.0.1:8002/agent/search

기존 일정 재검증
POST http://127.0.0.1:8003/agent/itineraryVerify
```

> 최초 일정 생성은 Supervisor로 호출합니다.
> 입력에 `selected`가 없으면 Supervisor가 Search Agent를 먼저 호출합니다.
> 기존 일정 재검증은 Supervisor가 아니라 Verification Agent로 직접 호출합니다.

### 현재 로컬 hybrid demo 모드 기준

현재 `.env`는 실제 API 결과와 demo 보강값을 함께 사용합니다.

```bash
STRICT_FACTS=false
ROUTES_ALLOW_ESTIMATES=true
```

실제 API가 직접 주는 값과 demo로 보강하는 값은 아래처럼 나뉩니다.

| 항목 | 현재 처리 |
|---|---|
| 항공편 | SerpApi 실제 검색 결과 |
| 장소 이름·주소·좌표·평점·Google 제공 영업시간 | Google Places 실제 검색 결과 |
| 숙소 이름·주소·좌표·평점 | Google Places 실제 검색 결과 |
| 숙소 가격·체크인·체크아웃 | `[DEMO DATA]` 보강값 |
| 장소 가격·체류시간·활동강도 | `[DEMO DATA]` 보강값 |
| 이동시간 | Google Routes 실제 경로값 우선. 경로 없음/429 등으로 실패하면 좌표 기반 `[DEMO DATA]` 추정 |

> `[DEMO DATA]`는 note와 verification evidence에 표시됩니다.
> 완전 사실 기반으로 비어 있는 값은 만들지 않는 모드는 `provider_mode: "live"`와
> `STRICT_FACTS=true`를 사용합니다.

---

## 1. Supervisor 실행 포트 / Endpoint

### Supervisor 포트 번호

```text
8000
```

### Supervisor 기본 URL

```text
http://127.0.0.1:8000
```

### Supervisor Endpoint 목록

| 기능 | Method | Endpoint | 설명 |
|---|---|---|---|
| 상태 확인 | `GET` | `/health` | Supervisor 서버가 떠 있는지 확인 |
| 최초 일정 생성 | `POST` | `/agent/plan` | Search부터 Plan, Verification까지 실행 |

> 현재 Supervisor에는 "기존 일정 재검증" 전용 endpoint가 없습니다.  
> 기존 일정 재검증은 Verification Agent를 직접 호출합니다.

### 관련 Agent Endpoint

| Agent | 기본 주소 | Method | Endpoint | 설명 |
|---|---|---|---|---|
| Search Agent | `http://127.0.0.1:8002` | `POST` | `/agent/search` | 검색 요청을 Plan Agent 입력으로 변환 |
| Plan Agent | `http://127.0.0.1:8001` | `POST` | `/agent/itineraryGenerate` | 일정 생성 |
| Plan Agent | `http://127.0.0.1:8001` | `POST` | `/agent/itineraryReplan` | 검증 피드백 기반 재계획 |
| Verification Agent | `http://127.0.0.1:8003` | `POST` | `/agent/itineraryVerify` | 기존 일정 재검증 |

---

## 2. 최초 일정 생성 curl 예제

Supervisor의 `/agent/plan`을 호출합니다.

Search Agent까지 포함한 전체 루프 입력 파일:

```text
data/sample/search-request.input.json
```

실행 명령:

```bash
curl -N -sS \
  -X POST http://127.0.0.1:8000/agent/plan \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  --data-binary @data/sample/search-request.input.json
```

이미 Search Agent 결과가 준비된 경우 입력 파일:

```text
data/sample/search-to-plan.input.json
```

실행 명령:

```bash
curl -N -sS \
  -X POST http://127.0.0.1:8000/agent/plan \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  --data-binary @data/sample/search-to-plan.input.json
```

### 최초 생성 결과 저장하기

전체 SSE 응답을 파일로 저장합니다.

```bash
curl -N -sS \
  -X POST http://127.0.0.1:8000/agent/plan \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  --data-binary @data/sample/search-request.input.json \
  | tee /tmp/supervisor.sse
```

응답에서 `done.payload.plan`만 추출하면 기존 일정 재검증 입력으로 사용할 수 있습니다.

```bash
sed -n 's/^data: //p' /tmp/supervisor.sse \
  | jq -c 'select(.type=="done") | .payload.plan' \
  > /tmp/plan-to-verification.json
```

### 전체 동작 워크플로

Supervisor는 하위 agent를 HTTP SSE 호출로 실행합니다. 코드상으로는 하위 agent를
직접 import하지 않고, 아래 endpoint를 순서대로 호출합니다.

```text
Frontend
  │
  │ POST /agent/plan
  │ SearchRequest
  │   - trip_info
  │   - persona
  │   - provider_mode
  │
  ▼
Supervisor :8000
  │
  ├─ POST Search Agent :8002 /agent/search
  │    input : SearchRequest
  │    output: SearchToPlanInput
  │            { trip_info, selected: { flight, stay, places } }
  │
  ├─ POST Plan Agent :8001 /agent/itineraryGenerate
  │    input : SearchToPlanInput
  │    output: PlanToVerificationInput
  │            { trip_info, plan: { days } }
  │
  ├─ POST Verification Agent :8003 /agent/itineraryVerify
  │    input : PlanToVerificationInput
  │    output: VerificationResult
  │            { possible, checks, feedback }
  │
  └─ possible=false이면
       POST Plan Agent :8001 /agent/itineraryReplan
       → Verification Agent로 다시 검증
```

`trip_info`와 `persona`는 Frontend 입력이 원본입니다. Search, Plan,
Verification은 이 값을 바꾸지 않고 같은 조건으로 사용합니다.

현재 hybrid demo 로컬 성공 예시의 최종 payload 특징:

```text
selected.stay = Google Places 숙소 + [DEMO DATA] 가격/체크인 보강
plan.days = 날짜별 장소, 식당, 놀거리, 숙소 체크인/복귀 일정
verification.possible = true
checks.budget = pass, estimated_total = demo 보강 가격 합산
checks.walking_level = pass
```

Plan Agent는 최소 한 번 이상 `17:30` 이후 저녁 식사 뒤 활동 일정을 만들도록
배치합니다. 재계획 결과가 이 조건을 잃으면 Supervisor 수락 검사에서 통과시키지
않습니다.

`persona.max_walking_level`도 자동 선택과 배치에 반영합니다. 예를 들어 최대
걷기 수준이 `중간`이면 필수 방문지가 아닌 `높음` 활동강도 장소는 선택·배치에서
제외합니다.

장소 개수는 프론트 입력의 `place_count`로 조절합니다. hybrid demo 모드에서도
`place_count`를 여행 일수로 줄이지 않습니다. Google Places에서 검증 가능한
후보가 충분하면 Plan Agent가 하루에 여러 장소를 배치할 수 있습니다.

Search Agent는 `persona.must_visit` 주변의 맛집·카페 후보도 함께 조회합니다.
예를 들어 `must_visit: ["센소지"]`이면 센소지 자체뿐 아니라 센소지 주변 식사
후보를 Google Places에서 받아 Plan Agent로 넘길 수 있습니다.

대중교통 Routes API가 특정 구간의 `TRANSIT` 경로를 반환하지 않는 경우,
Plan Agent는 Google Routes의 `WALK` 값을 한 번 더 확인합니다. 그래도 경로가
없거나 API quota/429가 발생하면 `ROUTES_ALLOW_ESTIMATES=true` 기준으로 좌표 기반
`[DEMO DATA]` 이동시간을 사용합니다.

---

## 3. 기존 일정 재검증 curl 예제

기존 일정 재검증은 Verification Agent의 `/agent/itineraryVerify`를 직접 호출합니다.

입력 파일:

```text
/tmp/plan-to-verification.json
```

실행 명령:

```bash
curl -N -sS \
  -X POST http://127.0.0.1:8003/agent/itineraryVerify \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  --data-binary @/tmp/plan-to-verification.json
```

샘플 파일로 바로 테스트하려면 아래 명령을 사용합니다.

```bash
curl -N -sS \
  -X POST http://127.0.0.1:8003/agent/itineraryVerify \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  --data-binary @data/sample/plan-to-verification.output.json
```

---

## 4. 서버 실행 방법

각 서버는 별도 터미널에서 실행합니다.

### Search Agent 실행

```bash
cd agent/supervisor/search-agent
PYTHONPATH=src python -m uvicorn voyagent_search.main:app --host 127.0.0.1 --port 8002
```

### Plan Agent 실행

```bash
cd agent/supervisor/plan-agent
PYTHONPATH=src python -m uvicorn plan_agent.main:app --host 127.0.0.1 --port 8001
```

### Verification Agent 실행

```bash
cd agent/supervisor/verification-agent
PYTHONPATH=src python -m uvicorn verification_agent.main:app --host 127.0.0.1 --port 8003
```

### Supervisor 실행

```bash
cd agent/supervisor
PYTHONPATH=src python -m uvicorn supervisor.main:app --host 127.0.0.1 --port 8000
```

---

## 5. Health Check

Supervisor 서버가 정상 실행 중인지 확인합니다.

```bash
curl -s http://127.0.0.1:8000/health | jq
```

예상 응답:

```json
{
  "status": "ok",
  "search_url": "http://127.0.0.1:8002",
  "plan_url": "http://127.0.0.1:8001",
  "verification_url": "http://127.0.0.1:8003",
  "hard_timeout_ms": 180000
}
```

---

## 6. 응답 형식

모든 Agent 응답은 `text/event-stream` 형식입니다.

즉, 일반 JSON 응답이 아니라 아래처럼 `data: {...}` 형태의 이벤트가 여러 번 옵니다.

```text
data: {"seq":0,"at":...,"type":"status","text":"일정 생성을 준비하고 있어요"}
data: {"seq":1,"at":...,"type":"progress","value":0.05}
data: {"seq":2,"at":...,"type":"done","payload":{...},"summary":"..."}
```

### 이벤트 타입

| type | 의미 |
|---|---|
| `status` | 현재 진행 상태 메시지 |
| `progress` | 진행률 |
| `done` | 정상 완료 |
| `error` | 실패 |

실패 시 예시:

```text
data: {"seq":0,"at":...,"type":"error","code":"invalid_input","message":"입력 형식이 계약과 맞지 않아요.","retryable":false}
```

---

## 7. 참고 환경변수

기본값을 바꾸고 싶을 때 아래 환경변수를 사용할 수 있습니다.

```bash
SUPERVISOR_PORT=8000

PLAN_AGENT_PORT=8001
SEARCH_AGENT_PORT=8002
VERIFICATION_AGENT_PORT=8003

PLAN_AGENT_URL=http://127.0.0.1:8001
SEARCH_AGENT_URL=http://127.0.0.1:8002
VERIFICATION_AGENT_URL=http://127.0.0.1:8003

AGENT_HARD_TIMEOUT_MS=180000
PLAN_AGENT_TIMEOUT_MS=60000
SEARCH_AGENT_TIMEOUT_MS=120000
VERIFICATION_AGENT_TIMEOUT_MS=45000

STRICT_FACTS=false
ROUTES_ALLOW_ESTIMATES=false

SUPERVISOR_AUTO_REPLAN=1
SUPERVISOR_MAX_REISSUE=1
```

---

## 8. 한 줄 요약

- 최초 일정 생성은 Supervisor의 `POST /agent/plan` 호출
- 기존 일정 재검증은 Verification Agent의 `POST /agent/itineraryVerify` 호출
- 응답은 JSON 한 번이 아니라 SSE 이벤트 스트림
- 현재 strict 로컬 모드는 추가 API가 필요한 숙소·입장료·활동강도 기능을 제외
