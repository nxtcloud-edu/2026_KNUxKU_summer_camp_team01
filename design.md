# JustGO — AI 디자인 프롬프트 세트

> **문서 버전** v1.0 · **최종 수정** 2026-08-13
> **짝 문서** [`spec.md`](./spec.md) — 화면·데이터·인터랙션 전체 명세
> **이 문서의 역할** `spec.md`의 명세를 **v0 / Figma AI / Lovable / Cursor / Claude** 같은 도구에 그대로 붙여넣을 수 있는 프롬프트로 변환한 것

---

## 이 문서는 잠긴 디자인 시스템이다

이 프로젝트는 **`design.md` 관리 프로젝트**다. 즉,

- 화면마다 다른 룩을 만들지 **않는다**. 모든 화면이 하나의 시스템을 공유한다.
- 프롬프트마다 색·폰트·radius·모션을 새로 고르지 **않는다**. [B. 공통 시스템 프롬프트](#b-공통-시스템-프롬프트)의 토큰만 쓴다.
- 구조적 다양성은 "화면 간 룩 차이"가 아니라 **"각 화면이 그 화면의 과제에 맞는 고유한 배치를 갖는 것"** 으로 달성한다.

한 가지 예외: **S0 홈**은 유일하게 랜딩 성격의 화면이다. 여기서만 "히어로 → 3열 기능 소개 → CTA → 4단 푸터" 라는 **AI가 기본값으로 뱉는 리듬을 의도적으로 피한다**. 자세한 규칙은 [C-1](#c-1-s0-홈)에 있다.

---

## 목차

| 절 | 내용 |
|---|---|
| A | [도구별 사용법](#a-도구별-사용법) |
| B | [공통 시스템 프롬프트](#b-공통-시스템-프롬프트) ← **모든 프롬프트 앞에 반드시 붙인다** |
| C | [화면별 프롬프트 10개](#c-화면별-프롬프트) |
| D | [컴포넌트 프롬프트 8개](#d-컴포넌트-프롬프트) |
| E | [리파인 프롬프트](#e-리파인-프롬프트) |
| F | [이미지·일러스트 생성 프롬프트](#f-이미지일러스트-생성-프롬프트) |
| G | [운용 규칙과 자체 검수](#g-운용-규칙과-자체-검수) |

---

# A. 도구별 사용법

## A-1. 어떤 도구에 무엇을 넣나

| 도구 | 잘하는 것 | 넣는 것 | 주의 |
|---|---|---|---|
| **v0 (Vercel)** | React + Tailwind + shadcn 코드 생성. 이 프로젝트 스택과 정확히 일치 | B + C의 화면 프롬프트 1개 | 한 번에 화면 1개만. 여러 화면을 한 프롬프트에 넣으면 전부 얕아진다 |
| **Cursor / Claude Code** | 기존 코드베이스에 맞춰 수정·확장 | B + C 또는 D + `spec.md`의 해당 절 링크 | `spec.md`를 컨텍스트에 함께 넣으면 정확도가 크게 오른다 |
| **Lovable** | 여러 화면을 한 앱으로 엮기 | B + C 전체를 순서대로, 화면당 한 턴 | 첫 턴에서 B를 확실히 각인시킬 것 |
| **Figma AI / Figma Make** | 시각 시안, 컴포넌트 세트 | B + D의 컴포넌트 프롬프트 | 코드가 아니라 시안이므로 상태(8종)를 명시적으로 요구해야 한다 |
| **Claude / ChatGPT (대화)** | 레이아웃 대안 탐색, 카피 다듬기 | B + C + "대안 3개를 제시해줘" | 코드 생성보다 **의사결정 상담**에 쓸 때 가치가 크다 |

## A-2. 프롬프트 조립 공식

```
[B. 공통 시스템 프롬프트 전문]
        +
[C 또는 D에서 만들 대상 프롬프트 1개]
        +
(선택) [E의 리파인 프롬프트 — 1차 결과를 받은 뒤]
```

B를 빼고 C만 넣으면 도구가 자기 기본값(보라 그라데이션, 둥근 카드, 이모지 아이콘)으로 돌아간다. **B는 매 턴 붙인다.** 대화형 도구라면 최소한 3턴마다 다시 붙인다.

## A-3. 1차 결과를 받은 뒤 순서

```
1. G-1 자체 검수 체크리스트로 스스로 점수 매기게 한다 (프롬프트에 이미 포함됨)
2. 눈으로 확인: 금지 목록(B-5) 위반이 있는지
3. E의 리파인 프롬프트로 1~2회 교정
4. 그래도 안 되면 프롬프트를 쪼갠다 (화면 → 섹션 단위)
```

---

# B. 공통 시스템 프롬프트

> **아래 블록 전체를 복사해 모든 프롬프트 맨 앞에 붙인다.**

````text
당신은 여행 계획 웹앱 "JustGO"의 프론트엔드를 만드는 시니어 프로덕트 디자이너 겸
프론트엔드 엔지니어입니다. 아래 시스템을 **그대로** 따르세요. 임의로 색·폰트·모양을
새로 고르지 마세요.

## 0. 제품 한 줄
도시와 날짜만 정하면 AI 에이전트가 항공권·숙소·관광지를 찾아 검증된 여행 일정표까지
만들어 주는 웹앱. 한국어 UI. 데스크톱 우선(1440px), 모바일(375px) 필수 대응.

## 1. 디자인 방향
- 비주얼: Linear / Notion 계열의 **뉴트럴 미니멀**. 고밀도, 얇은 선, 절제된 모션.
- 레이아웃·상호작용: Wanderlog 계열. **좌측 리스트 + 우측 지도 스플릿**, 리스트와
  지도가 hover·클릭 단위로 양방향 동기화.
- 판정 기준: 색·타이포·여백·모션은 Linear를 따르고, 정보 배치와 상호작용은
  Wanderlog를 따른다.
- 화면의 95%는 흰색·회색·검정. 브랜드 색은 주 행동 1개와 포커스 링에만 쓴다.
- 위계는 여백이 아니라 **선의 굵기와 글자 굵기**로 만든다.

## 2. 색 토큰 (OKLCH. 이 값만 사용. 새 색을 만들지 마세요)
--bg              oklch(100% 0 0)              /* 페이지 배경 */
--surface         oklch(98.4% 0 0)             /* 카드·패널 */
--surface-hover   oklch(96.7% 0.001 286)       /* 행 hover */
--surface-active  oklch(94.6% 0.002 286)
--surface-sunken  oklch(92% 0.004 286)         /* 트랙 */
--border          oklch(92% 0.004 286)         /* 1px hairline */
--border-strong   oklch(87% 0.005 286)         /* 입력창 */
--text            oklch(21% 0.006 286)         /* 본문·제목 */
--text-secondary  oklch(44.2% 0.017 286)       /* 보조 */
--text-muted      oklch(55.2% 0.016 286)       /* 캡션 */
--text-disabled   oklch(71.1% 0.013 286)       /* 비활성·placeholder 전용. 본문 금지 */
--primary         oklch(53.5% 0.163 274)       /* 브랜드. 흰 글자 대비 4.7:1 */
--primary-hover   oklch(48.5% 0.158 274)
--primary-fg      oklch(100% 0 0)
--primary-subtle  oklch(97% 0.012 274)         /* 선택된 행 배경 */
--primary-border  oklch(87% 0.05 274)
--success         oklch(50% 0.115 148)         /* 검증 통과 */
--success-subtle  oklch(97.5% 0.018 150)
--warning         oklch(48% 0.105 76)          /* 주의 */
--warning-subtle  oklch(97.8% 0.025 95)
--danger          oklch(53.5% 0.185 26)        /* 충돌 */
--danger-subtle   oklch(96.8% 0.014 20)

일자 색 (일정의 날짜별 지도 마커·헤더에 순환 배정. 흰 글자 대비 4.5:1 이상)
--day-1 oklch(53.5% 0.163 274)  /* 인디고 */
--day-2 oklch(51%   0.135 46)   /* 테라코타 */
--day-3 oklch(48%   0.093 167)  /* 틸 */
--day-4 oklch(47%   0.145 328)  /* 플럼 */
--day-5 oklch(50%   0.105 258)  /* 스틸블루 */
--day-6 oklch(49.5% 0.145 12)   /* 로즈 */

## 3. 타이포그래피
- 폰트: Pretendard Variable(한글·기본) + Inter(라틴 폴백). 코드성 표기만 JetBrains Mono.
- 굵기는 400 / 500 / 600 **세 개만**. 700 이상, 400 미만 금지.
- 크기: 11 / 12 / 13 / **14(본문)** / 15 / 16 / 20 / 24 / 32 / 44
- 자간: 크기가 커질수록 좁힌다 (14px에 -0.011em, 44px에 -0.028em). 한글에 양수 자간 금지.
- 가격·시각·소요시간 등 **변하는 숫자에는 tabular-nums** 강제.
- 제목은 항상 로만체. **이탤릭 제목 금지**(강조는 굵기나 색으로).

## 4. 형상 · 간격 · 모션
- radius: 컨트롤 6px / 카드 8px / 모달·드로어 12px. 16px 이상 금지(pill 버튼 예외).
- 그림자: 카드에는 쓰지 않는다. 떠 있는 요소(드로어·팝오버·토스트)만 아주 미묘하게.
- 간격: 4pt 스케일. 리스트 행 높이 36~40px, 카드 패딩 12~16px.
- 아이콘: lucide-react, strokeWidth 1.5, 크기 14/16/20/24 중 하나.
- 모션: 기본 140ms, 이징 cubic-bezier(0.2,0,0,1). 200ms 초과 hover 금지.
  transform·opacity만 애니메이션. **바운스·오버슈트 이징 금지.**
  **한 화면에 모션 종류는 3개 이하.** 없어도 정보가 전달되는 애니메이션은 삭제.
  prefers-reduced-motion 대응 필수.

## 5. 금지 목록 (하나라도 어기면 결과물을 폐기하고 다시 만듭니다)
- 그라데이션 배경. (예외: 이미지 위 텍스트 가독성용 어두운 오버레이 1개)
- 보라~파랑 그라데이션, 네온, 글로우, 글래스모피즘, 블러 배경 장식.
- 원색·형광 CTA. 브랜드 색은 --primary 하나뿐.
- 이모지를 기능 아이콘으로 쓰기. (예외: 국기 이모지 1종만)
- 이탤릭 제목. 대문자 변환(uppercase) 라벨.
- 섹션 위의 번호형 말머리(`01 · FEATURES`, `Chapter 2`, `STEP 03`).
- **말머리 라벨을 왼쪽 열에, 제목을 오른쪽 열에 두는 2단 헤더 배치**(hanging header).
  라벨이 필요하면 제목 바로 위에 같은 열로 쌓는다.
- 가짜 브라우저 창(주소창 + 신호등 점 3개), 가짜 휴대폰 목업, 가짜 코드 창 크롬.
  스크린샷이 필요하면 실제 캡처를 얇은 보더의 figure로 감싼다.
- **없는 숫자 만들기.** "50,000+ 팀이 사용", "3배 빠른", "만족도 98%" 같은 지표를
  임의로 만들지 마세요. 제품에 실제 사용자 수치가 없습니다. 필요하면 그 섹션을
  아예 다른 구조로 바꾸세요.
- 존재하지 않는 후기·로고·수상 배지.
- 로딩을 스피너 하나로 처리하기. (에이전트 작업은 무엇을 하는지 문장으로 보여준다)
- 삭제를 확인 다이얼로그로 막기. (즉시 실행 + 되돌리기 토스트)
- z-index 임의값(z-[9999]). 색 임의값(bg-[#FAFAFA]).

## 6. 인터랙티브 요소는 8개 상태를 모두 코드로 낸다
default / hover / focus-visible / active / disabled / loading / error / success
- focus-visible: 2px 링, --primary 40% 투명도, offset 2px. 즉시 표시(애니메이션 금지).
- disabled: opacity 0.5 + cursor not-allowed.
- loading: 좌측 16px 스피너 + 라벨 유지(버튼 폭이 변하면 안 됨).

## 7. 모바일 필수 사항 (375px에서 반드시 통과)
- 가로 스크롤 0. html과 body에 overflow-x: clip (hidden 아님).
- 버튼·내비 링크·CTA의 라벨이 **두 줄로 줄바꿈되지 않게** 한다.
- 이미지가 들어가는 그리드 트랙은 `minmax(0, 1fr)`. 맨 `1fr` 금지.
- 큰 제목은 `overflow-wrap: anywhere; min-width: 0`.
- 100vh 금지, **100dvh** 사용.
- 터치 타깃 최소 44×44px. hover에만 존재하는 기능은 모바일에서 항상 표시.
- 모바일 입력창 font-size 16px (iOS 자동 확대 방지).

## 8. 출력 형식
- React + TypeScript + Tailwind CSS + shadcn/ui.
- 색·폰트는 **반드시 토큰 이름으로 참조**한다. 파일 안에 OKLCH·hex 값을 직접 쓰지 않는다.
  필요한 값이 토큰에 없으면 토큰 블록에 새 변수로 올린 뒤 이름으로 참조한다.
- 한국어 문구는 프롬프트에 주어진 것을 **그대로** 쓴다. 임의로 바꾸거나 영어로 만들지 않는다.
- 파일 맨 위에 다음 형식의 주석을 남긴다:
  /* JustGO · screen: <화면ID> · 자체검수: P_ H_ E_ S_ R_ V_ */
- 코드 뒤에 자체 검수 결과를 6축(철학·위계·완성도·구체성·절제·다양성) 1~5점으로
  적고, 3점 미만 항목이 있으면 그 부분을 수정한 뒤 다시 제출한다.
````

---

# C. 화면별 프롬프트

각 프롬프트는 **B 다음에 붙인다.** 화면 ID는 `spec.md` 7장과 동일하다.

## C-1. S0 홈

> **구조 주의**: 이 화면은 이 앱의 유일한 랜딩 성격 화면이다. AI가 기본값으로 만드는
> "히어로 → 3열 아이콘 카드 → 가짜 후기 → 4단 링크 푸터" 리듬을 **쓰지 않는다.**
> 대신 **"바로 시작하는 검색 입력 + 내가 하던 일 이어가기"** 두 블록만으로 끝낸다.
> 제품 설명은 페이지 맨 아래 한 줄로 축약한다.

````text
[S0] 홈 화면을 만드세요.

목적: 돌아온 사용자가 진행 중인 여행을 3초 안에 이어서 열고, 처음 온 사용자는
바로 도시를 검색해 시작한다.

## 구조 (위에서 아래로 이 순서만. 섹션을 추가하지 마세요)
1. 상단 바 (56px): 좌측 워드마크 "JustGO" (text-base 600).
   우측에 테마 토글 아이콘 버튼 + ⌘K 힌트 버튼. 링크 메뉴 없음.
2. 시작 블록 (상하 패딩 96px, 최대 폭 720px 중앙):
   - h1 2행, text-4xl(44px) 600, 행간 52px:
     "도시와 날짜만 정하세요."
     "나머지는 AI가 계획합니다."
   - 설명 2행, text-lg, --text-secondary:
     "항공권부터 관광지, 하루 동선까지."
     "검증까지 마친 여행 일정을 만들어 드려요."
   - 검색 폼: 높이 56px, radius 8px, 1px --border-strong 한 덩어리.
     좌측에 도시 자동완성 입력(placeholder "어디로 떠나세요?", 좌측 Search 아이콘 16px),
     우측에 primary 버튼 "새 여행 시작". 폼 전체가 포커스 시 2px 링.
   - 그 아래 한 줄: "인기" 라벨 + 도시 칩 4개.
     칩은 국기 이모지 + 도시명. (🇯🇵 도쿄 / 🇯🇵 오사카 / 🇫🇷 파리 / 🇹🇭 방콕)
3. 내 여행 블록 (상단 1px --border 로만 구분):
   - h2 "내 여행" text-xl 600 + 우측에 개수 "3개" text-sm --text-muted
   - 카드 그리드: repeat(auto-fill, minmax(280px, 1fr)), 최대 3열, 갭 16px
4. 맨 아래 한 줄 (text-sm --text-muted, 중앙): 
   "도시와 날짜를 고르면 AI가 항공권·숙소·관광지를 찾아 일정을 만들고 검증합니다."
   링크 컬럼 푸터를 만들지 마세요.

## 여행 카드 사양
- 상단 이미지 160px, object-cover, 상단만 radius 8px
- 이미지 우상단 오버레이: 검증 완료 시 success 배지 "검증 완료"
- 이미지 우상단(hover 시): 더보기 아이콘 버튼 (배경 --bg/90 + backdrop-blur)
- 본문 패딩 14px, 4행:
  1행 국기 16px + 제목 text-base 500 (1줄 말줄임)
  2행 날짜 요약 text-sm --text-muted  (예: "6.12–6.16 · 4박5일" / 없으면 "날짜 미정")
  3행 진행바 4px + 현재 단계 라벨 text-xs --text-muted
  4행 상대 시간 text-xs --text-disabled  (예: "2시간 전")
- hover 시 우하단에 "이어서" subtle 버튼이 페이드 인
- 카드 전체가 링크. 더보기 메뉴는 링크 안에 중첩하지 말고 형제 요소로 배치

## 목 데이터 (이 3개만 사용)
1. 🇯🇵 도쿄 여행 · 6.12–6.16 · 4박5일 · 진행 100% "완료" · 검증 완료 · 2시간 전
2. 🇫🇷 파리 여행 · 9.03–9.10 · 7박8일 · 진행 60% "일정" · 어제
3. 🇹🇭 방콕 여행 · 날짜 미정 · 진행 15% "여행 스타일" · 3일 전

## 빈 상태 (여행이 0개일 때 "내 여행" 블록 대신)
lucide Compass 아이콘 40px --text-disabled +
제목 text-lg 500 "아직 계획한 여행이 없어요" +
설명 text-sm --text-muted "위에서 도시를 검색해 첫 여행을 시작해 보세요"
+ primary 버튼 "새 여행 시작". 일러스트를 그리지 마세요.

## 반응형
- 1200px+: 카드 3열
- 768~1199px: 카드 2열
- 767px 이하: 카드 1열, h1은 text-3xl(32px), 검색 폼은 2행으로 분리
  (입력 위·버튼 아래 전체 폭), 인기 칩은 가로 스크롤

## 인터랙션
- 도시를 선택하면 시작 버튼 라벨이 "도쿄 여행 시작"으로 바뀐다
- 카드 더보기 메뉴: 이름 변경 / 복제 / 삭제. 삭제는 즉시 실행 + "되돌리기" 토스트 6초

모션은 2개만: 카드 hover의 보더 색 전환, "이어서" 버튼 페이드 인.
````

## C-2. S1 도시와 날짜

````text
[S1] 여행 위저드의 1단계 — 도시와 날짜 선택 화면을 만드세요.

## 공통 셸 (S1~S7 모든 화면에 동일하게 적용)
1. 여행 헤더 바 (52px, sticky, 하단 1px --border):
   좌측: 뒤로 아이콘 + 국기 + 도시명(text-base 500) + " · " + 날짜 요약(text-sm
   --text-muted) + " · " + 인원 요약. 도시 미선택 시 "새 여행"만.
   우측: 저장 인디케이터("모든 변경사항 저장됨" + Check 14px --text-muted),
   ⌘K 버튼, 테마 토글, 더보기.
2. 단계 진행바 (40px, sticky, 하단 1px --border):
   ①도시 ─ ②여행 스타일 ─ ③항공권 ─ ④숙소 ─ ⑤가고 싶은 곳 ─ ⑥일정 ─ ⑦검증
   - 완료: 20px 원에 Check 아이콘(--success) + 라벨 --text-secondary
   - 현재: 20px 원 --primary 채움 + 흰 숫자 + 라벨 text 600 + 하단 2px --primary
   - 이후: 20px 원 보더만 + 라벨 --text-muted
   - 연결선 1px --border (완료 구간은 --success)
   - 좌측 정렬, 넘치면 가로 스크롤(스크롤바 숨김)
   - 767px 이하: 라벨 숨기고 점 표시 + 우측에 "1/7 도시"
3. 하단 푸터 (60px, sticky): 좌측 "← 이전"(secondary), 우측 "다음: 여행 스타일 →"(primary)

## 본문 (최대 폭 720px, 중앙, 상하 패딩 40px)
- h1 text-2xl(24px) 600 "어디로, 언제 떠나세요?"
- 설명 text-base --text-secondary "도시와 날짜만 정하면 나머지는 AI가 준비합니다."
- 상단 1px --border 로 구분 후:

### 목적지 (라벨 text-sm 500)
[상태 A · 미선택] 높이 48px 입력창. 좌측 Search 16px --text-muted,
placeholder "도시 이름을 입력하세요". 아래에 자동완성 드롭다운을 펼친 상태로 보여주세요:
- 드롭다운: 입력창과 같은 폭, 최대 높이 360px, radius 8px, 1px --border, 미묘한 그림자
- 그룹 헤더 text-xs 500 --text-muted, 패딩 6px 8px 4px
- 옵션 행 36px: 좌측 국기 20px + 도시명 text-base + 국가명 text-sm --text-muted
  + 우측에 "데모 데이터" neutral 배지(해당 도시만)
- 활성 행: --surface-hover 배경 + 좌측 2px --primary
- 내용:
  그룹 "최근 검색" → 🇯🇵 도쿄 / 일본
  그룹 "인기 도시" → 🇯🇵 오사카 / 일본 [데모 데이터], 🇫🇷 파리 / 프랑스 [데모 데이터],
  🇹🇭 방콕 / 태국 [데모 데이터], 🇺🇸 뉴욕 / 미국, 🇪🇸 바르셀로나 / 스페인

[상태 B · 선택 완료] 입력창 대신 높이 132px 카드:
- 배경은 도시 사진 object-cover, radius 8px
- 텍스트 가독성용으로 하단에서 위로 어두워지는 오버레이 1개만 허용
- 좌하단: 국기 20px + 도시명 text-xl 600 흰색 / 아래 "일본 · JPY · GMT+9" text-sm 흰색 80%
- 우상단: "변경" 버튼 (배경 --bg/90 + backdrop-blur, sm 사이즈)

### 여행 날짜 (라벨 text-sm 500 + 우측에 "4박 5일" text-sm --text-muted)
- 도시 미선택 시: 비활성 입력창에 "도시를 먼저 선택해 주세요"
- 도시 선택 시: 달력 2개월 나란히
  - 셀 36×36px, radius 6px, text-sm
  - 오늘: 하단 2px 점 --primary
  - 과거: --text-disabled, 클릭 불가
  - 선택 시작·종료: --primary 채움 + 흰 글자 (시작은 좌측만, 종료는 우측만 둥글게)
  - 사이 범위: --primary-subtle 배경, 글자색 유지
  - 달력 상단에 빠른 선택 칩 3개: "주말 (금–일)" "3박 4일" "1주일"
- 달력 아래 요약: "6월 12일 목요일 → 6월 16일 월요일" text-base 500 +
  "4박 5일" text-sm --text-muted + "초기화" ghost 버튼

## 반응형
767px 이하: 달력을 바텀시트로 전환. 날짜 필드를 탭하면 시트가 60% 높이로 열리고
1개월 표시 + 세로 스크롤, 시트 하단에 전체 폭 "적용" 버튼. 히어로 카드 높이 108px.

## 데스크톱 와이어를 2개 상태로 모두 만들어 주세요 (미선택 / 선택 완료).
모션은 2개만: 드롭다운 등장(140ms 위로 슬라이드 + 페이드), 입력창↔카드 크로스페이드.
````

## C-3. S2 페르소나 설문

````text
[S2] 여행 위저드 2단계 — 여행 스타일 설문 화면을 만드세요. 공통 셸은 S1과 동일.

목적: 에이전트가 좋은 결과를 내기 위한 최소 조건을 "설문 같지 않게" 받는다.
응답 필수는 4개(+조건부 1개)뿐이고 나머지는 기본값이 이미 들어 있다.

## 본문 (최대 폭 720px 중앙)
- h1 text-2xl 600 "어떤 여행을 원하세요?"
- 설명 text-base --text-secondary "몇 가지만 알려주시면 AI가 취향에 맞춰 찾아드려요."
- 진행 표시: 4px 진행바(--primary, 50% 채움) + 우측 "필수 4개 중 2개 완료"
  text-xs --text-muted

## 그룹 헤더 스타일
text-sm 500 --text-muted 라벨의 좌우로 1px --border 선이 이어지는 형태.
그룹 간 간격 32px, 문항 간 24px. 번호를 붙이지 마세요.

## 그룹 1 — "함께 찾을 것"
Q1 라벨 text-base 500 "항공권을 함께 찾아드릴까요?" (응답 완료 시 우측에 Check 14px --success)
  선택 카드 2개 (2열, 높이 76px, 갭 12px):
  - 카드 A: lucide Plane 20px / 제목 "네, 찾아주세요" text-base 500 /
    설명 "조건에 맞는 왕복 항공권을 비교해요" text-sm --text-muted
  - 카드 B: lucide Ban 20px / "아니요, 괜찮아요" / "이미 예약했거나 직접 알아볼게요"
  - 미선택: --bg + 1px --border. hover: --border-strong + --surface-hover
  - 선택: --primary-subtle + 1px --primary-border + 우하단 CircleCheck 18px --primary
  - radiogroup으로 구현. 카드 A가 선택된 상태로 보여주세요.

Q1a (Q1이 "네"일 때만 나타남) 라벨 "어디서 출발하세요?"
  높이 36px 셀렉트: lucide Plane 16px + "🇰🇷 인천국제공항 (ICN)" + 우측 ChevronDown

Q2 "숙소를 함께 찾아드릴까요?" — Q1과 같은 카드 2개
  (lucide BedDouble / Ban, 설명은 "조건에 맞는 숙소를 비교해요" / 위와 동일)

## 그룹 2 — "누구와, 어떻게"
Q3 "누구와 함께 가세요?" — 컴팩트 카드 5열, 높이 64px, 아이콘 20px + 라벨 text-sm
  lucide User "혼자" / Heart "연인" / Users "가족" / UsersRound "친구" / Briefcase "동료"
  ("연인"이 선택된 상태)

Q4 "인원은 몇 명인가요?" — 행 높이 40px 카운터 3개
  좌측 라벨 text-base + 보조설명 text-sm --text-muted, 우측 [−] 값 [+]
  버튼 28×28px subtle, 값은 폭 32px 중앙 tabular-nums
  - "성인" / "13세 이상" / 값 2
  - "아동" / "2–12세" / 값 0
  - "어르신" / "65세 이상" / 값 0
  아래 1px --border 구분선 후 스위치 행: "반려동물과 함께 가요" (off)

Q5 "여행 페이스는 어떻게 할까요?" — 카드 3열, 높이 72px
  제목 text-base 500 / 방문지 수 text-sm / 설명 text-xs --text-muted
  - "여유롭게" / "하루 2–3곳" / "이동 최소화"
  - "적당히" / "하루 3–4곳" / "균형 잡힌 일정"  ← 선택 상태
  - "빽빽하게" / "하루 5곳 이상" / "최대한 많이"
  아래 파생 문구 text-xs --text-muted:
  "하루 09:00–20:00, 3–4곳 방문 기준으로 일정을 만들어요"

Q6 "어떤 걸 좋아하세요?" + 우측 "2개 선택" text-xs --text-muted
  칩 10개, flex-wrap, 갭 8px, 높이 32px, radius 9999px, 패딩 0 12px, text-sm 500
  각 칩은 lucide 아이콘 16px + 라벨. 이모지를 쓰지 마세요.
  - UtensilsCrossed "맛집" ← 선택
  - Coffee "카페·디저트"
  - Trees "자연·공원" ← 선택
  - Building2 "미술관·박물관"
  - Landmark "역사·문화"
  - ShoppingBag "쇼핑"
  - Moon "야경·나이트라이프"
  - Ticket "액티비티·테마파크"
  - Camera "사진 스팟"
  - Waves "휴양·온천"
  - 미선택: --bg + 1px --border + --text-secondary
  - 선택: --primary-subtle + 1px --primary-border + --primary 글자 + 좌측 Check 14px
  - 중요: 선택 시 폭이 변하지 않게, 체크 아이콘 자리를 미선택 때도 투명하게 확보

## 그룹 3 — 접힌 아코디언
행 36px: ChevronRight 16px + "더 자세히 알려주기" text-base 500 + neutral 배지 "선택"
아래 부제 text-xs --text-muted "이동 수단 · 고려사항 · 예산 · 메모"
(펼친 상태도 함께 만들어 주세요: 이동수단 칩 4개, 스위치 4개, 예산 필드, 텍스트영역)

## 반응형
639px 이하: 선택 카드 1열(높이 68px, 아이콘을 좌측 인라인으로),
동행 3열 2행, 페이스 1열.

모션은 2개만: 조건부 문항 등장(200ms 위로 슬라이드), 체크 아이콘 그리기(200ms).
````

## C-4. S3-a 항공권 조건 설문

````text
[S3-a] 항공권 검색 전 조건 설문 화면을 만드세요. 공통 셸 동일.
모든 항목은 선택 사항입니다.

## 본문 (최대 폭 720px 중앙)
- h1 text-2xl 600 "항공권을 찾기 전에"
- 설명 "조건을 알려주시면 맞는 것만 골라드려요. 모두 선택 사항이에요."
- 요약 카드 (높이 72px, --surface 배경, radius 8px, 1px --border):
  1행 text-base 500 "🇰🇷 인천 (ICN) → 🇯🇵 도쿄 (NRT · HND)"
  2행 text-sm --text-muted "6.12(목) 출발 · 6.16(월) 귀국 · 성인 2명 · 이코노미"
  우측 "수정" ghost 버튼

## 필드 (간격 24px)
1. "도착 공항" — 칩 2개: "나리타 NRT"(선택) "하네다 HND"(선택)
   아래 힌트 text-xs --text-muted "둘 다 선택하면 더 많은 항공편을 비교해요"
2. "경유" — 라디오 인라인: "직항만"(선택) / "경유도 괜찮아요"
   ("경유도 괜찮아요" 선택 시에만 아래 슬라이더: "최대 경유 시간" 1~12시간, 값 4시간)
3. "가는 날 출발 시간대" + 우측 상태 "무관" 또는 "1개 선택"
   칩 4개: "새벽 00–06" / "오전 06–12"(선택) / "오후 12–18" / "저녁 18–24"
4. "오는 날 출발 시간대" — 칩 4개, "오후"와 "저녁" 선택
5. "선호 항공사" + 우측 "전체 12개"
   최대 높이 200px 스크롤 박스 안에 상단 검색 입력 + 2열 체크박스 그리드.
   각 행: 항공사 로고 20px(단색 원형 이니셜 마크로 대체) + 코드 text-xs --text-muted
   + 항공사명 text-sm.
   KE 대한항공(체크) / OZ 아시아나항공 / JL 일본항공(체크) / NH 전일본공수 /
   LJ 진에어 / TW 티웨이항공
   박스 하단 고정 힌트 "모두 해제하면 무관"
6. "좌석 등급" — 라디오 칩 4개: 이코노미(선택) / 프리미엄 / 비즈니스 / 퍼스트
7. "위탁 수하물 (1인당)" — 카운터, 값 1
8. "1인당 가격 상한" — 슬라이더, 값 90만원
   아래 파생 text-xs --text-muted "예산 1,200,000원 중 항공권에 900,000원까지"

## 푸터
좌측 "← 이전", 중앙 "이 단계 건너뛰기"(ghost), 우측 "항공권 찾기 →"(primary)

모션은 1개만: 조건부 슬라이더 등장.
````

## C-5. S3-b 에이전트 검색 스트리밍

> 이 화면이 제품의 차별점이다. **스피너 하나로 대체하면 실패다.**

````text
[S3-b] AI 에이전트가 항공권을 검색하는 동안 보여주는 스트리밍 화면을 만드세요.
공통 셸 동일. 최대 폭 880px 중앙.

## 스트림 패널 (radius 8px, 1px --border, --bg 배경, 그림자 없음)
### 헤더 48px
좌측: lucide Sparkles 16px --primary + "항공권을 찾고 있어요" text-base 500
우측: "중단" ghost 버튼 (xs)
헤더 하단에 2px 진행바 — --primary 인디케이터가 좌우로 왕복하는 불확정 바

### 본문 (패딩 16px, 최대 높이 320px, 자동 하단 스크롤)
1) 섹션 라벨: lucide Brain 14px + "추론" text-sm 500 --text-secondary

2) 추론 문장 — text-base, 단락 간격 12px.
   완료된 문장은 --text 색, 지금 타이핑 중인 문장은 --text-secondary 색이며
   문장 끝에 2px 세로 커서가 깜빡입니다.
   문장 1 (완료):
   "인천(ICN) → 도쿄(NRT/HND), 6월 12일 출발 · 6월 16일 귀국. 성인 2명, 이코노미
   기준으로 찾습니다."
   문장 2 (타이핑 중):
   "직항만, 오전 출발 선호, 1인 90만원 이하. 이 조건에 맞는 항공편만 남깁니다"

3) 도구 호출 카드 2개 (높이 64px, --surface 배경, radius 6px, 1px --border, 간격 8px)
   구조 3행:
   1행: lucide Wrench 14px + 도구명(JetBrains Mono, text-xs, --text-muted)
        + 우측 상태 아이콘
   2행: 한글 라벨 text-sm
   3행: "→ 결과" text-sm --text-muted (완료 시에만)
   카드 A (완료): search_flights / "항공편 데이터베이스 조회 중" /
     "→ 128개 항공편 확인" / 우측 Check 14px --success
   카드 B (진행 중): apply_constraints / "조건 필터 적용 중…" /
     3행 없음 / 우측 Loader2 14px --primary 회전

## 스트림 패널 아래 — 결과 스켈레톤
항공권 카드와 동일한 크기의 스켈레톤 5개 (간격 12px).
각 스켈레톤: 높이 200px, radius 8px, 1px --border,
안쪽에 --surface-active 배경의 블록들(로고 자리 20px 원, 시각 자리 2개,
가격 자리 우상단). shimmer는 왼쪽에서 오른쪽으로 흐르는 밝은 띠 1.4초 루프.
스켈레톤과 실제 카드의 높이가 정확히 같아야 합니다(레이아웃 흔들림 0).

## 푸터
"다음" 버튼은 보이지만 비활성 느낌. hover 시 툴팁 "검색이 끝나면 선택할 수 있어요"

모션은 3개: 타이핑 커서 깜빡임, 도구 카드 등장(200ms 위로 슬라이드),
스켈레톤 shimmer. 그 외 애니메이션을 추가하지 마세요.
````

## C-6. S3-c 항공권 결과와 선택

````text
[S3-c] 항공권 검색 결과 화면을 만드세요. 공통 셸 동일.

## 결과 요약 바 (44px, --primary-subtle 배경)
좌측: Sparkles 14px + "12개 항공권을 찾았어요. 추천은 대한항공 684,000원입니다."
우측: "추론 보기" ghost xs

## 레이아웃: 좌측 필터 사이드바 220px + 우측 결과 리스트
### 필터 사이드바 (sticky, 자체 스크롤, 섹션 간 1px --border-t)
상단: "필터" text-sm 500 + 우측 "초기화" ghost xs
- "가격" — 듀얼 슬라이더 + "28만 – 95만" text-sm
- "경유" — 체크박스 3개. 각 라벨 우측에 개수 text-xs --text-muted
  "직항 (8)" 체크 / "1회 경유 (3)" / "2회 이상 (1)"
- "항공사" — "대한항공 (4)" 체크 / "일본항공 (3)" 체크 / "아시아나항공 (2)"
- "가는 날 출발" — 칩 4개 (오전 선택)
- "오는 날 출발" — 칩 4개 (오후·저녁 선택)
- "총 소요시간" — 슬라이더 "14시간"
- 하단: "조건 다시 설정" secondary 전체 폭

### 정렬 탭 (36px, 하단 2px --primary 인디케이터, 하단 1px --border 전체 폭)
"추천순"(활성) / "최저가" / "최단시간" / "출발 이른순" / "도착 늦은순"
우측 끝에 "12개 중 12개 표시" text-xs --text-muted

### 항공권 카드 3개 (패딩 16px, radius 8px, 1px --border, 간격 12px)
카드 구조:
- 좌상단 태그 배지 / 우상단 가격: text-xl 600 tabular-nums + 아래 "1인당" text-xs --text-muted
- 항공사: 로고 20px(단색 원형 이니셜) + 이름 text-sm 500
- 여정 타임라인 2개 (가는 편 / 오는 편), 각각 한 줄:
  좌측 시각 text-lg 500 tabular-nums → 가운데 1px --border-strong 선 위에
  소요시간 text-xs --text-muted → 우측 도착 시각
  시각 아래에 공항 코드 text-sm --text-muted, 그 아래 날짜 text-xs --text-disabled
  선 아래 중앙에 "직항" text-xs --text-muted
- 메타 행 text-sm --text-muted: "수하물 23kg×1 · 환불 가능 · 2석 남음"
- 상단 1px --border-t 후 에이전트 노트: Sparkles 12px + text-sm --text-secondary
- 우하단 액션: "상세" ghost sm + "선택" primary sm

카드 1 (선택된 상태 — --primary-subtle 배경 + 1px --primary-border + 좌측 3px --primary 바):
  배지 primary "추천" / 684,000원 / KE 대한항공
  가는 편: 09:05 ICN 6.12 목 → 2시간 15분 직항 → 11:20 NRT
  오는 편: 14:30 NRT 6.16 월 → 2시간 30분 직항 → 17:00 ICN
  노트: "오전 도착이라 첫날 일정을 넉넉하게 쓸 수 있어요"
  액션 버튼은 "선택됨" + Check (secondary로 전환)
카드 2: 배지 success "최저가" / 412,000원 / LJ 진에어 / 09:35→12:05, 18:40→21:15
카드 3: 배지 neutral "최단시간" / 736,000원 / NH 전일본공수 / 07:50→10:00, 19:00→21:25

## 하단 선택 바 (56px, sticky, --bg + 상단 1px --border + 위로 향한 미묘한 그림자)
좌측: lucide Plane 16px + "대한항공 KE703 · 왕복 684,000원 (1인) · 총 1,368,000원"
우측: "다음: 숙소 →" primary
(미선택 상태 버전도 만들어 주세요: 좌측이 "항공권을 선택해 주세요" --text-muted)

## 반응형
767px 이하: 사이드바를 상단 "필터 (3)" 버튼 + 바텀시트로 전환. 정렬은 셀렉트로.
카드는 가격을 우상단에서 하단 전체 폭으로 옮기고, 소요시간 라벨을 선 아래로.
하단 선택 바는 2행 72px.

모션은 2개만: 카드 선택 전환(140ms), 정렬 변경 시 재정렬.
````

## C-7. S4 숙소 결과 (지도 스플릿)

````text
[S4] 숙소 검색 결과 화면을 만드세요. 공통 셸 동일.
이 화면부터 좌측 리스트 + 우측 지도 스플릿 구조가 시작됩니다.

## 결과 요약 바 (44px, --primary-subtle)
"18곳을 찾았어요. 호텔 그레이스리 신주쿠가 위치·가격 균형이 좋습니다." + "추론 보기"

## 레이아웃: 좌 52% / 우 48%. 높이는 100dvh에서 헤더(92px)와 푸터(60px)를 뺀 값.
### 좌측
상단 40px 바: "필터 (2)" secondary sm + "추천순 ▾" 셀렉트 + 우측 "18곳" text-sm --text-muted
숙소 카드 3개 (높이 168px, 패딩 12px, radius 8px, 1px --border, 간격 8px)
카드 구조: 좌측 이미지 128×144px + 우측 정보 (갭 12px)
- 이미지: radius 6px, 캐러셀. 좌우 화살표는 hover 시에만 28px 원형(배경 --bg/90).
  하단 중앙에 "1/6" 카운터 (text-xs 흰색 pill)
- 우측 정보:
  1행 태그 배지
  2행 숙소명 text-lg 500
  3행 "★★★★ 호텔 · 신주쿠" text-sm --text-muted
  4행 평점: 8px 원형 점(--primary) + "8.7" text-base 500 + "훌륭해요" text-sm
      + "(2,431)" text-xs --text-muted
  5행 lucide TrainFront 14px + "신주쿠역 도보 6분" text-sm
  6행 어메니티 아이콘 최대 5개 16px --text-muted (Wifi, Croissant, Luggage, Accessibility)
  7행 "무료 취소 가능" text-sm --success
  8행 상단 1px --border-t 후 Sparkles 12px + "관광지 접근성이 가장 좋아요" text-sm
  우하단: 가격 text-lg 600 tabular-nums "180,000원" + "/1박" text-xs --text-muted,
         아래 "총 720,000원" text-sm --text-muted, 그 아래 "선택" primary sm

카드 1: 배지 success "위치 최고" / 호텔 그레이스리 신주쿠 / 8.7 훌륭해요 (2,431) /
        신주쿠역 도보 6분 / 180,000원 · 총 720,000원  ← 선택된 상태
카드 2: 배지 primary "가성비" / 신주쿠 그란벨 호텔 / 8.2 좋아요 (1,180) /
        신주쿠산초메역 도보 4분 / 112,000원 · 총 448,000원
카드 3: 배지 neutral "평점 높음" / 파크 하이엇 도쿄 / 9.2 최고예요 (3,902) /
        도초마에역 도보 8분 / 480,000원 · 총 1,920,000원

### 우측 지도
채도가 낮은 회색 톤 지도(OpenStreetMap positron 스타일). 지도 자체에 색을 넣지 마세요.
- 가격 pill 마커: 높이 24px, --bg 배경 + 1px --border-strong + text-xs 500 tabular-nums.
  예: "18만" "11만" "48만" "22만" "14만" "9만"
- 선택된 마커: --primary 채움 + 흰 글자
- 선택한 관광지: 반투명 회색 8px 점
- 좌하단 범례 (배경 --bg/90 + backdrop-blur, radius 6px, 패딩 8px, text-xs):
  "● 숙소   ○ 가고 싶은 곳"
- 우하단 지도 컨트롤 세로 스택: [+] [−] [전체보기] 각 32×32px,
  --bg + 1px --border + 미묘한 그림자
- 마커 hover 팝오버 1개를 함께 보여주세요 (280px): 썸네일 + 이름 + 평점 + 가격 + "선택"

## 하단 선택 바 (56px)
좌측 BedDouble 16px + "호텔 그레이스리 신주쿠 · 4박 720,000원"
우측 "다음: 가고 싶은 곳 →" primary

## 반응형
768~1023px: 지도 숨기고 리스트 전체 폭 + 상단에 "지도 보기" 버튼
767px 이하: 하단에 세그먼트 토글 [목록 | 지도] 고정(52px, --bg/95 + backdrop-blur).
카드는 세로 구조로: 이미지가 상단 전체 폭 16:9, 정보가 하단.

모션은 2개만: 마커 hover 확대(1.08배), 카드 hover 보더 전환.
지도 마커가 통통 튀는 애니메이션을 넣지 마세요.
````

## C-8. S5 가고 싶은 곳 + 장소 상세 드로어

````text
[S5] 관광지 후보를 훑고 선택하는 화면과, 장소 상세 드로어를 만드세요. 공통 셸 동일.

## 결과 요약 바 (44px, --primary-subtle)
"도쿄에서 40곳을 찾았어요. 관심사에 맞는 곳을 위로 올려뒀습니다." + "추론 보기"

## 레이아웃: 좌 46% / 우 54% 스플릿
### 좌측 상단 컨트롤
1) 검색 입력 36px: Search 16px + placeholder "장소 검색"
2) 카테고리 탭 (가로 스크롤, 각 탭에 개수):
   "전체 40"(활성) / "맛집 7" / "관광 6" / "자연 4" / "미술관 4" / "카페 4" …
3) 우측 정렬 셀렉트 "추천순 ▾" + secondary 버튼 "＋ 링크로 추가"(lucide Link2 아이콘)

### 장소 리스트 항목 3개 (최소 높이 96px, 패딩 12px, radius 8px, 1px --border, 간격 8px)
구조: 좌측 체크박스 16px(상단 정렬) + 썸네일 64×64px radius 6px + 정보
정보 5행:
  1행 장소명 text-base 500 (1줄 말줄임) + 우측 배지 영역
  2행 "카테고리 · 지역" text-sm --text-muted
  3행 별 아이콘 + 평점 text-sm 500 + "(리뷰수)" text-xs --text-muted + " · " + 소요시간
  4행 요약 text-sm --text-secondary, 2줄 말줄임
  5행 메타 칩들 text-xs: 입장료 / 예약 안내 / 휴관 배지 / Sparkles + 에이전트 노트
행 전체가 체크 토글이고, 썸네일과 제목만 상세 드로어를 엽니다.
그래서 썸네일과 제목에 hover 시 밑줄이 생깁니다.
선택된 항목: --primary-subtle 배경 + 1px --primary-border + 좌측 3px --primary 바

항목 1 (선택됨):
  센소지 / 사찰 · 아사쿠사 / ★4.5 (32,841) · 1시간 30분 /
  "628년에 창건된 도쿄에서 가장 오래된 사찰. 붉은 가미나리몬과 나카미세 상점가가
  함께 있습니다." / 칩 "무료" + Sparkles "가족 여행에 적합"
  우측 배지: Star 12px --primary (관심사 일치)
항목 2 (미선택):
  도쿄 스카이트리 / 전망대 · 오시아게 / ★4.4 (58,120) · 2시간 /
  "634m 높이의 전파탑. 350m와 450m 두 개의 전망대가 있습니다." /
  칩 "2,100엔" + warning 칩 "예약 권장"
항목 3 (선택됨):
  도쿄 국립박물관 / 박물관 · 우에노 / ★4.6 (21,004) · 2시간 30분 /
  "일본 최대 규모의 박물관. 국보 89점을 소장하고 있습니다." /
  칩 "1,000엔" + danger 칩 "월 휴관"
  우측 배지: danger "월 휴관"

리스트 하단: "37곳 더" text-sm --text-muted 중앙

### 우측 지도
- 미선택 후보: 10px 원, --bg 채움 + 2px --border-strong 테두리
- 선택됨: 24px 원, --primary 채움 + 2px 흰 테두리 + 중앙에 선택 순번 흰 숫자 text-xs 500
- 숙소: 24×24px 사각(radius 6px), --text-secondary 채움 + BedDouble 흰색 14px
- 좌하단 범례: "● 선택   ○ 후보   ▪ 숙소"
- 우하단 컨트롤 [+] [−] [전체보기]

## 하단 선택 바 (56px)
좌측: Check 16px --primary + "12곳 선택" text-base 500 + " · " +
"예상 소요 18시간 40분" text-sm --text-muted + " · " + "하루 평균 2.4곳"
우측: "모두 해제" ghost xs + "다음: 일정 →" primary

## 장소 상세 드로어 (우측에서 슬라이드, 폭 440px, 전체 높이)
헤더 48px: "센소지" text-xl 600 + 우측 X 아이콘 버튼, 하단 1px --border
본문 (스크롤):
1) 이미지 갤러리 4:3 (330px). 좌우 화살표 hover 시. 하단 중앙 도트 3개 + "1/3"
2) "사찰 · 아사쿠사" text-sm --text-muted
3) 별 4.5 + "리뷰 32,841개" text-sm --text-muted
4) 관심사 칩 3개 (Landmark "역사·문화" / Camera "사진 스팟" / ShoppingBag "쇼핑")
5) 에이전트 노트 카드: --primary-subtle 배경, radius 6px, 패딩 12px,
   Sparkles 14px + "유아차 이동이 편하고 입장료가 없어 가족 여행 첫날에 적합해요" text-sm
6) "소개" 라벨 text-sm 500 + 본문 text-base(15px) --text-secondary 4줄 +
   "출처: 센소지 공식 ↗  도쿄 관광 공식 ↗" text-xs
7) 정보 3열 그리드 (--surface 배경, radius 6px): 
   Clock "1시간 30분" / Ticket "무료" / Calendar "예약 불필요" — 각 아이콘 16px + text-sm
8) "영업시간" 라벨 + 우측 success 배지 "오늘 열림"
   접힌 아코디언: "목요일  06:00 – 17:00" + 우측 "오늘"
   아래 lucide Lightbulb 14px + "이른 아침 07–09시 (관광객 적음)" text-sm --text-secondary
9) "접근성" 라벨 + 아이콘 3개 + 라벨: Accessibility "휠체어 가능" /
   Baby "유아차 가능" / Footprints "계단 적음"
10) "리뷰 32,841개" 라벨 + 리뷰 카드 2개:
   카드 구조: 아바타 24px 원형(--surface 배경 + 이니셜) + 이름 text-sm 500 +
   별 + 날짜 text-xs --text-muted / 본문 text-sm 3줄 / ThumbsUp 12px + "42"
   리뷰 1: (ㅁ) 민지 ★★★★★ 2026.04.18
     "아침 7시에 갔더니 사람이 거의 없어서 사진을 마음껏 찍었어요. 8시 넘으니 단체
     관광객이 몰려오기 시작했습니다."
   리뷰 2: (D) Daniel ★★★★☆ 2026.03.02
     "아름다운 사찰이지만 오후에는 매우 혼잡합니다. 상점가는 기념품 사기에 좋아요."
     + "원문 보기 ▾" text-xs
   아래 "리뷰 더 보기" secondary 전체 폭
11) "위치" 라벨 + 미니 지도 160px(상호작용 없음) +
   주소 text-sm "2-3-1 Asakusa, Taito City, Tokyo" + "복사" ghost xs +
   "구글 지도에서 보기 ↗" text-sm
12) "근처에 있는 곳" 라벨 + 리스트 2개: "나카미세 상점가 · 도보 2분"
푸터 60px (상단 1px --border): 전체 폭 primary lg 버튼 "＋ 가고 싶은 곳에 추가"

## 반응형
767px 이하: 하단 [목록 | 지도] 세그먼트. 드로어는 바텀시트(60% 스냅, 드래그로 92%).
리스트 항목은 썸네일 48px, 요약 1줄, 메타 칩 2개까지.

모션은 3개: 드로어 슬라이드(240ms), 체크 그리기(200ms), 마커 확대(hover).
````

## C-9. S6 일정과 지도 (핵심 화면)

````text
[S6] 일정 편집 화면을 만드세요. 이 앱의 가장 중요한 화면입니다. 공통 셸 동일.

## 결과 요약 바 (44px, --primary-subtle)
"5일 일정을 완성했어요. 총 이동 시간은 4시간 12분입니다." + "추론 보기"

## 레이아웃: 좌 46% / 우 54% 스플릿
### 좌측 상단 (36px)
탭 3개 "일정"(활성) / "지출" / "준비물" — 하단 2px --primary 인디케이터
우측에 secondary sm 버튼 "경로 최적화" (lucide Wand2 아이콘)

### 일자 섹션 헤더 (56px, 스크롤 시 상단에 붙음)
1행: ChevronDown 16px + 10px 원형 일자 색 점(--day-1) + "Day 1" text-base 600 +
     "6/12 목" text-base --text-secondary + "아사쿠사 & 스카이트리" text-base --text-muted
     + 우측 더보기 아이콘
2행: "4곳 · 활동 7시간 20분 · 이동 52분" text-xs --text-muted

### 일정 항목 카드 (패딩 12px, radius 8px, 1px --border, --bg)
1행 (40px): 드래그 핸들(GripVertical 16px --text-disabled, hover 시에만 보임) +
  순번 배지(20px 원, --day-1 채움, 흰 숫자 text-xs 500) +
  시각 text-base 500 tabular-nums + 제목 text-base 500 +
  우측 검증 배지 + 더보기 아이콘
2행: 썸네일 40×40px radius 6px + "카테고리 · 체류시간" text-sm --text-muted
3행: 평점 + 입장료 text-sm --text-muted
4행: Sparkles 12px + 배치 이유 text-xs --text-secondary

### 이동 구간 커넥터 (높이 28px, 카드 사이)
순번 배지 중심선에 맞춘 세로 점선(1px dashed --border) +
lucide Footprints 14px + "12분" text-xs 500 --text-secondary +
" · " + TrainFront 14px + "6분" text-xs --text-muted +
우측에 "경로보기" ghost xs (hover 시에만)

### Day 1의 실제 내용 (이 순서로)
1. Plane 아이콘 항목: "11:20  나리타 공항 도착" / 2행 "KE703 · 공항→숙소 1시간 20분"
   (순번 배지 없음, 대신 --surface 배경 원에 Plane 아이콘 12px)
   ↓ 커넥터: TrainFront "78분" · Car "62분"
2. BedDouble 아이콘 항목: "14:00  호텔 그레이스리 체크인"
   ↓ 커넥터: Footprints "8분"
3. 순번 ① "15:00  센소지" / "사찰 · 1시간 30분" / "★4.5 · 무료" /
   Sparkles "오후 햇빛이 좋아요" / 검증 배지 CircleCheck 12px --success
   ↓ 커넥터: Footprints "12분" · TrainFront "6분" + "경로보기"
4. 순번 ② "17:00  도쿄 스카이트리" / "전망대 · 2시간" / "★4.4 · 2,100엔" /
   검증 배지 TriangleAlert 12px --warning / 4행에 warning 텍스트 "예산 초과 가능"
   ↓ 커넥터: Footprints "4분"
5. UtensilsCrossed 아이콘 항목: "19:30  저녁 (자유)"
그 아래 ghost 버튼 "＋ 장소 추가"

### 접힌 일자 섹션 2개
"▸ ● Day 2  6/13 금  시부야 & 하라주쿠 / 5곳 · 활동 8시간 10분 · 이동 1시간 8분"
"▸ ● Day 3  6/14 토  우에노 & 야네센 / 4곳 · 활동 6시간 40분 · 이동 44분"
(각각 --day-2, --day-3 색 점)

### 미배치 장소 패널 (리스트 맨 아래, --warning-subtle 배경, radius 8px)
"아직 배치하지 않은 곳 2개" text-sm 500 + 접기 화살표
행 2개: "하라주쿠 다케시타 거리" + 우측 "Day에 추가 ▾" ghost xs
       "오다이바 해변공원" + 우측 "Day에 추가 ▾"

### 우측 지도
채도 낮은 회색 지도. 우리가 올리는 마커와 경로만 색을 갖습니다.
- 번호 마커: 28px 원, 일자 색 채움 + 2px 흰 테두리 + 흰 숫자 text-xs 500
- 숙소 마커: 26×26px 사각(radius 6px), --text-secondary + BedDouble 흰색
- 공항 마커: 26px 원, --text-muted + Plane 흰색
- 경로 라인: 3px, 일자 색, 불투명도 0.75, 끝이 둥근 선.
  도보 구간은 점선, 대중교통·차량은 실선
- 좌하단 일자 범례: "● Day1  ○ Day2  ○ Day3  ○ Day4  ○ Day5" (Day1만 채워짐)
- 우하단 컨트롤 [+] [−] [전체보기]
- 마커 hover 팝오버 1개 (240px): "② 도쿄 스카이트리 / 전망대 · 17:00–19:00"

## 하단 푸터 (60px)
좌측 "← 가고 싶은 곳" secondary / 우측 "일정 검증 →" primary

## 드래그 중 상태도 함께 만들어 주세요
- 원래 자리: 같은 높이의 점선 플레이스홀더(1px dashed --primary-border,
  --primary-subtle 배경)
- 커서에 붙어 있는 카드: 1.02배 확대 + 1.5도 기울임 + 미묘한 그림자 +
  1px --primary 링. 배경은 불투명.
- 드롭 대상 일자 섹션: 1px --primary-border 링

## 반응형
767px 이하: 하단 [목록 | 지도] 세그먼트. 카드는 썸네일 32px, 배치 이유 숨김,
드래그 핸들 항상 표시. 커넥터의 대안 수단 숨김. 최적화 버튼은 더보기 메뉴로.

모션은 3개만: 순번 숫자 롤링(순서 변경 시), 이동시간 숫자 카운트업,
일자 섹션 접기/펼치기. 그 외를 추가하지 마세요.
````

## C-10. S7 검증 (실시간 추론 + 리포트)

````text
[S7] 일정 검증 화면을 만드세요. 공통 셸 동일.
두 가지 상태를 각각 만들어 주세요: (1) 검증 진행 중, (2) 검증 완료 리포트.

═══════════════════════════════
## 상태 1 — 검증 진행 중 (좌 46% / 우 54%)

### 좌측 — 체크리스트
상단: "일정을 검증하고 있어요" text-xl 600 +
4px 진행바(60% 채움) + 우측 "6/10" text-xs --text-muted

체크리스트 컨테이너 (radius 8px, 1px --border, 행 사이 1px --border-t)
각 행 48px(메시지 있으면 auto):
좌측 상태 아이콘 16px + 규칙 라벨 text-base + 우측 결과 배지
문제가 있는 행은 2행에 메시지 text-sm --text-muted

1. CircleCheck --success / "영업시간 · 휴관일" / danger 배지 "충돌 1"
   2행 "Day 4 도쿄 국립박물관 월요일 휴관"
2. CircleCheck --success / "이동 시간 실현성" / warning 배지 "주의 1"
   2행 "Day 3 이동 시간이 촉박해요"
3. CircleCheck --success / "항공 도착 · 출발 여유" / success 배지 "정상"
4. CircleCheck --success / "숙소 체크인 · 체크아웃" / success 배지 "정상"
5. CircleCheck --success / "하루 일정량" / warning 배지 "주의 1"
   2행 "Day 3 활동 11시간 20분"
6. Loader2 --primary 회전 / "예산" / primary 배지 "검사 중…"
   (행 배경을 --primary-subtle로 아주 살짝)
7. Circle --text-disabled / "접근성" / 배지 없음, 우측에 "대기" text-xs --text-disabled
8. Circle / "관심사 반영" / "대기"
9. Circle / "사전 예약 필요" / "대기"
10. Circle / "시즌 · 날씨" / "대기"

### 우측 — 추론 콘솔 (radius 8px, 1px --border, 배경 oklch(97% 0.001 286))
헤더 40px: Brain 14px + "추론 과정" text-sm 500 + 우측 "중단" ghost xs
본문 (패딩 12px, 최대 높이 520px, 자동 하단 스크롤):
- 자연어 추론은 일반 산세리프 text-sm --text-secondary 단락
- 로그는 JetBrains Mono text-xs, 행간 20px

내용 (이 순서로):
[산세리프] "5일 일정, 총 17개 방문지를 10개 항목으로 점검합니다."
[모노 · text-sm 500 --text-secondary] "[V1] 영업시간 · 휴관일"
[모노 --text-muted] "> 17개 장소의 요일별 영업시간 조회"
[모노 --text-muted] "> Day 2 (6/13 금) 확인 완료"
[모노 --text-muted] "> Day 3 (6/14 토) 확인 완료"
[모노 --warning] "⚠ 도쿄 국립박물관: 월요일 휴관"
[모노 --warning] "  방문 예정 6/15(월) 11:00"
[모노 --text-secondary 500] "→ 충돌 1건"
[산세리프] "Day 4의 도쿄 국립박물관이 월요일 휴관입니다. 근처 대안이나 다른 날
이동을 제안할게요."
[도구 카드] Wrench + check_budget / "예산 대비 비용 계산 중…" / Loader2 회전
[타이핑 커서] 2px 세로 커서 깜빡임

═══════════════════════════════
## 상태 2 — 검증 완료 리포트 (단일 컬럼, 최대 폭 880px 중앙)

### 스코어카드 (radius 8px, 1px --border, 패딩 20px, --danger-subtle 배경)
1행: "검증을 마쳤어요" text-xl 600 + 우측 "추론 다시 보기" ghost
2행: 카운터 3개 가로 배치. 각각 숫자 text-3xl(32px) 600 tabular-nums + 라벨 text-sm
  - "7" --success / "정상"
  - "2" --warning / "주의"
  - "1" --danger / "충돌"
  우측 끝에 "검사 10개 · 12.4초 소요" text-xs --text-muted
3행: "충돌 1건을 해결하면 일정이 완성돼요." text-base +
  우측 primary 버튼 "자동 수정 모두 적용"

### "해결해야 할 것" 라벨 (text-base 500) 아래 이슈 카드 3개
카드 (radius 8px, 1px --border, 패딩 16px, 좌측 3px 심각도 색 border-l)
구조:
- 헤더: 심각도 배지 + 규칙 라벨 text-sm 500 +
  우측 규칙 ID "[V1]" JetBrains Mono text-xs --text-disabled
- 제목 text-base 500
- 대상 text-sm --text-muted
- 설명 text-sm --text-secondary
- "근거" 라벨 text-sm 500 + 불릿 리스트 text-sm --text-muted
- 제안 카드: --primary-subtle 배경, radius 6px, 패딩 12px.
  Sparkles 12px + "제안" text-sm 500 + 요약 → 이유 text-sm --text-secondary →
  영향 text-xs --text-muted
- 액션 3개: "일정에서 보기" secondary / "무시하기" ghost / "이 수정 적용" primary

이슈 1 (좌측 border --danger):
  배지 danger "충돌" / "영업시간 · 휴관일" / [V1]
  제목 "도쿄 국립박물관이 방문일에 휴관입니다"
  대상 "Day 4 · 6/15(월) 11:00 방문 예정"
  설명 "이 박물관은 매주 월요일 휴관입니다."
  근거: "영업시간: 화–일 09:30–17:00, 월요일 휴관" / "6월 15일은 월요일"
  제안: "Day 3(6/14 토) 10:30으로 옮기기" /
    "Day 3에 우에노 공원이 있어 같은 지역이라 이동이 늘지 않아요." / "이동시간 +4분"

이슈 2 (좌측 border --warning):
  배지 warning "주의" / "하루 일정량" / [V5]
  제목 "Day 3 활동 시간이 페이스보다 길어요"
  대상 "Day 3 · 6/14(토)"
  설명 "'적당히' 페이스는 하루 3–4곳인데 6곳이 배치되어 있습니다."
  근거: "활동 11시간 20분 (기준 11시간)" / "이동 1시간 22분"
  제안: "마지막 방문지를 Day 4로 옮기기" / "Day 4가 4곳으로 여유가 있어요." /
    "Day 3 활동 9시간 10분으로 감소"

이슈 3 (좌측 border --warning):
  배지 warning "주의" / "사전 예약 필요" / [V9]
  제목 "예약이 필요한 곳이 2군데 있어요"
  대상 "Day 3 팀랩 플래닛 · Day 5 도쿄 디즈니시"
  근거: "팀랩 플래닛: 날짜 지정 예약 필수" / "도쿄 디즈니시: 파크 티켓 사전 구매 권장"
  액션은 "준비물에 추가하기" primary 하나만

### 맨 아래 접힌 섹션
"통과한 항목 7개" text-base 500 + ChevronDown

### 푸터 (60px)
좌측 "← 일정 수정" secondary / 우측 "다시 검증" ghost + "일정 공유하기 →" primary

## 반응형
767px 이하: 상태 1은 콘솔을 체크리스트 아래로 세로 배치(최대 높이 320px).
이슈 카드의 액션 버튼 3개는 2행으로(주 액션이 전체 폭 위, 보조 2개 아래).

모션은 3개만: 상태 아이콘 확정(체크 그리기 200ms), 카운터 숫자 카운트업(400ms),
타이핑 커서. 컨페티나 축하 애니메이션을 넣지 마세요.
````

---

# D. 컴포넌트 프롬프트

화면 전체가 아니라 컴포넌트 하나를 만들 때 쓴다. **B를 앞에 붙이는 것은 동일하다.**

컴포넌트 프롬프트에는 공통 요구가 하나 더 붙는다.

````text
[모든 컴포넌트 프롬프트에 공통 추가]

## 8개 상태를 전부 코드로 내세요
default / hover / focus-visible / active / disabled / loading / error / success
각 상태를 강제로 볼 수 있게 클래스도 함께 지원하세요:
  .is-hover, .is-focus, .is-active  (실제 의사 클래스와 OR 조건으로)
  예: .btn:hover, .btn.is-hover { ... }

## 미리보기 파일을 함께 만드세요
<컴포넌트명>.preview.tsx — 8개 상태를 세로로 쌓고 각 행에 상태 이름을 라벨로 붙인
독립 페이지. 프로덕션 코드가 아니며 확인 후 삭제할 용도입니다.

## 파일 맨 위 주석
/* JustGO · component: <타입> · states: default·hover·focus·active·disabled·loading·error·success */
````

## D-1. 버튼 세트

````text
버튼 컴포넌트를 만드세요.

## variant 6종
- primary   : --primary 배경 → hover --primary-hover / 글자 --primary-fg / 보더 없음
              (화면당 1개만 쓰는 주 행동)
- secondary : --bg 배경 → hover --surface-hover / 글자 --text / 1px --border-strong
- ghost     : 투명 → hover --surface-hover / 글자 --text-secondary → hover --text
- subtle    : --surface 배경 → hover --surface-hover / 글자 --text / 보더 없음
- danger    : 투명 → hover --danger-subtle / 글자 --danger / 보더 없음
- link      : 배경 없음 / 글자 --primary / hover 시 밑줄

## size 5종
- xs   : 높이 26px, 패딩 0 8px,  text-xs 500,  아이콘 14px
- sm   : 높이 32px, 패딩 0 10px, text-sm 500,  아이콘 16px
- md   : 높이 36px, 패딩 0 14px, text-base 500, 아이콘 16px  ← 기본
- lg   : 높이 44px, 패딩 0 20px, text-md 500,  아이콘 18px
- icon : 32×32px 정사각, 아이콘 16px

## 공통
- radius 6px, transition은 색상만 80ms
- active 시 scale(0.98)
- focus-visible: 2px 링 --primary 40% + offset 2px, 즉시 표시
- disabled: opacity 0.5 + cursor not-allowed
- loading: 좌측에 16px 스피너 추가 + 라벨 유지. **버튼 폭이 변하면 안 됩니다.**
- error: 1px --danger 보더 + 아이콘 CircleAlert 16px (라벨은 유지)
- success: 아이콘이 Check 16px --success로 잠깐 바뀜 (1.5초 후 원복)
- 아이콘만 있는 버튼은 aria-label 필수
- 라벨이 두 줄로 줄바꿈되지 않게 white-space: nowrap

한국어 라벨 예: "다음: 숙소" / "항공권 찾기" / "이 수정 적용" / "되돌리기" / "모두 해제"
````

## D-2. 선택 칩 (ChipMultiSelect)

````text
다중 선택 칩 컴포넌트를 만드세요. 관심 카테고리·어메니티·시간대에 쓰입니다.

## 규격
- 높이 32px, 패딩 0 12px, radius 9999px, text-sm 500
- 좌측에 lucide 아이콘 16px (선택 사항) + 6px 갭
- 미선택: --bg 배경 / 1px --border / --text-secondary
- hover:  --surface-hover / 1px --border-strong
- 선택:   --primary-subtle / 1px --primary-border / --primary 글자
          + 좌측에 Check 14px
- disabled: opacity 0.5
- **중요**: 선택 시 칩 폭이 변하면 줄바꿈이 흔들립니다.
  체크 아이콘 자리를 미선택 상태에서도 opacity 0으로 확보하세요.

## 그룹
- flex flex-wrap gap-2
- role="group", 각 칩은 role="checkbox" + aria-checked
- Tab으로 그룹 진입 → ←→ 로 이동 → Space로 토글
- 그룹 라벨 우측에 카운터: "{n}개 선택" (0개면 "1개 이상 선택해 주세요" --warning)

## 목 데이터 (관심 카테고리 10개, lucide 아이콘)
UtensilsCrossed 맛집 / Coffee 카페·디저트 / Trees 자연·공원 /
Building2 미술관·박물관 / Landmark 역사·문화 / ShoppingBag 쇼핑 /
Moon 야경·나이트라이프 / Ticket 액티비티·테마파크 / Camera 사진 스팟 / Waves 휴양·온천

이모지를 쓰지 마세요. lucide 아이콘만 사용하세요.
````

## D-3. 지도 마커 세트

````text
지도 위에 올리는 마커 컴포넌트들을 만드세요. MapLibre GL의 HTML 마커로 구현합니다.
지도 타일은 채도가 낮은 회색 톤이고, 색은 마커와 경로만 갖습니다.

## 1) 번호 마커 (일정 항목)
- 28px 원, 일자 색 채움(--day-1 ~ --day-6 순환), 2px 흰 테두리
- 중앙에 순번 흰 숫자 text-xs 500
- 그림자: 0 1px 3px rgb(0 0 0 / 0.3)
- hover: scale(1.18) + z-index 최상위
- 비활성 일자(다른 날 강조 중): opacity 0.35 + 크기 20px
- **색만으로 일자를 구분하지 않습니다. 항상 숫자를 함께 표시하세요.**

## 2) 후보 마커 (S5 미선택 장소)
- 10px 원, --bg 채움 + 2px --border-strong 테두리
- hover: scale(1.25)

## 3) 선택 마커 (S5 선택된 장소)
- 24px 원, --primary 채움 + 2px 흰 테두리 + 중앙에 선택 순번 흰 숫자 text-xs 500

## 4) 가격 pill 마커 (S4 숙소)
- 높이 24px, 패딩 0 8px, radius 9999px
- --bg 배경 + 1px --border-strong + text-xs 500 tabular-nums
- 라벨 예: "18만" "11만" "48만"
- hover: 1px --primary-border + scale(1.08)
- 선택: --primary 채움 + 흰 글자

## 5) 숙소 마커
- 26×26px 사각(radius 6px), --text-secondary 채움, BedDouble 흰색 14px

## 6) 공항 마커
- 26px 원, --text-muted 채움, Plane 흰색 14px

## 7) 클러스터 마커
- 32px 원, --surface 채움 + 1px --border-strong + 개수 text-xs 500 --text

## 8) 마커 팝오버 (240~280px)
- --bg 배경, 1px --border, radius 8px, 미묘한 그림자, 화살표 있음
- 구조: 썸네일(있으면) + 제목 text-base 500 + 메타 text-sm --text-muted + 액션 버튼

## 9) 경로 라인 (지도 레이어)
- 폭 3px, 일자 색, opacity 0.75, line-cap round
- 도보 구간: 점선 (dasharray [1,2])
- 대중교통·차량: 실선
- 비활성 일자: 폭 2px + --text-disabled 색

## 10) 일자 범례
- 좌하단, --bg/90 배경 + backdrop-blur, radius 6px, 패딩 8px, text-xs
- "● Day1  ○ Day2  ○ Day3" 형태. 활성 일자만 채워진 점
- 클릭 시 해당 일자만 강조

## 접근성
모든 마커는 tabindex="0" + role="button" + aria-label
예: aria-label="Day 1, 1번, 센소지, 15시 00분부터 1시간 30분"

마커에 바운스·펄스 애니메이션을 넣지 마세요. hover 확대만 허용합니다.
````

## D-4. 이동 구간 커넥터

````text
일정 항목 사이에 들어가는 이동 시간 표시 컴포넌트를 만드세요.

## 기본 상태
- 높이 28px, 카드 사이에 배치
- 좌측: 순번 배지 중심선과 정렬된 세로 점선 (1px dashed --border, 높이 전체)
- 그 우측에 인라인으로:
  주 수단 아이콘 14px + "{n}분" text-xs 500 --text-secondary
  " · " + 대안 수단 아이콘 14px + "{n}분" text-xs --text-muted (최대 1개)
  거리가 500m 이상이면 " · 1.2km" text-xs --text-muted
- 맨 우측: "경로보기" ghost xs — **hover 시에만 표시**

## 수단 아이콘 (lucide)
도보 Footprints / 대중교통 TrainFront / 택시·차량 Car / 자전거 Bike

## 상태 변형
- 일반: 위 기본
- 이동 과다 (60분 초과): 아이콘과 텍스트를 --warning 색으로 +
  hover 툴팁 "이동이 1시간을 넘어요"
- 시간 부족 (검증 충돌): --danger 색 + 앞에 TriangleAlert 12px +
  툴팁 "다음 일정 시작까지 시간이 부족해요"
- 값 갱신 직후: 숫자가 카운트업(300ms)되고 배경이 아주 짧게 플래시

## 예시 3개를 모두 만들어 주세요
1. Footprints 12분 · TrainFront 6분 + "경로보기"
2. TrainFront 78분 · Car 62분  (warning 색)
3. Footprints 4분
````

## D-5. 에이전트 스트림 패널

````text
AI 에이전트의 작업 과정을 실시간으로 보여주는 패널을 만드세요.
S3(항공권), S4(숙소), S5(장소 발견), S6(일정 생성)에서 공용으로 씁니다.

## 컨테이너
radius 8px, 1px --border, --bg 배경. 그림자 없음.

## 헤더 (48px)
좌측: Sparkles 16px --primary + 상태 텍스트 text-base 500
우측: "중단" ghost xs
하단에 2px 진행바.
- progress 값이 있으면: --primary 채움 + 폭 트랜지션 200ms
- 값이 없으면: --primary 인디케이터가 좌우로 왕복하는 불확정 바 (1.4초 루프)

## 본문 (패딩 16px, 최대 높이 320px, overflow-y auto)
새 콘텐츠가 도착하면 자동으로 하단 스크롤.
사용자가 위로 스크롤하면 자동 스크롤을 멈추고 우하단에 "최신으로" 버튼을 띄웁니다.

### 1) 섹션 라벨
Brain 14px + "추론" text-sm 500 --text-secondary

### 2) 추론 문장 (ThoughtStream)
- text-base, 단락 간격 12px
- 완료된 문장: --text 색
- 타이핑 중 문장: --text-secondary 색 + 문장 끝에 2px 세로 커서가 1초 주기로 깜빡임
- 타이핑 속도는 초당 42자, 문장 끝(마침표·"요"·"다")에서 120ms 멈춤
- prefers-reduced-motion에서는 타이핑 없이 문장 단위로 즉시 표시(순서는 유지)

### 3) 도구 호출 카드 (ToolCallCard)
높이 64px, --surface 배경, radius 6px, 1px --border, 카드 간격 8px
3행 구조:
  1행: Wrench 14px + 도구명(JetBrains Mono text-xs --text-muted) + 우측 상태 아이콘
  2행: 한글 라벨 text-sm
  3행: "→ {결과}" text-sm --text-muted (완료 시에만)
상태 아이콘: 진행 중 Loader2 14px --primary 회전 / 완료 Check 14px --success /
실패 X 14px --danger
등장: 200ms 위로 슬라이드 + 페이드

## 상태 변형 4개를 모두 만들어 주세요
1. 진행 중 (위 구조)
2. 완료 — 헤더가 결과 요약으로 바뀌고 패널이 접힘. 접힌 헤더에 "추론 보기" 버튼
3. 중단됨 — 배너 "3개까지 찾았어요. 다시 찾을까요?" + "다시 찾기" 버튼
4. 실패 — CircleAlert 40px --danger + 제목 "검색 결과를 가져오지 못했어요" +
   설명 "네트워크 상태를 확인하고 다시 시도해 주세요" +
   "다시 시도" primary + "이 단계 건너뛰기" secondary
   (이미 도착한 부분 결과는 지우지 말고 아래에 그대로 둡니다)

## 접근성
패널은 role="log" aria-live="polite" aria-atomic="false".
도구 카드의 상태 변화는 aria-live에서 제외하고, 완료된 결과만 알립니다.

모션은 3개만: 타이핑 커서, 도구 카드 등장, 진행바. 그 외를 넣지 마세요.
````

## D-6. 검증 상태 배지와 체크리스트 행

````text
검증 결과를 표시하는 배지와 체크리스트 행을 만드세요.

## 원칙 — 3중 인코딩
색만으로 상태를 전달하지 않습니다. **색 + 아이콘 + 텍스트**를 항상 함께 씁니다.

## 상태 6종
| 상태     | 색             | lucide 아이콘        | 텍스트    |
|---------|---------------|--------------------|----------|
| 대기     | --text-disabled | Circle             | 대기      |
| 검사 중  | --primary      | Loader2 (회전)      | 검사 중…  |
| 통과     | --success      | CircleCheck        | 정상      |
| 주의     | --warning      | TriangleAlert      | 주의 {n}  |
| 충돌     | --danger       | CircleX            | 충돌 {n}  |
| 해당 없음 | --text-muted   | MinusCircle        | 해당 없음  |

## 배지 규격
높이 20px, 패딩 0 6px, radius 4px, text-xs 500,
배경은 각 상태의 -subtle, 보더 1px는 각 상태 색의 옅은 값, 글자는 상태 색.
아이콘 12px + 4px 갭.

## 작은 배지 (일정 카드에 붙는 것)
아이콘만 12px. 툴팁으로 이유를 표시.
검증이 낡은 상태(일정이 바뀐 뒤): 아이콘에 취소선 + opacity 0.5 +
툴팁 "일정이 바뀌어 재검증이 필요해요"

## 체크리스트 행
- 높이 48px (메시지가 있으면 auto, 최대 2행)
- 좌측 상태 아이콘 16px + 규칙 라벨 text-base + 우측 결과 배지
- 2행에 메시지 text-sm --text-muted (문제가 있을 때만)
- 검사 중인 행: 배경을 --primary-subtle로 아주 살짝
- 행 사이 1px --border-t, 컨테이너는 radius 8px + 1px --border
- 대기 → 검사 중 → 결과 확정의 3단 전이.
  확정 순간에 아이콘이 체크를 그리는 애니메이션(200ms) + 0.8→1 스케일

## 10개 규칙 라벨 (이 순서)
영업시간 · 휴관일 / 이동 시간 실현성 / 항공 도착 · 출발 여유 /
숙소 체크인 · 체크아웃 / 하루 일정량 / 예산 / 접근성 / 관심사 반영 /
사전 예약 필요 / 시즌 · 날씨

## 접근성
컨테이너 role="list", 각 행 role="listitem".
결과 확정만 aria-live="polite"로 알림: "영업시간 · 휴관일: 충돌 1건"
진행률은 role="progressbar" + aria-valuetext="10개 중 6개 검사 완료"
````

## D-7. 단계 진행바 (StepProgressBar)

````text
위저드 단계 진행바를 만드세요. 높이 40px, sticky, 하단 1px --border.

## 단계 7개
①도시 ②여행 스타일 ③항공권 ④숙소 ⑤가고 싶은 곳 ⑥일정 ⑦검증

## 상태 4종
- 완료:   20px 원에 Check 12px (--success 색) + 라벨 text-base --text-secondary,
          클릭 가능
- 현재:   20px 원 --primary 채움 + 흰 숫자 text-xs 500 + 라벨 text-base 600 --text
          + 라벨 하단에 2px --primary 인디케이터
- 이후:   20px 원 1px --border 보더만 + 숫자 --text-muted + 라벨 --text-muted,
          조건 충족 시 클릭 가능
- 건너뜀: 숫자 없이 원에 Minus 아이콘 + 라벨에 취소선 + --text-disabled,
          클릭 불가, 툴팁 "건너뜀"

## 연결선
단계 사이 1px --border 수평선. 완료된 구간은 --success.

## 레이아웃
전체 폭을 균등 분할하지 마세요. 좌측 정렬 + 라벨 폭에 맞춥니다.
넘치면 가로 스크롤(스크롤바 숨김) + 현재 단계가 자동으로 보이게 스크롤.

## 반응형
767px 이하: 라벨을 숨기고 점만 표시 (● ● ● ○ ○ ○ ○) +
우측에 현재 위치 텍스트 "3/7 항공권" text-sm

## 예시 3개를 만들어 주세요
1. 1단계 진행 중 (모두 이후 상태)
2. 3단계 진행 중 (1·2 완료)
3. 5단계 진행 중, 항공권·숙소를 건너뛴 경우 (③④가 취소선)

## 접근성
nav 요소 + aria-label="여행 계획 단계".
현재 단계에 aria-current="step".
클릭 불가한 단계는 button disabled + aria-disabled + 이유를 툴팁으로.
````

## D-8. 자동 수정 diff 다이얼로그

````text
검증 이슈의 자동 수정을 적용하기 전에 보여주는 diff 다이얼로그를 만드세요.
폭 560px, radius 12px, 1px --border, 미묘한 그림자, 배경 오버레이는 검정 40%.

## 구조
### 헤더 (48px, 하단 1px --border)
"이렇게 수정할까요?" text-xl 600 + 우측 X 아이콘 버튼

### 본문 (패딩 20px)
1) 이슈 제목: 심각도 아이콘 12px + "영업시간 충돌 해결" text-base 500

2) diff 블록 (radius 6px, 1px --border, 2행)
   - 이전 행: --danger-subtle 배경, 패딩 12px
     "이전" 라벨 text-xs --text-muted (폭 40px) +
     "Day 4 · 6/15(월) 11:00  도쿄 국립박물관" text-sm
     (변경되는 부분만 500 굵기, 나머지 --text-muted)
   - 이후 행: --success-subtle 배경
     "이후" 라벨 + "Day 3 · 6/14(토) 10:30  도쿄 국립박물관"

3) "함께 바뀌는 것" 라벨 text-sm 500 + 불릿 리스트 text-sm --text-secondary
   · "Day 3의 우에노 공원이 13:00 → 13:40으로 밀립니다"
   · "Day 3 이동 시간 54분 → 58분"
   · "Day 4에 2시간 30분 여유가 생깁니다"

4) 부작용 경고 (있을 때만): TriangleAlert 14px --warning +
   "Day 4가 비어 보일 수 있어요. 미배치 장소를 넣어 보세요." text-sm --warning

### 푸터 (60px, 상단 1px --border)
우측 정렬: "취소" secondary + "적용하고 다시 검증" primary

## 일괄 모드 변형도 만들어 주세요
여러 이슈를 한 번에 적용할 때:
- 이슈별로 접이식 섹션 + 각 섹션 헤더에 체크박스(해제 가능)
- 푸터 좌측에 "3건 중 2건 적용" text-sm --text-muted

## 반응형
767px 이하: 바텀시트로 전환(92% 높이). 푸터 버튼은 세로 스택(주 액션이 위).

## 접근성
role="dialog" aria-modal="true" aria-labelledby.
열리면 제목에 포커스, Esc로 닫기, 닫으면 트리거 버튼으로 포커스 복귀.
포커스 트랩 필수.
````

---

# E. 리파인 프롬프트

1차 결과를 받은 뒤 교정용으로 쓴다. **한 번에 하나씩** 적용한다.

## E-1. AI 티 제거 (가장 자주 쓰게 될 프롬프트)

````text
방금 만든 화면을 아래 기준으로 점검하고 위반 사항을 모두 고쳐 주세요.
고친 항목을 목록으로 알려 주세요.

□ 그라데이션 배경이 있는가 → 단색으로 (이미지 위 가독성 오버레이만 예외)
□ 보라~파랑 그라데이션, 네온, 글로우, 글래스모피즘이 있는가 → 제거
□ 브랜드 색을 --primary 외에 쓴 곳이 있는가 → --primary 하나로
□ 이모지를 기능 아이콘으로 썼는가 → lucide 아이콘으로 (국기 이모지만 예외)
□ 제목이 이탤릭인가 → 로만체로
□ 라벨을 uppercase로 변환했는가 → 원래 대소문자로
□ 섹션 위에 번호 말머리(01 · FEATURES, STEP 2)를 붙였는가 → 제거
□ 말머리를 왼쪽 열, 제목을 오른쪽 열에 둔 2단 헤더가 있는가
  → 제목 바로 위에 같은 열로 쌓기
□ 가짜 브라우저 창(주소창 + 점 3개), 가짜 휴대폰 목업, 가짜 코드 창이 있는가 → 제거
□ 만들어 낸 숫자("1만 명이 사용", "3배 빠른", "만족도 98%")가 있는가
  → 삭제하고 그 자리를 다른 구조로
□ 존재하지 않는 후기·로고·수상 배지가 있는가 → 제거
□ radius가 16px 이상인 요소가 있는가 → 6/8/12px로 (pill 버튼만 예외)
□ 카드에 그림자를 넣었는가 → 1px 보더로 대체
□ 글자 굵기가 700 이상이거나 400 미만인 곳이 있는가 → 400/500/600만
□ 색·폰트 값을 파일 안에 직접 썼는가 → 토큰 이름으로 참조
□ hover 트랜지션이 200ms를 넘는가 → 80~140ms로
□ 바운스·오버슈트 이징을 썼는가 → cubic-bezier(0.2,0,0,1)로
□ 한 화면의 모션 종류가 3개를 넘는가 → 정보 전달에 필수인 것만 남기고 삭제
□ 로딩을 스피너 하나로 처리했는가 → 무엇을 하는지 문장으로 보여주기
□ 변하는 숫자에 tabular-nums를 안 썼는가 → 적용
````

## E-2. 밀도 올리기

````text
이 화면이 너무 헐렁합니다. Linear / Notion 수준의 정보 밀도로 조정해 주세요.

- 리스트 행 높이를 36~40px로 줄이세요
- 카드 패딩을 12~16px로 줄이세요
- 본문 글자 크기를 14px로 맞추세요 (16px을 쓰고 있다면 내리세요)
- 섹션 간 여백을 32px 이하로 줄이세요
- 위계는 여백을 늘려서 만들지 말고, 1px 보더선과 글자 굵기(500 vs 400)로 만드세요
- 빈 공간을 채우려고 요소를 추가하지는 마세요. 같은 정보를 더 좁게 담으세요
- 화면에 담기는 항목 수가 기존보다 최소 1.5배 늘어야 합니다
````

## E-3. 모바일 대응 강제

````text
375px 폭에서 이 화면을 점검하고 아래를 모두 통과하게 고쳐 주세요.

□ 가로 스크롤이 0인가 → html과 body에 overflow-x: clip (hidden 아님)
□ 버튼·내비 링크·CTA 라벨이 두 줄로 줄바꿈되는 곳이 있는가
  → 라벨을 줄이거나 white-space: nowrap + 폭 조정
□ 이미지가 들어가는 그리드 트랙이 맨 1fr인가 → minmax(0, 1fr)로
□ 큰 제목이 화면을 넘치는가 → overflow-wrap: anywhere; min-width: 0
□ 100vh를 썼는가 → 100dvh로
□ 터치 타깃이 44×44px보다 작은 곳이 있는가 → 확대
□ hover에만 존재하는 기능이 있는가 (드래그 핸들, 더보기 메뉴, 갤러리 화살표)
  → 모바일에서는 항상 표시
□ 입력창 font-size가 16px보다 작은가 → 16px로 (iOS 자동 확대 방지)
□ 하단 고정 바가 마지막 항목을 가리는가 → 스크롤 영역에 하단 패딩 추가
□ 좌우 스플릿을 그대로 두었는가 → 하단 [목록 | 지도] 세그먼트 토글로 전환
□ 드로어를 그대로 두었는가 → 바텀시트로 전환 (60% 스냅, 드래그로 92%)
□ 안전 영역을 고려했는가 → 하단 고정 요소에 env(safe-area-inset-bottom)
````

## E-4. 8개 상태 채우기

````text
이 컴포넌트에 빠진 상태를 모두 추가해 주세요.
default / hover / focus-visible / active / disabled / loading / error / success

- focus-visible: 2px 링 --primary 40% + offset 2px. 즉시 표시(애니메이션 금지)
- disabled: opacity 0.5 + cursor not-allowed + aria-disabled
- loading: 좌측 16px 스피너 + 라벨 유지. 폭이 변하면 안 됩니다
- error: 1px --danger 보더 + CircleAlert 16px + aria-invalid + 하단에 에러 문구
- success: 아이콘이 Check --success로 1.5초간 바뀜

각 상태를 강제로 볼 수 있는 클래스(.is-hover, .is-focus, .is-active)도 함께 지원하고,
8개 상태를 세로로 쌓아 라벨을 붙인 미리보기 파일을 별도로 만들어 주세요.
````

## E-5. 다크 모드 추가

````text
이 화면에 다크 모드를 추가해 주세요. class="dark" 방식입니다.

토큰 값 (이것만 사용):
--bg              oklch(15% 0.004 286)
--surface         oklch(19% 0.005 286)
--surface-hover   oklch(23% 0.006 286)
--surface-active  oklch(27% 0.006 286)
--border          oklch(31% 0.007 286)
--border-strong   oklch(38% 0.008 286)
--text            oklch(96% 0.003 286)
--text-secondary  oklch(75% 0.010 286)
--text-muted      oklch(62% 0.012 286)
--text-disabled   oklch(47% 0.012 286)
--primary         oklch(72% 0.128 275)   /* 어두운 배경에서 밝게 뒤집습니다 */
--primary-fg      oklch(17% 0.020 275)
--primary-subtle  oklch(24% 0.045 275)
--primary-border  oklch(38% 0.075 275)
--success         oklch(72% 0.115 150)
--warning         oklch(78% 0.125 82)
--danger          oklch(70% 0.150 25)

규칙:
- 다크에서는 그림자로 계층을 만들지 말고 **보더 대비**로 만드세요
- 일자 색은 명도를 +18% 보정해 어두운 지도 위에서 묻히지 않게 하세요
- 지도 타일은 positron → dark-matter 스타일로 교체
- 이미지는 dark:brightness-90 정도만. 반전 금지
- 라이트 모드의 레이아웃·간격·모션은 그대로 유지하세요
````

## E-6. 빈 상태 · 에러 상태 추가

````text
이 화면의 빈 상태와 에러 상태를 추가해 주세요.

## 빈 상태
- 세로 패딩 48px, 중앙 정렬, 최대 폭 360px
- lucide 라인 아이콘 40px --text-disabled (일러스트를 그리지 마세요)
- 제목 text-lg 500
- 설명 text-sm --text-muted — **왜 비었는지 + 무엇을 하면 되는지** 둘 다 담기
- 주 CTA primary + 보조 CTA ghost (필요할 때만)

## 에러 상태
- CircleAlert 40px --danger
- 제목은 사용자 언어로. "500 Internal Server Error" 같은 표현 금지
- 항상 재시도 경로를 주세요. 재시도가 불가하면 대안 경로를
- 개발 모드에서만 하단에 details 아코디언으로 원본 에러

## 이 화면에 필요한 케이스
(해당 화면에 맞게 채워서 요청하세요. 예:)
- 필터 결과 0건: "'맛집'에 해당하는 곳이 없어요" + "전체 보기"
- 검색 결과 0건: "'{검색어}'와 맞는 곳이 없어요" + "링크로 직접 추가"
- 네트워크 실패: "검색 결과를 가져오지 못했어요" + "다시 시도" + "이 단계 건너뛰기"
````

## E-7. 구조 다시 짜기 (템플릿 느낌이 날 때)

````text
이 화면이 흔한 템플릿처럼 보입니다. 정보 구조를 다시 짜 주세요.

금지하는 리듬:
- 히어로 → 3열 아이콘 카드 → 후기 → 4단 링크 푸터
- 좌측 텍스트 / 우측 이미지를 번갈아 반복하는 지그재그 섹션
- 모든 섹션을 같은 폭·같은 상하 여백으로 쌓기
- 섹션마다 "제목 + 설명 + 버튼" 3요소를 반복

대신:
- 이 화면의 사용자 과제가 무엇인지 한 문장으로 먼저 적으세요
- 그 과제에 직접 기여하지 않는 섹션을 삭제하세요
- 남은 블록의 폭·정렬·구분 방식을 서로 다르게 하세요
  (전체 폭 / 720px 중앙 / 좌우 스플릿을 섞기)
- 구분은 여백이 아니라 1px 보더선으로
- 제품 설명이 필요하면 화면 맨 아래 한 줄로 압축하세요

바뀐 구조를 먼저 개요로 알려 주고, 확인받은 뒤 코드를 만드세요.
````

---

# F. 이미지·일러스트 생성 프롬프트

이미지 생성 도구(Midjourney / DALL·E / Nanobanana / Recraft)에 넣는 프롬프트다.
**필요한 이미지는 많지 않다.** 대부분의 화면은 타이포그래피만으로 완성된다.

## F-1. 도시 히어로 이미지 (4장 · 필수)

S1의 `CityHeroPreview`와 S0 여행 카드에 쓰인다. 1200×630, webp.

````text
Tokyo cityscape at late afternoon, photographic, natural daylight,
wide establishing shot, muted and desaturated color grade,
soft overcast light, no people in foreground, no text, no logos,
no lens flare, no HDR look, editorial travel photography,
composition leaves the lower-left third visually calm for text overlay
--ar 1200:630
````

도시별 치환:

| 파일 | 프롬프트 앞부분 치환 |
|---|---|
| `tokyo.webp` | `Tokyo cityscape at late afternoon` |
| `osaka.webp` | `Osaka Dotonbori canal at dusk, neon signs dimmed and desaturated` |
| `paris.webp` | `Paris rooftops with zinc chimneys, soft grey morning light` |
| `bangkok.webp` | `Bangkok river with long-tail boats, hazy warm afternoon` |

**공통 요구**: 채도를 낮게. 우리 UI의 뉴트럴 팔레트와 싸우는 원색 사진은 쓰지 않는다.
텍스트가 올라갈 좌하단 3분의 1이 시각적으로 조용해야 한다.

## F-2. OG 이미지 (1장)

1200×630, `public/og/default.png`.

````text
Minimal editorial poster, off-white paper background oklch(98% 0 0),
single thin 1px horizontal rule across the lower third,
large Korean sans-serif headline set in two lines, weight 600, tight letter spacing,
one small indigo dot as the only accent color oklch(53% 0.16 274),
no gradient, no glow, no photograph, no 3d, no illustration,
generous negative space, Swiss typographic poster discipline
--ar 1200:630
````

생성 후 텍스트는 **직접 얹는다**(이미지 생성 모델의 한글 렌더는 신뢰할 수 없다).
얹을 문구: `JustGO` / `도시와 날짜만 정하면, AI가 여행을 계획합니다`

## F-3. 빈 상태 (생성하지 않는다)

⛔ 빈 상태에는 일러스트를 만들지 않는다. lucide 라인 아이콘 40px + 문구로 끝낸다.
`Compass`(여행 없음), `SearchX`(결과 없음), `CircleAlert`(오류), `MapPinOff`(지도 실패).

## F-4. 항공사 로고 (28개 · 직접 제작)

⛔ 실제 항공사 로고를 생성하거나 가져오지 않는다(저작권). 대신 **단색 이니셜 마크**를 만든다.

````text
24×24px SVG. 원형 배경 currentColor 12% opacity.
중앙에 2글자 IATA 코드, 대문자, Inter 600, 9px, currentColor.
색은 컴포넌트에서 상속받는다(고정 색을 넣지 않는다).
28개: KE OZ JL NH LJ TW BX RS 7C ZE CI BR CX SQ TG MH VN PR GA UA DL AA AF KL LH BA EK QR
````

## F-5. 장소 사진 (생성하지 않는다)

목데이터의 장소 이미지는 `https://picsum.photos/seed/{placeId}-{n}/800/600`을 쓴다.
시드가 고정이므로 항상 같은 이미지가 나오고, API 키도 과금도 없다.
실제 사진으로 교체하려면 `spec.md` 6.2.3의 `local` 모드로 전환한다.

⛔ **생성 이미지를 실제 장소 사진인 것처럼 쓰지 않는다.** 존재하지 않는 장소를
그린 그림을 "센소지"라고 붙이는 것은 사용자를 속이는 것이다.

---

# G. 운용 규칙과 자체 검수

## G-1. 자체 검수 6축 (모든 프롬프트에 이미 포함됨)

결과물을 받으면 도구가 스스로 6축을 1~5점으로 채점하게 한다. **3점 미만이 있으면 수정 후 재제출**을 요구한다.

| 축 | 질문 | 5점의 모습 |
|---|---|---|
| **철학** (P) | 이 화면에 일관된 관점이 있는가? | 뉴트럴 미니멀 + 고밀도라는 원칙이 모든 결정에서 보인다 |
| **위계** (H) | 무엇이 가장 중요한지 3초 안에 보이는가? | 주 행동 1개가 명확하고, 나머지가 그것을 방해하지 않는다 |
| **완성도** (E) | 상태·엣지 케이스가 채워졌는가? | 8개 상태 + 빈/로딩/에러 상태가 모두 있다 |
| **구체성** (S) | 이 제품에만 맞는 결정인가? | 문구·데이터·레이아웃이 여행 계획이라는 맥락에 특화되어 있다 |
| **절제** (R) | 뺄 것이 없는가? | 장식적 요소 0개, 모션 3개 이하, 색 1개 |
| **다양성** (V) | 템플릿 리듬을 피했는가? | 흔한 랜딩 구조·지그재그 섹션이 없다 |

## G-2. 프롬프트 작성 규칙

| 규칙 | 이유 |
|---|---|
| **B를 매 턴 붙인다** | 도구는 3~4턴이면 자기 기본값으로 돌아간다 |
| **한 프롬프트에 화면 1개** | 2개 이상 넣으면 둘 다 얕아진다 |
| **목 데이터를 한국어로 직접 준다** | "적당한 예시를 넣어줘"라고 하면 영어 Lorem이 나온다 |
| **숫자를 준다** | "적당한 높이"가 아니라 "48px". 픽셀을 안 주면 도구가 크게 만든다 |
| **상태를 열거한다** | "여러 상태"가 아니라 8개 이름을 나열 |
| **금지 목록을 뺀다** | B-5는 길지만 지우지 말 것. 여기서 대부분의 AI 티가 걸러진다 |
| **부정문보다 대체안** | "그림자 쓰지 마" → "그림자 대신 1px 보더로" |
| **개요를 먼저 받는다** | 큰 화면은 "구조를 먼저 알려주고 확인받은 뒤 코드" |
| **실패하면 쪼갠다** | 화면 → 섹션 → 컴포넌트 순으로 범위를 줄인다 |

## G-3. 자주 나오는 실패와 대처

| 증상 | 원인 | 대처 |
|---|---|---|
| 보라 그라데이션 히어로 | B를 안 붙였거나 3턴 이상 지났다 | B 재투입 + E-1 |
| 카드가 다 둥글고 그림자가 있다 | 도구 기본 스타일 | E-1 + "radius 8px, 그림자 없음, 1px 보더" 반복 |
| 이모지 아이콘 | 아이콘 이름을 안 줬다 | D-2처럼 **lucide 아이콘 이름을 하나씩** 명시 |
| 영어 UI | 한국어 문구를 안 줬다 | `spec.md` 7장의 카피 블록을 그대로 붙인다 |
| 헐렁한 레이아웃 | 픽셀 값을 안 줬다 | E-2 + 높이·패딩을 숫자로 |
| 없는 지표가 등장 | 랜딩 화면에서 자주 발생 | E-1의 "만들어 낸 숫자" 항목. 그 섹션 자체를 삭제 |
| 지도가 무지개색 | 지도 스타일을 안 지정했다 | "채도 낮은 회색 톤, 색은 마커와 경로만" 명시 |
| 애니메이션 과다 | 모션 개수를 안 제한했다 | "이 화면의 모션은 N개만: A, B" 식으로 이름까지 지정 |
| 스켈레톤이 실제와 크기가 다르다 | CLS 요건을 안 줬다 | "스켈레톤과 실제 카드의 높이가 정확히 같아야 함" 명시 |
| 컴포넌트에 상태가 3개뿐 | 상태를 열거하지 않았다 | E-4 |

## G-4. 최종 인수 전 확인 (사람이 눈으로)

```
□ B-5 금지 목록 위반 0건
□ 1440px과 375px 두 폭에서 스크린샷을 찍어 비교했다
□ 키보드 Tab만으로 화면의 모든 조작에 도달했다
□ 포커스 링이 모든 인터랙티브 요소에서 보인다
□ 한국어 문구가 spec.md 7장의 카피와 일치한다
□ 색·폰트가 토큰 이름으로 참조되고, 파일 안에 hex/OKLCH 값이 없다
□ 변하는 숫자에 tabular-nums가 적용되어 폭이 흔들리지 않는다
□ 모션 종류가 3개 이하이고, prefers-reduced-motion에서 멈춘다
□ 이 화면의 주 행동이 무엇인지 처음 보는 사람이 3초 안에 말할 수 있다
```

---

**문서 끝** · 명세 원본은 [`spec.md`](./spec.md)에 있다. 문구를 바꿀 때는 `spec.md` 7장의 카피 블록을 먼저 고친 뒤 이 문서의 프롬프트를 갱신한다.
