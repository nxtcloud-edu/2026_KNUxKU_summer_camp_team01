# 버그 및 이슈 기록

> 작성 시점: `dev/plan-verification-test` 브랜치. Plan Agent(8001) · Verification
> Agent(8003) · Supervisor(8000)를 실제로 기동해 더미데이터로 전체 루프를
> 검증하는 과정에서 발견한 문제들이다. **코드는 아직 고치지 않았다.** 재현
> 방법과 원인 분석까지만 정리한다.

## 검증 방법

```powershell
# 세 서버를 각각 기동
cd agent/supervisor/plan-agent; $env:PYTHONPATH="src"; $env:ROUTES_ENABLED="off"; python -m uvicorn plan_agent.main:app --port 8001
cd agent/supervisor/verification-agent; $env:PYTHONPATH="src"; python -m uvicorn verification_agent.main:app --port 8003
cd agent/supervisor; $env:PYTHONPATH="src"; python -m uvicorn supervisor.main:app --port 8000

# 정상 입력 + 재계획 트리거 확인
python agent/supervisor/plan-agent/tools/e2e_full_loop.py

# 일부러 잘못된 더미데이터 4종
python agent/supervisor/plan-agent/tools/e2e_bad_input.py
```

---

## 1. [심각] 이동시간 추정에 상한이 없어 비현실적인 값이 그대로 계약에 실림

**위치**: `agent/supervisor/plan-agent/src/plan_agent/geo.py::estimate_minutes`

**재현**: `e2e_bad_input.py`의 `3_이동불가_거리` 시나리오 — 장소 절반을 뉴욕
좌표(40.7128, -74.0060)로 바꿔 도쿄-뉴욕 거리(약 14,105km)를 만들었다.

**실제 로그**:
```
Day 3 '도쿄 타워' 이동시간을 좌표 기반으로 추정했습니다 (42325분, 14105.24km)
```

42,325분은 293.9일이다. `estimate_minutes()`가 직선거리 × 우회계수 ÷ 속도로
계산만 하고, 결과값에 상한을 두지 않는다.

```python
# geo.py 현재 코드
def estimate_minutes(distance_km: float, mode_key: str) -> int:
    speed_kmh, detour, fixed_wait = _MODE_PROFILE.get(mode_key, _MODE_PROFILE[DEFAULT_MODE])
    if distance_km <= 0:
        return fixed_wait
    road_km = distance_km * detour
    travel_minutes = (road_km / speed_kmh) * 60
    return int(round(travel_minutes)) + fixed_wait   # <- 상한 없음
```

**왜 문제인가**: 이 값이 그대로 `TravelFromPrevious.estimated_min`에 실려
`PlanToVerificationInput`으로 나간다. `plan_agent/models.py`의 계약 검증은
`estimated_min: int = Field(ge=0)`만 확인하므로 상한이 없어 통과한다. Search
Agent가 좌표 오류를 주거나(버그) 악의적인 입력을 주면, 검증 에이전트로 명백히
비현실적인 값이 그대로 넘어갈 수 있다.

**이번 테스트에서 실제로 영향이 드러나지는 않았다** — 같은 실행에서
`MUST_VISIT_MISSING`(아래 2번)이 먼저 걸려 산출물 자체가 반송됐기 때문이다.
하지만 그 문제가 없었다면 이 값이 그대로 나갔을 것이다.

**제안 방향(적용 안 함)**: 도시 내 이동이라는 전제에 맞는 상한(예: 300분)을
두고, 넘으면 로그 경고 + 캡핑하거나 `Violation`으로 명시적으로 보고한다. 조용히
캡핑만 하면 "이 구간은 원래 계산이 이상했다"는 사실이 사라지므로, 캡핑보다는
`contracts.py`에 "이동시간이 비현실적으로 크다" 같은 자기 검증 규칙을 추가하는
쪽이 이 프로젝트의 원칙(조용한 실패 금지)에 더 맞다.

---

## 2. [확인 필요] 재계획이 `MUST_VISIT_MISSING`을 반복해서 해결하지 못함

**위치**: `agent/supervisor/plan-agent/src/plan_agent/replan.py`,
`agent/supervisor/plan-agent/src/plan_agent/allocate.py`

**재현**: `e2e_bad_input.py`의 `2_필수방문지_휴무`, `3_이동불가_거리` 두
시나리오 모두 **의도한 위반이 아니라** `MUST_VISIT_MISSING`으로 실패했다.

**실제 로그** (시나리오 2, 필수 방문지 '센소지'를 연중 휴무로 만들었을 때):
```
자기 검증에서 1건이 걸렸습니다: MUST_VISIT_MISSING
문장을 붙인 뒤 위반이 생겼습니다. 문장을 버리고 원본을 유지합니다: ['MUST_VISIT_MISSING']
일정 생성 완료: 5일 18항목, ...
```
그 뒤 supervisor의 acceptance 검사(`check_plan_output`)가 이걸 잡아 최종적으로
`agent_failed: plan 산출물 계약 위반 1건: 필수 방문지 '센소지'가 일정에 없습니다`로
종료됐다.

**의도와 다른 지점**: 이 시나리오는 `CLOSED_DAY`(영업일 위반)를 검증 에이전트
쪽에서 잡는지 보려고 만들었는데, 실제로는 Plan Agent의 `allocate.py` 단계에서
"연중 휴무 장소는 배치 후보에서 제외"하는 로직이 먼저 작동해 그 장소 자체가
`unassigned` 처리된 것으로 보인다(로그상 `contracts.check_input_usable`이
사전에 걸렀어야 하는 자리인데, 실제로는 배치까지 진행됐다가 결과적으로
`must_visit`에서 빠졌다). **정확한 실행 경로는 아직 코드를 추적해 확인하지
않았다** — 로그만으로는 "왜 최종 산출물에서 센소지가 빠졌는지"까지는
단정할 수 없다.

**재계획도 이 문제를 못 고쳤다**: `replan.py`가 Gemini 호출까지는 성공했다
(`AFC is enabled` → `HTTP 200 OK` → `문장을 붙인 뒤 위반이 생겼습니다`). 즉
LLM이 배치 변경 지시를 냈지만, 그 지시를 반영한 결과도 `MUST_VISIT_MISSING`을
해결하지 못했다. `replan.py`의 안전장치(재계획 결과가 계약을 어기면 원본
유지)는 정확히 설계대로 동작했지만, **애초에 왜 필수 방문지가 배치에서
빠졌는지**가 근본 원인이고 이건 미해결이다.

**제안 방향(적용 안 함)**: `allocate.py`가 연중 휴무 장소를 제외할 때
`must_visit`에 포함된 장소는 다른 처리(예: 검증 실패로 명확히 종료)를 하도록
분기하거나, `check_input_usable`이 "필수 방문지가 전 기간 휴무"인 경우를
사전에 걸러내는 규칙을 갖고 있는지 코드를 다시 읽고 확인해야 한다.

---

## 3. [확인됨] Verification Agent가 Gemini 마크다운 코드펜스를 벗기지 않아 파싱 실패

**위치**: `agent/supervisor/verification-agent/src/verification_agent/ai.py::_parse_response`

**재현**: 전체 루프 실행 중 verification-agent 로그에서 자연 발생.

**실제 에러**:
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for AiHumanJudgement
  Invalid JSON: expected value at line 1 column 1 [type=json_invalid,
  input_value='```json\n{\n  "avoid": {...니다."\n  }\n}\n```', input_type=str]
```

Gemini가 응답 텍스트를 ` ```json ... ``` ` 코드펜스로 감싸 보냈는데,
`_parse_response`가 이걸 벗기지 않고 그대로 `AiHumanJudgement.model_validate_json(text)`에
넘겨 파싱이 깨졌다.

**왜 지금까지 안 보였는가**: 이 서비스는 `GEMINI_API_KEY`를 `.env`에서 못 읽는
버그가 있었다(아래 5번 — 이번 세션에서 로더를 추가해 고침). 로더가 없을 때는
`AI_NOT_CONFIGURED`로 항상 skip되어 이 파싱 경로 자체가 실행되지 않았다. 로더를
추가하고 실제로 Gemini를 호출하게 되면서 이 문제가 처음 드러났다.

**영향**: 예외가 잡혀서 `_skipped_judgement("AI_JUDGEMENT_FAILED", ...)`로
폴백되므로 화면은 안 깨진다. 하지만 `avoid`/`pace`/`walking_level` 검사가
**Gemini 키가 있어도 사실상 항상 실패**하고 있었다는 뜻이다 — 조용한 실패의
전형적인 형태다.

**제안 방향(적용 안 함)**: `_parse_response`에서 텍스트 앞뒤의 ` ```json` /
` ``` ` 마커를 벗기는 전처리를 추가하거나, `response_mime_type="application/json"`
설정이 실제로 코드펜스 없는 순수 JSON을 강제하는지 확인이 필요하다(현재
`response_format`에 `mime_type: application/json`을 주고 있는데도 코드펜스가
붙어 나왔다).

---

## 4. [수정 완료 — 재확인 필요] Gemini `response_schema`가 `additionalProperties`를 거부함 (400 에러)

**위치**: `plan_agent/replan.py`, `plan_agent/ai.py`,
`verification_agent/ai.py`

**증상**: Pydantic 모델(`extra="forbid"` 사용)을 `response_schema`에 직접
넘기면 `model_json_schema()`가 만든 `"additionalProperties": false`를 Gemini
API가 이해하지 못해 400 에러가 난다.

```
google.genai.errors.ClientError: 400 INVALID_ARGUMENT.
Unknown name "additional_properties" at 'generation_config.response_schema'
```

**이번 세션에서 이미 수정함**: `gemini_schema.py`(plan-agent, verification-agent
양쪽에 동일하게 추가)가 스키마에서 `additionalProperties`를 재귀적으로 제거한
dict를 만들어 넘기도록 `replan.py`·`ai.py`(plan-agent)·`ai.py`(verification-agent)
세 곳을 고쳤다. **이 수정은 코드에 반영되어 있다** (이 문서가 다루는 "고치지
않은 문제" 목록과는 별개로, 이미 적용된 변경 사항으로 기록해 둔다).

**재확인이 필요한 것**: 이 수정 이후 `replan.py`의 Gemini 호출이 실제로
성공했다(2번 항목의 로그에서 `HTTP 200 OK` 확인). 다만 verification-agent
쪽은 3번 항목의 파싱 실패가 남아 있어, `gemini_schema` 수정만으로는 완전히
해결되지 않았다.

---

## 5. [수정 완료] Verification Agent가 `.env`를 읽지 않아 `GEMINI_API_KEY`가 있어도 인식하지 못함

**위치**: `agent/supervisor/verification-agent/src/verification_agent/main.py`

**증상**: plan-agent는 `config.py`에 상위 디렉터리를 탐색해 `.env`를 읽는
로더가 있는데, verification-agent는 순수 `os.getenv`만 썼다. 저장소 루트
`.env`에 `GEMINI_API_KEY`가 실제로 있어도 이 프로세스는 못 읽어서
`judge_human_constraints`가 항상 `AI_NOT_CONFIGURED`로 skip됐다.

**이번 세션에서 이미 수정함**: `env_loader.py`를 추가하고 `main.py` 최상단에서
import해 `.env`를 읽도록 고쳤다. 수정 후 로그에
`INFO:verification_agent.main:.env: ...` 가 찍히는 것으로 확인했다.

---

## 6. [확인됨, 원인 불명] 예산 부족 시나리오에서 Verification 타임아웃 후 최종 검증 누락

**위치**: `agent/supervisor/src/supervisor/graph.py`
(`_dispatch_verification`, `_should_replan`, `_replan`)

**재현**: `e2e_bad_input.py`의 `1_예산_부족` 시나리오 (예산을 30,000원으로 설정,
실제 추정 비용은 약 74만원).

**실제 로그(클라이언트 쪽 이벤트)**:
```
seq= 8 status  일정 가능 여부를 확인하고 있어요.
seq=10 status  피드백을 확인하고 있어요        <- 자동 재계획 트리거됨 (정상)
seq=12 status  일정을 다시 배치하고 있어요
seq=14 status  일정 가능 여부를 확인하고 있어요. <- 두 번째 검증 시도
seq=17 done    5일 19개 일정을 만들었어요. 검증은 건너뛰었어요.
```
총 40.95초 소요. 최종 결과의 `warnings`에
`'verification: 9358ms 안에 응답하지 않았습니다'`가 담겨 있고, `verification`
필드는 `None`으로 끝났다.

**분석**: 자동 재계획(1회)까지는 정확히 설계대로 동작했다 —
`possible:false` → 피드백 프롬프트 생성 → `/agent/itineraryReplan` 호출 →
재검증 시도. 문제는 **두 번째 검증 호출이 남은 시간 예산(9.358초) 안에 끝나지
못해 타임아웃**된 것이다. `CONFIG.verification_timeout_ms`(기본 15,000ms)를
`_budget_for()`가 "남은 전체 예산"으로 깎아서 쓰는데, 첫 번째 Plan 생성 +
Gemini 문장 생성 + 첫 검증 + 재계획(Gemini 호출 포함)까지 이미 시간을 많이
써서 두 번째 검증에 배정된 시간이 9.3초로 줄어 있었다.

**결과적으로**: 예산 부족이라는 실제 문제는 **한 번도 검증되지 않은 채**
"검증은 건너뛰었어요"로 사용자에게 일정이 그대로 나갔다. 계약 위반(종료
이벤트 누락 등)은 아니지만, 이 프로젝트가 지키려는 "조용한 실패 금지" 원칙과
어긋나는 결과다 — 예산이 3만원인데 74만원짜리 일정이 별다른 경고 없이
`done`으로 나갔다.

**제안 방향(적용 안 함)**:
- 전체 하드 타임아웃(`AGENT_HARD_TIMEOUT_MS`, 기본 40초)이 Gemini 호출
  2~3회(각 10~15초)를 포함하기엔 너무 빠듯하다. 재계획 경로의 시간 예산을
  재설계하거나, Gemini 호출 자체의 타임아웃을 더 짧게 강제해야 한다.
- 검증이 타임아웃으로 스킵된 경우, `warnings`에만 담기지 말고
  `done.summary`나 별도 필드로 사용자에게 더 명확히 알려야 한다(현재 요약
  문구 "검증은 건너뛰었어요"는 있지만 원인이 타임아웃이라는 사실이 잘
  드러나지 않는다).

---

## 7. [설계 확인 필요] 계약 위반 입력에 대한 `agent_failed` 코드 사용

**위치**: `agent/supervisor/src/supervisor/main.py`

**재현**: `e2e_bad_input.py`의 `4_계약위반_입력` 시나리오 (`trip_info` 누락).

**실제 결과**:
```
seq=2 error agent_failed: plan: 입력 형식이 계약과 맞지 않아요. retryable=True
```

**확인 필요한 점**: Plan Agent 자신은 스키마 위반을 `invalid_input` +
`retryable: false`로 정확히 보고한다(로그의 `WARNING plan_agent.main: 입력
스키마 위반`). 그런데 supervisor가 이를 감싸면서 `code: agent_failed`,
`retryable: true`로 바뀌어 나간다. `clients.py`의 `AgentCallFailed`가 하위의
`error.code`를 그대로 전달하는지, 아니면 예외를 감싸며 뭉개는지 확인이
필요하다. 만약 하위가 낸 `invalid_input`(재시도 무의미)이 상위에서
`agent_failed`(재시도 가능)로 바뀐다면, 사용자가 재시도해도 똑같이 실패할
입력에 "다시 시도" 버튼을 보여주게 된다.

---

## 종합

| # | 문제 | 심각도 | 상태 |
|---|---|---|---|
| 1 | 이동시간 추정 상한 없음 (293일짜리 이동시간 생성 가능) | 높음 | 미수정 |
| 2 | 재계획이 `MUST_VISIT_MISSING`을 반복 해결 못함, 근본 원인 미규명 | 중간 (확인 필요) | 미수정 |
| 3 | Verification Gemini 응답의 마크다운 코드펜스 미처리로 파싱 항상 실패 | 중간 | 미수정 |
| 4 | Gemini `response_schema`의 `additionalProperties` 거부 (400) | 높음 | **수정됨** |
| 5 | Verification Agent가 `.env`를 안 읽어 키가 있어도 미인식 | 중간 | **수정됨** |
| 6 | 예산부족 시나리오에서 재계획 후 두 번째 검증이 타임아웃, 결과가 검증 없이 나감 | 높음 | 미수정 |
| 7 | supervisor가 하위 error.code를 재매핑해 retryable 의미가 바뀔 수 있음 | 낮음 (확인 필요) | 미수정 |

세 서버(plan:8001, verification:8003, supervisor:8000)를 실제로 띄운 상태에서
`e2e_full_loop.py`·`e2e_bad_input.py`로 검증했고, 종료 이벤트 누락이나 무한
대기 같은 **계약상 치명적 위반은 발견되지 않았다** — 모든 시나리오가 정확히
하나의 종료 이벤트(`done` 또는 `error`)로 끝났다. 다만 위 7건은 "계약은
지켰지만 내용이 정직하지 않거나 부정확할 수 있는" 지점들이다.
