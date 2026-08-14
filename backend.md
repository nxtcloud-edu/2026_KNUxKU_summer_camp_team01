# Supervisor Backend 사용 및 검증 가이드

## 바로 필요한 정보

| 구분 | 포트 번호 | 기본 URL | Endpoint |
|---|---:|---|---|
| Supervisor | `8000` | `http://127.0.0.1:8000` | `GET /health`, `POST /agent/plan` |
| Plan Agent | `8001` | `http://127.0.0.1:8001` | `POST /agent/itineraryGenerate`, `POST /agent/itineraryReplan` |
| Search Agent | `8002` | `http://127.0.0.1:8002` | 현재 Supervisor 내부에서 직접 호출하지 않음 |
| Verification Agent | `8003` | `http://127.0.0.1:8003` | `POST /agent/itineraryVerify` |

### 핵심 호출 URL

```text
Supervisor 상태 확인
GET http://127.0.0.1:8000/health

Search 결과로 최초 일정 생성 및 검증
POST http://127.0.0.1:8000/agent/plan

Plan Agent 일정 생성
POST http://127.0.0.1:8001/agent/itineraryGenerate

Plan Agent 피드백 기반 재계획
POST http://127.0.0.1:8001/agent/itineraryReplan

Verification Agent 일정 검증
POST http://127.0.0.1:8003/agent/itineraryVerify
```

> 현재 Supervisor의 입력은 canonical `SearchToPlanInput`입니다. Search Agent가 만든 결과 JSON을 `POST /agent/plan`에 전달하면 Supervisor가 Plan 생성과 Verification 검증을 조정합니다. Search Agent 자체를 Supervisor 내부에서 호출하는 구조는 아직 아닙니다.

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
| 상태 확인 | `GET` | `/health` | Supervisor 및 하위 Agent 연결 설정 확인 |
| 최초 일정 생성 | `POST` | `/agent/plan` | Search 결과를 받아 Plan 생성, Verification 검증, 필요 시 자동 재계획과 재검증까지 실행 |

> 현재 Supervisor에는 기존 일정을 전달해 재검증만 수행하는 전용 endpoint가 없습니다. 기존 일정만 재검증하려면 Verification Agent의 `POST /agent/itineraryVerify`를 직접 호출합니다.

### 관련 Agent Endpoint

| Agent | 기본 주소 | Method | Endpoint | 호출 주체 및 용도 |
|---|---|---|---|---|
| Plan Agent | `http://127.0.0.1:8001` | `POST` | `/agent/itineraryGenerate` | Supervisor가 최초 일정 생성 시 호출 |
| Plan Agent | `http://127.0.0.1:8001` | `POST` | `/agent/itineraryReplan` | Supervisor가 Verification 실패 feedback을 전달할 때 호출 |
| Verification Agent | `http://127.0.0.1:8003` | `POST` | `/agent/itineraryVerify` | Supervisor가 최초 일정 및 재계획 결과를 검증할 때 호출 |

### 현재 데이터 흐름

```text
Search Agent 또는 Search mock
  -> canonical SearchToPlanInput JSON
  -> Supervisor POST /agent/plan
  -> Plan POST /agent/itineraryGenerate
  -> Verification POST /agent/itineraryVerify
  -> possible=false이면 Supervisor가 feedback 생성
  -> Plan POST /agent/itineraryReplan
  -> Verification POST /agent/itineraryVerify
  -> Supervisor가 최종 SSE done 반환
```

Search mock fixture 예시:

```text
agent/fixtures/search-to-plan.mock-agent-output.json
```

---

## 2. 최초 일정 생성 예제

Supervisor의 `POST /agent/plan`에 Search 결과 JSON을 전달합니다. 응답은 단일 JSON이 아니라 SSE 스트림입니다.

### Windows PowerShell

```powershell
curl.exe -N -sS `
  -X POST "http://127.0.0.1:8000/agent/plan" `
  -H "Content-Type: application/json" `
  -H "Accept: text/event-stream" `
  --data-binary "@agent/fixtures/search-to-plan.mock-agent-output.json"
```

### SSE 응답 저장

```powershell
curl.exe -N -sS `
  -X POST "http://127.0.0.1:8000/agent/plan" `
  -H "Content-Type: application/json" `
  -H "Accept: text/event-stream" `
  --data-binary "@agent/fixtures/search-to-plan.mock-agent-output.json" `
  -o "supervisor.sse"
```

정상 완료 이벤트의 `payload`에는 일반적으로 다음 결과가 포함됩니다.

```json
{
  "plan": {},
  "verification": {},
  "acceptance": [],
  "warnings": []
}
```

---

## 3. Verification 실패 시 feedback 및 자동 재계획

Supervisor는 아래 조건을 모두 만족할 때 자동 재계획을 실행합니다.

1. Plan 결과가 존재합니다.
2. Verification 결과가 존재하고 `verification.possible`이 정확히 `false`입니다.
3. `replan_count`가 `SUPERVISOR_AUTO_REPLAN`보다 작습니다.
4. Supervisor 전체 제한시간이 5초보다 많이 남았습니다.

기본 `SUPERVISOR_AUTO_REPLAN=1`이므로 자동 루프는 한 요청에서 최대 1회입니다. 같은 제약으로 반복 호출해 시간과 LLM 비용을 낭비하지 않도록 재계획 결과가 여전히 불가능해도 두 번째 자동 재계획은 하지 않습니다.

### feedback 생성 방식

Supervisor는 Verification의 `feedback.dangers`와 `feedback.cautions`를 읽어 Plan Agent가 이해할 수 있는 자연어로 변환합니다. 검사 종류, 위험 수준, Day, 항목 ID, 수치와 확인사항을 가능한 한 그대로 유지합니다.

실제 E2E에서 생성된 feedback:

```text
아래 문제를 해결하도록 일정을 조정해 주세요. 시각은 다시 계산되므로 어느 장소를 어느 날로 옮길지, 어떤 장소를 뺄지만 정해 주세요.
- [위험/예산] : 예상 비용이 예산을 690600 KRW 초과합니다.
```

### 자동 처리 순서

```text
1. Plan /agent/itineraryGenerate
2. Verification /agent/itineraryVerify
3. verification.possible=false 판정
4. Supervisor가 구체적인 feedback 생성
5. Plan /agent/itineraryReplan에 기존 일정과 feedback 전달
6. Verification /agent/itineraryVerify로 재계획 결과 재검증
7. 자동 재계획 횟수 소진 후 최종 결과 반환
```

재계획 endpoint가 HTTP 200을 반환했다는 사실과 문제가 실제로 해결되었다는 사실은 다릅니다. Plan Agent는 재계획 결과가 계약을 위반하거나 유효한 배치 변경을 만들지 못하면 기존 일정을 안전하게 유지할 수 있습니다. 이 경우 Supervisor는 그 결과도 다시 Verification에 전달하고 최종 `possible:false`를 그대로 반환합니다.

---

## 4. feedback 루프 E2E 검증 결과

### 검증 목적

도쿄 5일 일정의 예산을 실제 추정액보다 현저히 낮은 `50,000 KRW`로 설정해 Verification 실패를 의도적으로 발생시켰습니다. 이 테스트의 성공 기준은 여행 가능 판정이 아니라 다음 제어 흐름의 실제 실행입니다.

- Verification이 예산 문제를 `possible:false`로 판정
- Supervisor가 예산 초과 수치를 포함한 feedback 생성
- Supervisor가 Plan의 `/agent/itineraryReplan` 호출
- Supervisor가 재계획 결과를 Verification의 `/agent/itineraryVerify`로 재호출
- 설정된 자동 재계획 1회 후 정상적인 SSE `done` 반환

### 실행 명령

세 서버를 실행한 뒤 프로젝트 루트에서 다음 명령을 실행했습니다.

```powershell
& ".\agent\supervisor\plan-agent\.venv\Scripts\python.exe" `
  "agent/supervisor/plan-agent/tools/e2e_full_loop.py"
```

### 실제 결과

| 검증 항목 | 결과 |
|---|---|
| Supervisor 응답 | HTTP `200` |
| SSE 이벤트 | 요청당 `18`개 |
| 종료 이벤트 | `done` 정상 수신 |
| 최종 일정 | `5일`, `19항목` |
| 최초 Verification | `possible=false` |
| 예산 검사 | `fail` |
| 예상 비용 | `740,600 KRW` |
| 입력 예산 | `50,000 KRW` |
| 예산 초과 | `690,600 KRW` |
| Supervisor feedback 생성 | 확인 |
| Plan 재계획 호출 | `POST /agent/itineraryReplan`, HTTP `200` |
| Verification 재호출 | `POST /agent/itineraryVerify`, HTTP `200` |
| 자동 재계획 횟수 | `1회` |
| Acceptance report | `3건`, 모두 `ok=true` |
| Warnings | `0건` |

핵심 Supervisor 로그:

```text
verification 산출물 수락 (5개 검사 통과)
재계획 요청 (1회): 아래 문제를 해결하도록 일정을 조정해 주세요.
- [위험/예산] : 예상 비용이 예산을 690600 KRW 초과합니다.
POST http://127.0.0.1:8001/agent/itineraryReplan "HTTP/1.1 200 OK"
POST http://127.0.0.1:8003/agent/itineraryVerify "HTTP/1.1 200 OK"
verification 산출물 수락 (5개 검사 통과)
자동 재계획 1회를 마쳤습니다. 사용자 요청 시 다시 계획합니다.
```

### 최종 `possible=false` 해석

이 결과는 feedback 루프 실패가 아닙니다. `50,000 KRW`로는 약 `740,600 KRW`가 필요한 2인 도쿄 5일 일정의 고정 비용과 선택 조건을 충족할 수 없도록 의도한 테스트입니다. Plan Agent는 재계획을 시도했지만 유효한 변경으로 예산 계약을 만족시키지 못해 기존 일정을 유지했고, Supervisor는 이를 다시 검증한 뒤 정직하게 `possible=false`를 반환했습니다.

즉, **feedback 생성·재계획 명령·재검증 제어 흐름은 정상 동작했으며, 비현실적인 예산 조건만 해결되지 않은 것**입니다.

---

## 5. 서버 실행 방법

Windows PowerShell에서 각 서버를 별도 터미널로 실행합니다. 아래 명령은 프로젝트 루트를 현재 경로로 가정합니다.

### Plan Agent 실행

```powershell
$env:ROUTES_ENABLED = "off"
$env:PLAN_AGENT_TIMEOUT_MS = "45000"
& ".\agent\supervisor\plan-agent\.venv\Scripts\python.exe" `
  -m uvicorn plan_agent.main:app --host 127.0.0.1 --port 8001
```

### Verification Agent 실행

```powershell
& ".\agent\supervisor\verification-agent\.venv\Scripts\python.exe" `
  -m uvicorn verification_agent.main:app --host 127.0.0.1 --port 8003
```

### Supervisor 실행

```powershell
$env:AGENT_HARD_TIMEOUT_MS = "120000"
$env:PLAN_AGENT_TIMEOUT_MS = "45000"
$env:VERIFICATION_AGENT_TIMEOUT_MS = "45000"
& ".\agent\supervisor\.venv\Scripts\python.exe" `
  -m uvicorn supervisor.main:app --host 127.0.0.1 --port 8000
```

`ROUTES_ENABLED=off`는 Google Routes API 과금을 피하고 좌표 기반 이동시간 추정을 사용하기 위한 E2E 설정입니다. 실제 Routes API를 검증하려면 키와 과금 정책을 확인한 뒤 별도로 활성화해야 합니다.

Gemini 응답 시간에 따라 기본 15~20초 timeout이 부족할 수 있습니다. 전체 feedback 루프 E2E에는 Supervisor `120000ms`, Plan/Verification 각각 `45000ms`를 권장합니다. 위 값은 실행 프로세스에만 적용되며 코드나 `.env`를 영구 변경하지 않습니다.

---

## 6. Health Check

Supervisor 서버가 정상 실행 중인지 확인합니다.

```powershell
curl.exe -sS "http://127.0.0.1:8000/health"
```

예상 응답 예시:

```json
{
  "status": "ok",
  "plan_url": "http://127.0.0.1:8001",
  "verification_url": "http://127.0.0.1:8003",
  "hard_timeout_ms": 120000
}
```

Health Check는 URL과 설정 확인용입니다. 하위 Agent의 실제 생성·검증 성공까지 보장하지 않으므로 전체 연결은 `POST /agent/plan` E2E로 확인해야 합니다.

---

## 7. SSE 응답 형식

Supervisor와 하위 Agent 응답은 `text/event-stream` 형식입니다. 각 이벤트는 `data: {...}` 줄로 전달됩니다.

```text
data: {"seq":0,"at":...,"type":"status","text":"일정 생성을 준비하고 있어요"}
data: {"seq":1,"at":...,"type":"progress","value":0.05}
data: {"seq":17,"at":...,"type":"done","payload":{...},"summary":"..."}
```

### 이벤트 타입

| type | 의미 |
|---|---|
| `status` | 현재 진행 단계 |
| `progress` | 진행률 |
| `done` | 정상 완료 및 최종 payload |
| `error` | 입력, 하위 Agent, timeout 등의 실패 |

### 자동 재계획이 발생한 실제 status 순서

```text
일정 생성을 준비하고 있어요
여행 조건을 확인하고 있어요
장소를 날짜별로 배치하고 있어요
배치 이유를 정리하고 있어요
일정 가능 여부를 확인하고 있어요.
피드백을 확인하고 있어요
일정을 다시 배치하고 있어요
일정 가능 여부를 확인하고 있어요.
done: 5일 19개 일정을 만들었어요. 일부 조건을 다시 살펴봐야 해요.
```

실패 이벤트 예시:

```text
data: {"seq":0,"at":...,"type":"error","code":"invalid_input","message":"입력 형식이 계약과 맞지 않아요.","retryable":false}
```

---

## 8. 참고 환경변수

PowerShell 설정 예시:

```powershell
$env:SUPERVISOR_PORT = "8000"

$env:PLAN_AGENT_PORT = "8001"
$env:SEARCH_AGENT_PORT = "8002"
$env:VERIFICATION_AGENT_PORT = "8003"

$env:PLAN_AGENT_URL = "http://127.0.0.1:8001"
$env:VERIFICATION_AGENT_URL = "http://127.0.0.1:8003"

$env:AGENT_HARD_TIMEOUT_MS = "120000"
$env:PLAN_AGENT_TIMEOUT_MS = "45000"
$env:VERIFICATION_AGENT_TIMEOUT_MS = "45000"

$env:SUPERVISOR_AUTO_REPLAN = "1"
$env:SUPERVISOR_MAX_REISSUE = "1"
$env:ROUTES_ENABLED = "off"
```

| 환경변수 | 역할 |
|---|---|
| `AGENT_HARD_TIMEOUT_MS` | Supervisor 요청 전체 제한시간 |
| `PLAN_AGENT_TIMEOUT_MS` | Plan Agent 단일 호출 제한시간 |
| `VERIFICATION_AGENT_TIMEOUT_MS` | Verification Agent 단일 호출 제한시간 |
| `SUPERVISOR_AUTO_REPLAN` | Verification 실패 후 자동 재계획 최대 횟수 |
| `SUPERVISOR_MAX_REISSUE` | 하위 Agent 산출물 acceptance 실패 시 재하달 최대 횟수 |
| `ROUTES_ENABLED` | Plan Agent의 Routes API 사용 여부 |

---

## 9. 현재 제한사항

- Supervisor 입력은 현재 canonical `SearchToPlanInput`입니다.
- Search Agent는 Supervisor 그래프 내부에서 직접 호출되지 않습니다. Search Agent 또는 mock이 만든 JSON을 호출자가 Supervisor에 전달해야 합니다.
- Supervisor에는 기존 일정 재검증 전용 endpoint가 없습니다. 재검증만 필요하면 Verification Agent를 직접 호출합니다.
- 자동 재계획 기본값은 요청당 1회입니다. 이후 추가 변경은 새 사용자 요청으로 처리해야 합니다.
- 자동 재계획 호출 성공이 모든 제약 해결을 의미하지는 않습니다. 불가능한 예산이나 상충 조건은 최종 `possible=false`로 남을 수 있습니다.
- `ROUTES_ENABLED=off` E2E는 실제 교통 API가 아니라 좌표 기반 추정치를 사용합니다.

---

## 10. 한 줄 요약

- Search 결과 JSON은 Supervisor의 `POST /agent/plan`에 전달합니다.
- Supervisor는 Plan 생성과 Verification 검증을 수행하고, 실패 시 구체적 feedback으로 Plan 재계획을 최대 1회 명령한 뒤 반드시 재검증합니다.
- 실제 5만원 도쿄 E2E에서 `/agent/itineraryReplan`과 두 번째 `/agent/itineraryVerify` 호출을 모두 HTTP 200으로 확인했습니다.
- 최종 `possible=false`는 feedback 루프 오류가 아니라 의도적으로 불가능하게 설정한 예산 때문입니다.
