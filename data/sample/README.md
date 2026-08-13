# Plan Agent 샘플 데이터

Search Agent 더미 입력과 그에 대한 Plan Agent 산출물이다. 세 에이전트가 각각
다른 담당자 손에 있으므로, 합칠 때 필요한 **구체적인 예시**를 파일로 남겼다.

```powershell
# 다시 생성 (외부 API 호출 없음, 결정론적)
python agent/supervisor/plan-agent/tools/save_samples.py
```

## 파일

| 파일 | 계약 | 내용 |
|---|---|---|
| `search-to-plan.input.json` | `SearchToPlanInput` | Search Agent가 Plan Agent에 넘기는 것 |
| `plan-to-verification.output.json` | `PlanToVerificationInput` | Plan Agent가 Verification Agent에 넘기는 것 |
| `meta.json` | — | 입출력 요약과 검증 결과 |

정본 스키마는 [`../../agent/schemas/`](../../agent/schemas/)에 있고, 계약 예시는
[`../../agent/fixtures/`](../../agent/fixtures/)에 있다. 이 폴더는 **실행 결과**다.

## 입력 하나, 출력 하나

`pace` · `max_walking_level` · `must_visit` · `avoid` 는 모두 **프론트엔드
웹사이트가 사용자에게서 받아 `trip_info.persona`에 담아 보내는 값**이다.
Search Agent는 그 조건을 받아 항공편·숙소·장소 후보를 찾을 뿐이고, Plan
Agent는 둘을 합쳐 **일정 하나**를 만든다. 여러 안을 만들어 고르게 하지 않는다.

페이스를 바꿔 보려면 다른 입력을 넣으면 된다.

```powershell
python agent/supervisor/plan-agent/tools/run_dummy.py --pace 빡빡
python agent/supervisor/plan-agent/tools/run_dummy.py --days 3
```

## 담당별 사용법

### Search Agent 담당

`search-to-plan.input.json`이 **목표 출력 형태**다. 두 가지를 특히 지켜야 한다.

1. **`opening_hours`는 두 형식만 인정된다.** `HH:MM-HH:MM` 또는 `HH:MM 이후`.
   `화-일 09:30-17:00`이나 `상시 개방`을 주면 그 장소는 어디에 배치해도
   Verification Agent가 `INVALID_OPENING_HOURS`로 fail 판정한다. 시각은 두
   자리여야 한다 — `6:00-17:00`은 파싱되지 않는다.
2. **좌표가 실제 위치와 맞아야 한다.** 좌표가 틀리면 이동시간과 경로가 전부
   무의미해진다.

### Verification Agent 담당

`plan-to-verification.output.json`을 그대로 넣으면 된다.

```powershell
curl -X POST http://localhost:8003/agent/itineraryVerify `
  -H "Content-Type: application/json" `
  -H "Accept: text/event-stream" `
  --data-binary "@data/sample/plan-to-verification.output.json"
```

이 파일은 결정론 규칙 5개를 통과하도록 만들어져 있다(`meta.json`의
`verification.passed` 확인). 여기서 `fail`이 나오면 두 구현의 판정이 어긋난
것이므로 알려주면 맞추겠다.

### 프론트엔드 담당

`plan-to-verification.output.json`으로 화면을 그려볼 수 있다.
`plan.days[].items[]`가 일자별 일정이고 `travel_from_prev`가 항목 사이 이동이다.

## 알아두어야 할 점

**이동시간은 좌표 기반 추정값이다.** 샘플 생성 시 Google Routes API를 호출하지
않는다(과금 방지 + 결정론 유지). 실제 서버는 `GOOGLE_MAPS_API_KEY`가 있으면
실제 경로로 계산한다. 계약에는 추정 여부를 담을 필드가 없어서 그 사실은 서버
로그에만 남는다.

**`note` 문장은 템플릿이다.** `GEMINI_API_KEY`가 있으면 Gemini가 더 구체적인
배치 이유를 쓴다. 샘플은 결정론을 유지하려고 Gemini를 끄고 만들었다.

**숙박비는 밤 수만큼 나눠 담겨 있다.** `LAST_ITEM_NOT_STAY` 규칙 때문에 숙소
항목이 매일 반복되는데, 총액을 그대로 넣으면 예산 합산에서 중복 가산된다.
`meta.json`의 `stay_price_sum`이 선택 숙소 총액과 같은지 확인할 수 있다.
