"""수락 검사 — 하위 산출물을 supervisor가 직접 검증한다.

## 왜 하위를 믿지 않는가

Plan Agent는 자기 검증기를 갖고 있고, Verification Agent도 판정을 한다.
그럼에도 supervisor가 다시 보는 이유는, **하위가 "괜찮다"고 말하는 것과
실제로 계약을 지키는 것은 다르기** 때문이다. 하위에 버그가 있으면 하위의
자기 보고도 함께 틀린다.

여기서 보는 것은 **경계 계약뿐**이다. 하위의 내부 판단(어느 장소를 왜 그날에
뒀는지)은 보지 않는다. 그건 하위의 재량이다.

## 검사 실패 시

`AcceptanceReport.ok`가 False면 supervisor가 재하달을 시도하거나(상한 있음),
사용자에게 이유를 알린다. 조용히 통과시키지 않는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# 계약 스키마 위치. supervisor는 agent/ 아래에 있으므로 두 단계 위가 agent/다.
_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas"

_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ITEM_ID_PATTERN = re.compile(r"^d[1-9]\d*-[1-9]\d*$")


@dataclass
class AcceptanceReport:
    agent: str
    artifact: str
    failures: list[str] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        if self.ok:
            return f"{self.agent} 산출물 수락 ({len(self.checked)}개 검사 통과)"
        return f"{self.agent} 산출물 반송 ({len(self.failures)}건 위반)"


def _minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def load_schema(name: str) -> dict | None:
    """계약 스키마를 읽는다. 없으면 None (구조 검사를 건너뛴다)."""

    path = _SCHEMA_DIR / name
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def check_plan_output(payload: Any, source: dict) -> AcceptanceReport:
    """Plan Agent 산출물이 `PlanToVerificationInput` 계약을 지키는지 확인한다.

    `source`는 Plan에 넘긴 `SearchToPlanInput`이다. 두 경계를 비교해야
    `trip_info` 불변과 장소 이름 그라운딩을 확인할 수 있다.
    """

    report = AcceptanceReport(agent="plan", artifact="PlanToVerificationInput")

    if not isinstance(payload, dict):
        report.failures.append("payload가 객체가 아닙니다")
        return report

    # ── 최상위 구조 ──
    report.checked.append("최상위 필드")
    if payload.get("schema_version") != "1.0":
        report.failures.append(
            f"schema_version이 '1.0'이 아닙니다: {payload.get('schema_version')!r}"
        )
    for key in ("trip_info", "plan"):
        if key not in payload:
            report.failures.append(f"{key}가 없습니다")
    if report.failures:
        return report

    # ── trip_info를 바꾸지 않았는가 ──
    # conformance.mjs가 두 handoff의 trip_info를 deepEqual로 비교한다.
    report.checked.append("trip_info 불변")
    if payload["trip_info"] != source.get("trip_info"):
        changed = sorted(
            key
            for key in set(payload["trip_info"]) | set(source.get("trip_info", {}))
            if payload["trip_info"].get(key) != source.get("trip_info", {}).get(key)
        )
        report.failures.append(
            f"trip_info가 입력과 다릅니다. 달라진 필드: {', '.join(changed)}"
        )

    trip = payload["trip_info"]
    plan = payload["plan"]
    days = plan.get("days") if isinstance(plan, dict) else None
    if not isinstance(days, list) or not days:
        report.failures.append("plan.days가 비어 있습니다")
        return report

    # ── 날짜·일차 연속성 ──
    report.checked.append("일수와 날짜 연속성")
    start_raw = trip.get("start_date", "")
    end_raw = trip.get("end_date", "")
    if _DATE_PATTERN.match(start_raw) and _DATE_PATTERN.match(end_raw):
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
        expected_count = (end - start).days + 1
        if len(days) != expected_count:
            report.failures.append(
                f"여행 {expected_count}일인데 plan.days는 {len(days)}개입니다"
            )
        for index, day in enumerate(days):
            expected_date = (start + timedelta(days=index)).isoformat()
            if day.get("day") != index + 1:
                report.failures.append(
                    f"days[{index}].day가 {index + 1}이 아닙니다: {day.get('day')}"
                )
            if day.get("date") != expected_date:
                report.failures.append(
                    f"days[{index}].date가 {expected_date}이 아닙니다: {day.get('date')}"
                )
    else:
        report.failures.append("trip_info의 날짜 형식이 올바르지 않습니다")

    # ── 항목 구조와 시각 정합 ──
    report.checked.append("항목 id·시각·이동시간 정합")
    seen_ids: set[str] = set()
    for day_index, day in enumerate(days):
        items = day.get("items")
        if not isinstance(items, list) or not items:
            report.failures.append(f"days[{day_index}].items가 비어 있습니다")
            continue

        for item_index, item in enumerate(items):
            where = f"days[{day_index}].items[{item_index}]"

            item_id = item.get("id", "")
            if not _ITEM_ID_PATTERN.match(str(item_id)):
                report.failures.append(f"{where}.id 형식 위반: {item_id!r}")
            if item_id in seen_ids:
                report.failures.append(f"{where}.id가 중복됩니다: {item_id}")
            seen_ids.add(item_id)

            start_time = item.get("start_time", "")
            end_time = item.get("end_time", "")
            if not _TIME_PATTERN.match(str(start_time)) or not _TIME_PATTERN.match(
                str(end_time)
            ):
                report.failures.append(
                    f"{where} 시각 형식 위반: {start_time!r} ~ {end_time!r}"
                )
                continue

            duration = item.get("expected_duration_min")
            span = _minutes(end_time) - _minutes(start_time)
            if span != duration:
                report.failures.append(
                    f"{where} 시간 {span}분과 expected_duration_min {duration}분 불일치"
                )

            travel = item.get("travel_from_prev")
            if item_index == 0:
                if travel is not None:
                    report.failures.append(f"{where} 첫 항목의 travel_from_prev는 null이어야 합니다")
            else:
                if travel is None:
                    report.failures.append(f"{where} 이동 정보가 없습니다")
                else:
                    previous = items[item_index - 1]
                    prev_end = previous.get("end_time", "")
                    if _TIME_PATTERN.match(str(prev_end)):
                        earliest = _minutes(prev_end) + travel.get("estimated_min", 0)
                        if _minutes(start_time) < earliest:
                            report.failures.append(
                                f"{where} 이동 시간이 "
                                f"{earliest - _minutes(start_time)}분 부족합니다"
                            )
                    # 계약이 허용하는 필드 세 개만 있어야 한다.
                    extra = set(travel) - {"mode", "estimated_min", "distance_km"}
                    if extra:
                        report.failures.append(
                            f"{where}.travel_from_prev에 계약 외 필드: {sorted(extra)}"
                        )

        # 마지막 여행일을 뺀 날의 마지막 항목은 숙소여야 한다.
        if day_index < len(days) - 1 and items:
            if items[-1].get("category") != "숙소":
                report.failures.append(
                    f"days[{day_index}] 마지막 항목이 숙소가 아닙니다: "
                    f"{items[-1].get('category')}"
                )

    # ── 장소 이름 그라운딩 ──
    report.checked.append("장소 이름 그라운딩")
    selected = source.get("selected", {})
    available = {
        str(place.get("name", "")).strip().casefold()
        for place in selected.get("places", [])
    }
    stay = selected.get("stay")
    if isinstance(stay, dict):
        available.add(str(stay.get("name", "")).strip().casefold())

    for day in days:
        for item in day.get("items", []):
            name = str(item.get("name", "")).strip().casefold()
            if name not in available:
                report.failures.append(
                    f"'{item.get('name')}'은 Search 선택 결과에 없는 이름입니다"
                )

    # ── 필수 방문지 ──
    report.checked.append("필수 방문지 반영")
    scheduled = {
        str(item.get("name", "")).strip().casefold()
        for day in days
        for item in day.get("items", [])
    }
    for required in trip.get("persona", {}).get("must_visit", []):
        if str(required).strip().casefold() not in scheduled:
            report.failures.append(f"필수 방문지 '{required}'가 일정에 없습니다")

    return report


def check_verification_output(payload: Any) -> AcceptanceReport:
    """Verification Agent 산출물이 `{possible, checks, feedback}` 형태인지 확인한다."""

    report = AcceptanceReport(agent="verification", artifact="VerificationResult")

    if not isinstance(payload, dict):
        report.failures.append("payload가 객체가 아닙니다")
        return report

    report.checked.append("최상위 필드")
    if not isinstance(payload.get("possible"), bool):
        report.failures.append("possible이 boolean이 아닙니다")

    checks = payload.get("checks")
    if not isinstance(checks, dict):
        report.failures.append("checks가 객체가 아닙니다")
        return report

    report.checked.append("검사 항목 8종")
    expected = {
        "physical_feasibility",
        "budget",
        "operating_hours",
        "daily_schedule",
        "must_visit",
        "avoid",
        "pace",
        "walking_level",
    }
    missing = expected - set(checks)
    if missing:
        report.failures.append(f"검사 항목 누락: {sorted(missing)}")

    report.checked.append("status 값 유효성")
    allowed = {"pass", "warning", "fail", "skipped"}
    for name, check in checks.items():
        if not isinstance(check, dict):
            report.failures.append(f"checks.{name}이 객체가 아닙니다")
            continue
        status = check.get("status")
        if status not in allowed:
            report.failures.append(f"checks.{name}.status 값이 잘못됨: {status!r}")

    # possible과 status가 어긋나면 어느 쪽을 믿어야 할지 알 수 없다.
    report.checked.append("possible과 status 일관성")
    statuses = [
        check.get("status")
        for check in checks.values()
        if isinstance(check, dict)
    ]
    has_fail = "fail" in statuses
    if payload.get("possible") is True and has_fail:
        report.failures.append("fail이 있는데 possible이 true입니다")
    if payload.get("possible") is False and not has_fail:
        report.failures.append("fail이 없는데 possible이 false입니다")

    report.checked.append("feedback 주의·위험 구조")
    feedback = payload.get("feedback")
    if not isinstance(feedback, dict):
        report.failures.append("feedback이 객체가 아닙니다")
        return report

    missing_feedback = {"cautions", "dangers"} - set(feedback)
    if missing_feedback:
        report.failures.append(f"feedback 필드 누락: {sorted(missing_feedback)}")

    for bucket, expected_level in (("cautions", "주의"), ("dangers", "위험")):
        entries = feedback.get(bucket)
        if not isinstance(entries, list):
            report.failures.append(f"feedback.{bucket}가 배열이 아닙니다")
            continue
        for index, entry in enumerate(entries):
            at = f"feedback.{bucket}[{index}]"
            if not isinstance(entry, dict):
                report.failures.append(f"{at}이 객체가 아닙니다")
                continue
            if entry.get("level") != expected_level:
                report.failures.append(f"{at}.level이 {expected_level!r}이 아닙니다")
            for field in ("check", "code", "message"):
                if not isinstance(entry.get(field), str) or not entry[field]:
                    report.failures.append(f"{at}.{field}가 비어 있거나 문자열이 아닙니다")
            if expected_level == "주의":
                attention = entry.get("attention")
                if not isinstance(attention, str) or not attention:
                    report.failures.append(f"{at}.attention이 비어 있거나 문자열이 아닙니다")

    return report


__all__ = [
    "AcceptanceReport",
    "check_plan_output",
    "check_verification_output",
    "load_schema",
]
