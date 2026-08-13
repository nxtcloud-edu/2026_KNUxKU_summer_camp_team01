"""시각·날짜·영업시간 산술. 전부 결정론적이며 LLM을 쓰지 않는다.

`opening_hours` 파싱과 휴무일 판정은 `verification-agent/rules.py`의 구현을
**의도적으로 그대로 복사**했다. 두 구현이 조금이라도 다르면 Plan Agent가
"통과할 것"이라고 판단한 일정이 검증에서 떨어진다. 그건 디버깅하기 가장 괴로운
종류의 버그다.

따라서 이 파일의 `parse_opening_hours` / `is_closed_on`은 rules.py가 바뀌면
**같이 바꿔야 한다**. 그 사실을 `tests/test_parity.py`가 지키게 한다.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

# rules.py와 동일: 월요일이 0
WEEKDAYS_KO: tuple[str, ...] = (
    "월요일",
    "화요일",
    "수요일",
    "목요일",
    "금요일",
    "토요일",
    "일요일",
)

# rules.py에서 그대로 가져온 정규식. 수정하지 말고 rules.py와 함께 바꾼다.
OPENING_HOURS_PATTERN = re.compile(r"^\s*(\d{2}):(\d{2})\s*[-~–]\s*(\d{2}):(\d{2})\s*$")
OPEN_AFTER_PATTERN = re.compile(r"^\s*(?:체크인\s*)?([01]\d|2[0-3]):([0-5]\d)\s*이후\s*$")

MINUTES_PER_DAY = 24 * 60


def to_minutes(value: str) -> int:
    """`HH:MM`을 자정 기준 분으로 바꾼다.

    형식이 어긋나면 조용히 0을 돌려주지 않고 예외를 던진다. 시각 계산이 조용히
    틀리면 일정 전체가 어긋나기 때문이다.
    """

    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", value)
    if match is None:
        raise ValueError(f"HH:MM 형식이 아닙니다: {value!r}")
    hour, minute = match.groups()
    return int(hour) * 60 + int(minute)


def to_hhmm(total_minutes: int) -> str:
    """자정 기준 분을 `HH:MM`으로 바꾼다.

    계약의 Time 패턴은 00:00~23:59만 허용한다. 24:00 이상이 나오면 그건
    '다음날로 넘어간 일정'이라는 뜻이고, 현재 계약은 하루를 넘는 항목을
    표현할 수 없다. 조용히 wrap around 시키면 오전으로 뒤집혀 보이므로
    예외로 막는다.
    """

    if total_minutes < 0:
        raise ValueError(f"음수 시각은 표현할 수 없습니다: {total_minutes}")
    if total_minutes >= MINUTES_PER_DAY:
        raise ValueError(
            f"하루를 넘는 시각은 계약으로 표현할 수 없습니다: {total_minutes}분"
        )
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def parse_date(value: str) -> date:
    """`YYYY-MM-DD`를 date로 바꾼다. 달력에 없는 날짜는 예외."""

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"YYYY-MM-DD 형식이 아닙니다: {value!r}")
    return date.fromisoformat(value)


def to_date_str(value: date) -> str:
    return value.isoformat()


def add_days(value: str, days: int) -> str:
    return to_date_str(parse_date(value) + timedelta(days=days))


def day_count(start_date: str, end_date: str) -> int:
    """양 끝을 포함한 여행 일수.

    `rules.py`의 `(trip.end_date - trip.start_date).days + 1`과 같아야 한다.
    """

    return (parse_date(end_date) - parse_date(start_date)).days + 1


def weekday_ko(value: str) -> str:
    """날짜에서 한국어 요일을 계산한다.

    요일을 하드코딩하거나 LLM에게 묻지 않는다. 날짜에서 계산하는 것만이
    유일하게 옳은 방법이다.
    """

    return WEEKDAYS_KO[parse_date(value).weekday()]


def _normalize(value: str) -> str:
    """rules.py의 `_normalize`와 동일."""

    return value.strip().casefold()


def is_closed_on(day_date: str, closed_days: list[str]) -> bool:
    """그 날짜가 휴무일인지. rules.py `_is_closed`와 동일한 판정.

    rules.py는 전체 요일명(`월요일`)과 첫 글자(`월`)를 모두 인정한다.
    계약 enum은 전체 요일명만 허용하지만, 판정 로직은 그대로 복사한다.
    """

    weekday = WEEKDAYS_KO[parse_date(day_date).weekday()]
    normalized = {_normalize(value) for value in closed_days}
    return _normalize(weekday) in normalized or _normalize(weekday[0]) in normalized


def parse_opening_hours(value: str) -> tuple[int, int] | None:
    """영업시간 문자열을 (여는 분, 닫는 분)으로 바꾼다.

    rules.py `_parse_opening_hours`와 동일하다. 파싱 불가면 `None`이고,
    검증 에이전트는 그 경우 `INVALID_OPENING_HOURS`로 **fail** 판정한다.
    그래서 Plan Agent는 입력 단계에서 이걸 미리 확인해야 한다.

    인정되는 두 형식만 있다.
      - `06:00-17:00` (구분자 `-` `~` `–`, 닫는 시각 `24:00` 허용)
      - `체크인 15:00 이후` / `15:00 이후`
    """

    range_match = OPENING_HOURS_PATTERN.fullmatch(value)
    if range_match is not None:
        open_hour, open_minute, close_hour, close_minute = map(int, range_match.groups())
        valid_open = open_hour <= 23 and open_minute <= 59
        valid_close = close_minute <= 59 and (
            close_hour <= 23 or (close_hour == 24 and close_minute == 0)
        )
        if valid_open and valid_close:
            return open_hour * 60 + open_minute, close_hour * 60 + close_minute
        return None

    after_match = OPEN_AFTER_PATTERN.fullmatch(value)
    if after_match is not None:
        open_hour, open_minute = map(int, after_match.groups())
        return open_hour * 60 + open_minute, MINUTES_PER_DAY

    return None


def format_open_after(check_in_time: str) -> str:
    """숙소용 `opening_hours` 문자열을 만든다.

    `SelectedStay`에는 `opening_hours`가 없고 `check_in_time`만 있다. 검증
    에이전트는 모든 항목의 `opening_hours`를 파싱하므로 Plan Agent가 이 형식으로
    합성해 줘야 한다. `체크인 HH:MM 이후`는 `OPEN_AFTER_PATTERN`에 걸린다.
    """

    to_minutes(check_in_time)  # 형식 검증. 어긋나면 예외.
    return f"체크인 {check_in_time} 이후"


def round_up_to_5(total_minutes: int) -> int:
    """5분 단위로 올림한다.

    이동시간을 1분 단위로 내놓으면 정밀해 보이지만 근거가 없다. 올림을 쓰는
    이유는 내림이 `INSUFFICIENT_TRAVEL_TIME`을 유발할 수 있기 때문이다.
    """

    if total_minutes <= 0:
        return 0
    return ((total_minutes + 4) // 5) * 5


__all__ = [
    "MINUTES_PER_DAY",
    "OPENING_HOURS_PATTERN",
    "OPEN_AFTER_PATTERN",
    "WEEKDAYS_KO",
    "add_days",
    "day_count",
    "format_open_after",
    "is_closed_on",
    "parse_date",
    "parse_opening_hours",
    "round_up_to_5",
    "to_date_str",
    "to_hhmm",
    "to_minutes",
    "weekday_ko",
]
