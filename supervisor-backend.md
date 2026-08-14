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
| 최초 일정 생성 | `POST` | `/agent/plan` | Search 결과를 받아 일정 생성 + 검증까지 실행 |

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

SUPERVISOR_AUTO_REPLAN=1
SUPERVISOR_MAX_REISSUE=1
```

---

## 8. 한 줄 요약

- 최초 일정 생성은 Supervisor의 `POST /agent/plan` 호출
- 기존 일정 재검증은 Verification Agent의 `POST /agent/itineraryVerify` 호출
- 응답은 JSON 한 번이 아니라 SSE 이벤트 스트림
