# Plan Agent 샘플 데이터

Search Agent 더미 입력과 그에 대한 Plan Agent 산출물 쌍이다. 세 에이전트가
각각 다른 담당자 손에 있으므로, 합칠 때 필요한 **구체적인 예시**를 파일로
남겼다.

```powershell
# 다시 생성 (외부 API 호출 없음, 결정론적)
python agent/supervisor/plan-agent/tools/save_samples.py
```

## 파일 구성

| 파일 | 내용 |
|---|---|
| `index.json` | 8개 시나리오 요약 — 일수·항목 수·비용·검증 결과 |
| `*.search-input.json` | Search Agent가 Plan Agent에 넘기는 `SearchToPlanInput` |
| `*.plan-output.json` | Plan Agent가 Verification Agent에 넘기는 `PlanToVerificationInput` |

## 담당별 사용법

### Search Agent 담당

`*.search-input.json`이 **목표 출력 형태**다. 이 형식으로 만들면 Plan Agent가
바로 받는다.

특히 두 가지를 지켜야 한다.

1. **`opening_hours`는 두 형식만 인정된다.** `HH:MM-HH:MM` 또는 `HH:MM 이후`.
   `화-일 09:30-17:00`이나 `상시 개방` 같은 문자열을 주면 그 장소는 어디에
   배치해도 Verification Agent가 `INVALID_OPENING_HOURS`로 fail 판정한다.
   시각은 두 자리여야 한다 — `6:00-17:00`은 파싱되지 않는다.
2. **좌표가 실제 위치와 맞아야 한다.** 좌표가 틀리면 이동시간·경로가 전부
   무의미해진다.

### Verification Agent 담당

`*.plan-output.json`을 그대로 넣으면 된다.

```powershell
curl -X POST http://localhost:8003/agent/itineraryVerify `
  -H "Content-Type: application/json" `
  -H "Accept: text/event-stream" `
  --data-binary "@agent/supervisor/plan-agent/samples/4일_표준.plan-output.json"
```

8개 샘플 전부 결정론 규칙 5개를 통과하도록 만들어져 있다. 만약 여기서
`fail`이 나오면 두 구현의 판정이 어긋난 것이므로 알려주면 맞추겠다.

### 프론트엔드 담당

`*.plan-output.json`으로 화면을 그려볼 수 있다. `plan.days[].items[]`가
일자별 일정이고, `travel_from_prev`가 항목 사이 이동 정보다.

## 시나리오 목록

| 시나리오 | 확인하려는 것 |
|---|---|
| `1일_단순` | 최소 구성. 당일 여행 |
| `4일_표준` | 일반적인 경우. 균등 분배 확인 |
| `5일_빡빡` | `빡빡` 페이스에서 하루 밀도 |
| `3일_여유` | `여유` 페이스에서 하루 2~3곳 유지 |
| `휴무일_포함` | 월요일 휴관 장소를 월요일에 두지 않는지 |
| `예산_촉박` | 예산이 빠듯할 때 초과 판정 |
| `항공_포함` | `selected.flight`가 있을 때 |
| `도보_여행` | `transport_mode`가 도보일 때 이동시간 |

## 알아두어야 할 점

**이동시간은 좌표 기반 추정값이다.** 샘플을 만들 때 Google Routes API를
호출하지 않는다(과금 방지 + 결정론 유지). 실제 서버는 `GOOGLE_MAPS_API_KEY`가
있으면 실제 경로로 계산한다. 계약에는 추정 여부를 담을 필드가 없어서
그 사실은 서버 로그에만 남는다.

**`note` 문장은 템플릿이다.** `GEMINI_API_KEY`가 있으면 Gemini가 더 구체적인
배치 이유를 쓴다. 샘플은 결정론을 유지하려고 Gemini를 끄고 만들었다.

**숙박비는 밤 수만큼 나눠 담겨 있다.** `LAST_ITEM_NOT_STAY` 규칙 때문에 숙소
항목이 매일 반복되는데, 총액을 그대로 넣으면 예산 합산에서 중복 가산된다.
`stay_price_sum`이 선택 숙소 총액과 같은지 `index.json`에서 확인할 수 있다.
