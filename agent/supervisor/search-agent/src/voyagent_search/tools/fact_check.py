"""검색 결과의 출처·범위·시간·가격 모순을 결정론적으로 판별하는 Tool.

외부 세계의 절대적 진위를 추측하지 않고, 공급자 원문 증거가 있는지와 결과 내부 값이
서로 일관적인지만 검사한다. error가 하나라도 있으면 후보를 Plan 전달 대상으로 쓰지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from ..contracts import (
    CityInfo,
    FactVerification,
    SelectedFlight,
    SelectedPlace,
    SelectedStay,
    SourceEvidence,
    VerificationIssue,
)


def evidence_from_raw(raw: dict[str, Any], fields: Iterable[str]) -> list[SourceEvidence]:
    """공급자가 원문에 부착한 provenance와 실제 존재하는 근거 필드만 기록한다."""

    source = raw.get("_source")
    if not isinstance(source, dict):
        return []
    present_fields = [field for field in fields if field in raw]
    try:
        return [SourceEvidence(**source, fields=present_fields)]
    except (TypeError, ValueError):
        return []


def cited_evidence_from_raw(raw: dict[str, Any], fields: Iterable[str]) -> list[SourceEvidence]:
    """웹 조사 provider가 보존한 citation별 provenance를 검증 가능한 근거로 변환한다."""

    sources = raw.get("_sources")
    if not isinstance(sources, list):
        return []
    present_fields = [field for field in fields if field in raw]
    evidence: list[SourceEvidence] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        try:
            evidence.append(SourceEvidence(**source, fields=present_fields))
        except (TypeError, ValueError):
            continue
    return evidence


def demo_evidence_from_raw(raw: dict[str, Any]) -> list[SourceEvidence]:
    """Google 근거와 분리된 명시적 demo enrichment provenance를 읽는다."""

    demo = raw.get("_demo_enrichment")
    if not isinstance(demo, dict):
        return []
    try:
        fields = demo.get("fields", [])
        if not isinstance(fields, list):
            return []
        return [SourceEvidence(
            provider=str(demo["provider"]),
            record_id=str(demo["record_id"]),
            title=str(demo["title"]),
            retrieved_at=demo["retrieved_at"],
            fields=[str(field) for field in fields],
        )]
    except (KeyError, TypeError, ValueError):
        return []


def _verify_demo_enrichment(
    raw: dict[str, Any],
    expected_currency: str,
    issues: list[VerificationIssue],
    evidence: list[SourceEvidence],
) -> None:
    """보강 metadata의 통화·provenance를 검사하고 경고로 demo 경계를 보존한다."""

    demo = raw.get("_demo_enrichment")
    if demo is None:
        return
    demo_evidence = demo_evidence_from_raw(raw)
    if not demo_evidence:
        issues.append(_issue("error", "invalid_demo_provenance", "DEMO 보강 출처가 올바르지 않습니다"))
        return
    evidence.extend(demo_evidence)
    if not isinstance(demo, dict) or demo.get("currency") != expected_currency:
        issues.append(_issue("error", "demo_currency_mismatch", "DEMO 보강 통화가 요청 통화와 다릅니다"))
    issues.append(_issue("warning", "demo_enrichment", "[DEMO DATA] canonical 누락 필드에 시연용 보강값을 사용했습니다"))


def _issue(severity: str, code: str, message: str, field: str | None = None) -> VerificationIssue:
    return VerificationIssue(severity=severity, code=code, field=field, message=message)  # type: ignore[arg-type]


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _finish(
    issues: list[VerificationIssue],
    evidence: list[SourceEvidence],
    estimated_fields: list[str] | None = None,
) -> FactVerification:
    return FactVerification(
        accepted=bool(evidence) and not any(issue.severity == "error" for issue in issues),
        issues=issues,
        evidence=evidence,
        estimated_fields=estimated_fields or [],
    )


def verify_flight(offer: SelectedFlight, raw: dict[str, Any], expected_currency: str) -> FactVerification:
    """가격·통화·ID를 검사하고 timezone이 명시된 시각에서만 duration을 재계산한다."""

    issues: list[VerificationIssue] = []
    evidence = evidence_from_raw(raw, ("id", "itineraries", "price"))
    if not evidence:
        issues.append(_issue("error", "missing_evidence", "항공 공급자 근거가 없습니다"))
    if str(raw.get("id")) != offer.id:
        issues.append(_issue("error", "id_mismatch", "정규화 ID가 원문 ID와 다릅니다", "id"))
    if offer.total_price.currency != expected_currency:
        issues.append(_issue("error", "currency_mismatch", "요청 통화와 항공권 통화가 다릅니다", "total_price.currency"))

    for field, leg in (("outbound", offer.outbound), ("inbound", offer.inbound)):
        if leg is None:
            continue
        depart, arrive = _parse_datetime(leg.depart_at), _parse_datetime(leg.arrive_at)
        if not depart or not arrive:
            issues.append(_issue("error", "invalid_datetime", "ISO 출도착 시각을 해석할 수 없습니다", field))
            continue
        if depart.tzinfo is None or arrive.tzinfo is None:
            issues.append(
                _issue(
                    "warning",
                    "duration_not_recomputed",
                    "공항 timezone offset이 없어 공급자 itinerary duration을 사용했습니다",
                    field,
                )
            )
            continue
        actual_minutes = int((arrive - depart).total_seconds() // 60)
        if actual_minutes < 0:
            issues.append(_issue("error", "negative_duration", "도착이 출발보다 빠릅니다", field))
        elif abs(actual_minutes - leg.duration_min) > 5:
            issues.append(_issue("error", "duration_mismatch", "표시 비행시간과 출도착 시각 차이가 다릅니다", field))
    return _finish(issues, evidence)


def verify_stay(stay: SelectedStay, raw: dict[str, Any], expected_currency: str) -> FactVerification:
    """숙소 ID·좌표·가격 통화와 공급자 근거를 확인하고 추정 필드는 거부한다."""

    issues: list[VerificationIssue] = []
    estimated_fields: list[str] = []
    evidence = evidence_from_raw(raw, ("id", "displayName", "location", "priceLevel"))
    if not evidence:
        issues.append(_issue("error", "missing_evidence", "숙소 공급자 근거가 없습니다"))
    _verify_demo_enrichment(raw, expected_currency, issues, evidence)
    if str(raw.get("id")) != stay.id:
        issues.append(_issue("error", "id_mismatch", "숙소 ID가 원문과 다릅니다", "id"))
    if stay.lat == 0 and stay.lng == 0:
        issues.append(_issue("error", "invalid_coordinates", "숙소 좌표가 원점입니다", "lat,lng"))
    if raw.get("_price_is_estimate"):
        estimated_fields.append("price")
        if raw.get("estimateCurrency") != expected_currency:
            issues.append(_issue("error", "estimate_currency_mismatch", "숙소 추정가격 통화가 요청 통화와 다릅니다", "price"))
        issues.append(_issue("error", "unverified_estimate", "실시간 객실가가 아닌 추정가격은 전달할 수 없습니다", "price"))
    if raw.get("_schedule_is_estimate"):
        estimated_fields.extend(("check_in_time", "check_out_time"))
        issues.append(_issue("error", "unverified_estimate", "미확인 체크인·체크아웃 시각은 전달할 수 없습니다"))
    return _finish(issues, evidence, estimated_fields)


def verify_place(place: SelectedPlace, raw: dict[str, Any], expected_currency: str) -> FactVerification:
    """장소 ID·좌표·가격·영업정보를 검증하고 추정 일정 필드는 거부한다."""

    issues: list[VerificationIssue] = []
    estimated_fields: list[str] = []
    evidence = evidence_from_raw(raw, ("id", "displayName", "location", "regularOpeningHours", "priceLevel"))
    if not evidence:
        issues.append(_issue("error", "missing_evidence", "장소 공급자 근거가 없습니다"))
    _verify_demo_enrichment(raw, expected_currency, issues, evidence)
    if str(raw.get("id")) != place.id:
        issues.append(_issue("error", "id_mismatch", "장소 ID가 원문과 다릅니다", "id"))
    if place.lat == 0 and place.lng == 0:
        issues.append(_issue("error", "invalid_coordinates", "장소 좌표가 원점입니다", "lat,lng"))
    if place.opening_hours == "정보 확인 필요":
        issues.append(_issue("error", "opening_hours_unknown", "영업시간을 확인하지 못한 장소는 전달할 수 없습니다", "opening_hours"))
    if raw.get("_price_is_estimate"):
        estimated_fields.append("price")
        if raw.get("estimateCurrency") != expected_currency:
            issues.append(_issue("error", "estimate_currency_mismatch", "장소 추정가격 통화가 요청 통화와 다릅니다", "price"))
        issues.append(_issue("error", "unverified_estimate", "가격 수준 기반 추정값은 전달할 수 없습니다", "price"))
    if raw.get("_schedule_is_estimate"):
        estimated_fields.extend(("closed_days", "expected_duration_min", "physical_intensity"))
        issues.append(_issue("error", "unverified_estimate", "미확인 휴무일·체류시간·활동강도는 전달할 수 없습니다"))
    return _finish(issues, evidence, estimated_fields)


def verify_city_info(city: CityInfo, raw: dict[str, Any]) -> FactVerification:
    """도시 정보가 공식 HTTPS 출처와 조회시각을 포함하고 미래 자료로 위장되지 않았는지 검사한다."""

    issues: list[VerificationIssue] = []
    evidence = evidence_from_raw(raw, ("sources", "weather", "transport", "safety"))
    cited_evidence = cited_evidence_from_raw(raw, ("sources", "weather", "transport", "safety"))
    evidence.extend(cited_evidence)
    if not evidence:
        issues.append(_issue("error", "missing_evidence", "도시 정보 공급자 근거가 없습니다"))
    if raw.get("_web_research") is not None:
        if not cited_evidence:
            issues.append(_issue("error", "missing_web_citation", "도시 웹 조사 citation이 없습니다"))
        elif len(cited_evidence) == 1:
            issues.append(
                _issue(
                    "warning",
                    "limited_web_sources",
                    "도시 웹 출처가 1개이므로 출발 전에 공식 정보를 다시 확인하세요",
                    "sources",
                )
            )
    now = datetime.now(timezone.utc)
    for index, source in enumerate(city.sources):
        if source.url.scheme != "https":
            issues.append(_issue("error", "insecure_source", "도시 정보 출처는 HTTPS여야 합니다", f"sources.{index}.url"))
        retrieved = source.retrieved_at
        if retrieved.tzinfo is None:
            retrieved = retrieved.replace(tzinfo=timezone.utc)
        if retrieved > now:
            issues.append(_issue("error", "future_retrieval", "출처 조회시각이 미래입니다", f"sources.{index}.retrieved_at"))
    return _finish(issues, evidence)
