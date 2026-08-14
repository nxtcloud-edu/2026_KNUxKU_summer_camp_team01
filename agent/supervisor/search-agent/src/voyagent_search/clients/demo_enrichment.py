"""Google Places 실데이터에 canonical 필수 누락값만 명시적으로 보강한다."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from typing import Any

from ..contracts import SearchRequest
from .base import StayPlaceProvider
from .google_places import GooglePlacesClient

_DEMO_LABEL = "[DEMO DATA]"
_DEMO_PROVIDER = "voyagent-demo-enrichment"


def _stable_number(record_id: str, namespace: str) -> int:
    """프로세스마다 달라지는 hash() 대신 SHA-256으로 결정론적 값을 만든다."""

    digest = hashlib.sha256(f"{namespace}:{record_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _demo_price(request: SearchRequest, record_id: str, *, stay: bool) -> float:
    """통화 단위와 무관하게 요청 총예산 비율로 시연용 가격을 만든다."""

    slot = _stable_number(record_id, "stay-price" if stay else "place-price")
    if stay:
        ratio = 0.08 + (slot % 9) * 0.01
    else:
        ratio = (slot % 5) * 0.005
    return round(request.trip_info.budget_total * ratio, 2)


def _metadata(record_id: str, currency: str, fields: list[str]) -> dict[str, Any]:
    """Google provenance와 분리된 내부 demo enrichment provenance를 만든다."""

    return {
        "provider": _DEMO_PROVIDER,
        "record_id": record_id,
        "title": f"{_DEMO_LABEL} deterministic canonical-field enrichment",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
        "currency": currency,
    }


class DemoEnrichedGooglePlacesProvider:
    """실제 Google 장소의 정체성은 유지하고 미제공 canonical 필드만 보강한다.

    보강값은 실시간 가격이나 확정 일정이 아니다. 입력 row와 Google ``_source``는
    변경하지 않으며, 모든 보강 필드는 ``_demo_enrichment``와 최종 note에 표시한다.
    """

    def __init__(self, delegate: StayPlaceProvider) -> None:
        self._delegate = delegate

    @classmethod
    def from_env(cls) -> "DemoEnrichedGooglePlacesProvider":
        """환경설정의 실제 Google Places client를 감싼 provider를 만든다."""

        return cls(GooglePlacesClient.from_env())

    async def search_stays(self, request: SearchRequest) -> list[dict[str, Any]]:
        rows = deepcopy(await self._delegate.search_stays(request))
        for row in rows:
            record_id = str(row.get("id", "unknown"))
            enriched_fields: list[str] = []
            defaults: tuple[tuple[str, object], ...] = (
                ("estimatedPrice", _demo_price(request, record_id, stay=True)),
                ("currency", request.trip_info.budget_currency),
                ("checkInTime", "15:00"),
                ("checkOutTime", "11:00"),
            )
            for field, value in defaults:
                if row.get(field) is None or row.get(field) == "":
                    row[field] = value
                    enriched_fields.append(field)
            row["_demo_note"] = (
                f"{_DEMO_LABEL} 객실 가격·체크인/체크아웃 시각은 시연용 보강값"
            )
            row["_demo_enrichment"] = _metadata(
                record_id,
                request.trip_info.budget_currency,
                enriched_fields,
            )
        return rows

    async def search_places(self, request: SearchRequest) -> list[dict[str, Any]]:
        rows = deepcopy(await self._delegate.search_places(request))
        for row in rows:
            record_id = str(row.get("id", "unknown"))
            stable = _stable_number(record_id, "place-schedule")
            enriched_fields: list[str] = []
            defaults: tuple[tuple[str, object], ...] = (
                ("estimatedPrice", _demo_price(request, record_id, stay=False)),
                ("currency", request.trip_info.budget_currency),
                ("priceUnit", "per_person"),
                ("closedDays", []),
                ("expectedDurationMin", (60, 90, 120, 150)[stable % 4]),
                ("physicalIntensity", ("낮음", "중간", "높음")[stable % 3]),
            )
            for field, value in defaults:
                if row.get(field) is None or row.get(field) == "":
                    row[field] = value
                    enriched_fields.append(field)
            regular_hours = row.get("regularOpeningHours") or {}
            descriptions = regular_hours.get("weekdayDescriptions") if isinstance(regular_hours, dict) else None
            if not row.get("openingHoursText") and not descriptions:
                row["openingHoursText"] = f"매일 09:00~18:00 {_DEMO_LABEL} 시연용 영업시간"
                enriched_fields.append("openingHoursText")
            row["_demo_note"] = (
                f"{_DEMO_LABEL} 가격·휴무일·체류시간·활동강도 및 표시된 대체 영업시간은 "
                "시연용 보강값"
            )
            row["_demo_enrichment"] = _metadata(
                record_id,
                request.trip_info.budget_currency,
                enriched_fields,
            )
        return rows
