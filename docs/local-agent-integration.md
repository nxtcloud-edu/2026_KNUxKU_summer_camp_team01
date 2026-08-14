# 로컬 Supervisor 연동

프론트와 Next.js 백엔드는 `dev/backend`, Supervisor·Plan·Verification Agent는 `dev/plan-verification-test`를 별도 worktree로 실행한다. Agent 코드를 백엔드 브랜치에 병합하지 않는다.

## 1. Agent worktree 준비

저장소 상위 디렉터리에서 한 번만 실행한다.

```powershell
git fetch origin --prune
git worktree add --detach ..\summer_camp_team01_agents origin/dev/plan-verification-test
```

각 Python 프로젝트의 환경을 준비한다.

```powershell
cd ..\summer_camp_team01_agents\agent\supervisor\plan-agent
uv sync

cd ..\verification-agent
uv sync

cd ..
uv sync
```

## 2. Agent 실행

서로 다른 PowerShell 터미널에서 실행한다.

```powershell
# Plan Agent — terminal 1
cd ..\summer_camp_team01_agents\agent\supervisor\plan-agent
uv run uvicorn plan_agent.main:app --host 127.0.0.1 --port 8001
```

```powershell
# Verification Agent — terminal 2
cd ..\summer_camp_team01_agents\agent\supervisor\verification-agent
uv run uvicorn verification_agent.main:app --host 127.0.0.1 --port 8003
```

```powershell
# Supervisor — terminal 3
cd ..\summer_camp_team01_agents\agent\supervisor
uv run uvicorn supervisor.main:app --host 127.0.0.1 --port 8000
```

Supervisor 상태를 확인한다.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## 3. Next.js 백엔드 연결

`summer_camp_team01_backend/.env.local`을 만든다. 이 파일은 Git에 커밋하지 않는다.

```dotenv
AGENT_MODE=live
SUPERVISOR_AGENT_URL=http://127.0.0.1:8000
VERIFICATION_AGENT_URL=http://127.0.0.1:8003
AGENT_HARD_TIMEOUT_MS=45000
```

Next.js를 실행한다.

```powershell
cd ..\summer_camp_team01_backend
npm ci
npm run dev
```

브라우저는 `http://localhost:3000`을 사용한다. 프론트는 Supervisor 주소를 직접 호출하지 않고 `/api/agent/*`만 호출한다.

## 연결되는 작업

| 프론트 작업 | Next.js API | 로컬 Agent |
|---|---|---|
| 일정 생성 | `POST /api/agent/itineraryGenerate` | Supervisor `POST :8000/agent/plan` |
| 일정 재검증 | `POST /api/agent/itineraryVerify` | Verification `POST :8003/agent/itineraryVerify` |

Supervisor는 최초 일정 생성 시 Plan Agent와 Verification Agent를 호출하고, 설정에 따라 재계획까지 수행한다. Search Agent 실행 코드는 통합 브랜치에 아직 없으므로 항공·숙소·장소 선택 결과는 현재 프론트 상태에서 `SearchToPlanInput`으로 변환한다.

`AGENT_MODE=mock`으로 바꾸거나 변수를 생략하면 기존 내장 mock Agent를 사용한다. Gemini 및 Google Routes API 키가 없어도 결정론·좌표 추정 모드로 로컬 데모가 동작한다.
