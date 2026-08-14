"""HTTP endpoint 없이 mock 또는 hybrid Search Agent 전체 흐름을 실행하는 CLI."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta
import sys
from typing import Sequence

from .aggregate import build_search_to_plan
from .clients.base import ProviderBundle
from .contracts import Persona, SearchRequest, SearchRunResult, SearchSelection, TripInfo
from .graph import hybrid_demo_provider_bundle, live_provider_bundle, mock_provider_bundle, run_search


def _positive_int(value: str) -> int:
    """CLI의 개수 인자가 양수인지 argparse 단계에서 확인한다."""

    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1 이상의 정수가 필요합니다")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """명시적인 provider mode와 시연 검색 조건을 받는 parser를 만든다."""

    parser = argparse.ArgumentParser(description="Voyagent Search Agent demo runner")
    parser.add_argument(
        "--mode",
        choices=("mock", "hybrid", "hybrid_demo", "live"),
        default="mock",
        help=(
            "mock: 도쿄 전용 전체 DEMO DATA, hybrid: 실제 정체성/위치 + canonical 누락값 DEMO 보강, "
            "live: 실제 provider 직접 제공값만 사용"
        ),
    )
    parser.add_argument("--start-date", help="여행 시작일 YYYY-MM-DD; 생략 시 오늘부터 30일 뒤")
    parser.add_argument("--end-date", help="여행 종료일 YYYY-MM-DD; 생략 시 시작일부터 2일 뒤")
    parser.add_argument("--origin-iata", default="ICN", help="출발 공항 IATA 코드")
    parser.add_argument(
        "--destination-iata",
        default=None,
        help="도착 공항 IATA 코드; 도쿄는 생략 시 NRT, 그 외 hybrid 목적지는 필수",
    )
    parser.add_argument("--destination", default="도쿄", help="목적지 도시/지역명; hybrid는 전 세계 Google Places 검색 지원")
    parser.add_argument("--travelers", type=_positive_int, default=2, help="성인 여행자 수")
    parser.add_argument("--budget-total", type=float, default=1_200_000, help="전체 여행 예산")
    parser.add_argument("--currency", default="KRW", help="3자리 대문자 통화 코드")
    parser.add_argument("--max-results", type=_positive_int, default=3, help="도메인별 최대 후보 수(1~20)")
    parser.add_argument("--place-count", type=_positive_int, default=2, help="자동 선택할 장소 수")
    parser.add_argument("--skip-stay", action="store_true", help="숙소를 선택하지 않고 stay=null로 전달")
    parser.add_argument("--one-way", action="store_true", help="실제 항공을 편도로 검색")
    return parser


def _trip_dates(start_text: str | None, end_text: str | None) -> tuple[str, str]:
    """입력 날짜를 검증하고 생략된 미래 시연 날짜를 결정한다."""

    start = date.fromisoformat(start_text) if start_text else date.today() + timedelta(days=30)
    end = date.fromisoformat(end_text) if end_text else start + timedelta(days=2)
    if end < start:
        raise ValueError("end-date는 start-date보다 빠를 수 없습니다")
    return start.isoformat(), end.isoformat()


def _build_request(args: argparse.Namespace) -> SearchRequest:
    """CLI 인자를 SearchRequest로 변환하고 mode별 데이터 범위를 검증한다."""

    destination = str(args.destination).strip()
    if not destination:
        raise ValueError("destination은 비어 있을 수 없습니다")
    is_tokyo = destination.casefold() == "tokyo" or destination == "도쿄"
    if args.mode == "mock" and not is_tokyo:
        raise ValueError("mock mode는 도쿄 전용 fixture입니다. 다른 목적지는 hybrid mode를 사용하세요")
    destination_iata = args.destination_iata or ("NRT" if is_tokyo else None)
    if args.mode in {"hybrid", "hybrid_demo", "live"} and not destination_iata:
        raise ValueError("도쿄 외 hybrid 목적지는 정확한 --destination-iata를 함께 입력해야 합니다")

    start_date, end_date = _trip_dates(args.start_date, args.end_date)
    if args.mode in {"hybrid", "hybrid_demo", "live"} and date.fromisoformat(start_date) < date.today():
        raise ValueError("hybrid mode의 실제 항공 출발일은 오늘 이후여야 합니다")
    budget_includes = ["식사", "관광지"]
    if not args.skip_stay:
        budget_includes.insert(0, "숙소")
    return SearchRequest(
        trip_info=TripInfo(
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            num_travelers=args.travelers,
            budget_total=args.budget_total,
            budget_currency=args.currency.upper(),
            budget_includes=budget_includes,
            transport_mode="대중교통",
            day_start_time="09:00",
            day_end_time="22:00",
            persona=Persona(
                description=f"{destination}의 대표 장소와 현지 경험을 선호하는 여행",
                must_visit=[],
                avoid=["장시간 도보"],
                pace="보통",
                max_walking_level="중간",
            ),
        ),
        origin_iata=args.origin_iata.upper(),
        destination_iata=destination_iata.upper() if destination_iata else None,
        include_flights=True,
        flight_trip_type="one_way" if args.one_way else "round_trip",
        include_stays=not args.skip_stay,
        max_results=args.max_results,
    )


def _providers_for_mode(mode: str) -> ProviderBundle:
    """사용자가 명시한 mode에만 live provider를 활성화한다."""

    if mode == "live":
        print(
            "[LIVE FACTS] provider가 직접 제공하지 않는 canonical 필드는 보강하지 않고 실패합니다.",
            file=sys.stderr,
        )
        return live_provider_bundle()
    if mode in {"hybrid", "hybrid_demo"}:
        print(
            "[HYBRID DEMO] 항공은 SerpApi 실데이터, 숙소·장소의 이름·좌표·주소·평점·Google 제공 "
            "영업시간은 Google Places 실데이터입니다. canonical에 필요한 가격·일정·활동강도 일부는 "
            "[DEMO DATA]이고, 도시정보는 Gemini agent가 Google Search로 조사합니다. 세 서비스 사용량이 "
            "차감될 수 있습니다.",
            file=sys.stderr,
        )
        return hybrid_demo_provider_bundle()
    print("[MOCK DEMO] 도쿄 전용이며 모든 검색 결과가 DEMO DATA입니다.", file=sys.stderr)
    return mock_provider_bundle()


def _auto_selection(result: SearchRunResult, place_count: int) -> SearchSelection:
    """검증된 실제 반환 후보에서만 첫 항공·숙소와 상위 장소를 선택한다."""

    if result.flights.status != "success" or not result.flights.candidates:
        detail = result.flights.error or "; ".join(result.flights.issues) or "후보 없음"
        raise RuntimeError(f"항공 검색에 실패했습니다: {detail}")
    stay_id: str | None = None
    if result.request.include_stays:
        if result.stays.status != "success" or not result.stays.candidates:
            detail = result.stays.error or "; ".join(result.stays.issues) or "후보 없음"
            raise RuntimeError(f"숙소 검색에 실패했습니다: {detail}")
        stay_id = result.stays.candidates[0].stay.id
    if result.places.status != "success" or not result.places.candidates:
        detail = result.places.error or "; ".join(result.places.issues) or "후보 없음"
        raise RuntimeError(f"장소 검색에 실패했습니다: {detail}")
    place_ids = [candidate.place.id for candidate in result.places.candidates[:place_count]]
    return SearchSelection(
        flight_id=result.flights.candidates[0].offer.id,
        stay_id=stay_id,
        place_ids=place_ids,
    )


async def _main(args: argparse.Namespace) -> None:
    """검색을 먼저 실행하고 runtime 후보 ID로 canonical handoff를 출력한다."""

    request = _build_request(args)
    result = await run_search(request, _providers_for_mode(args.mode))
    if result.city.status != "success":
        print(
            f"[CITY INFO ERROR] {result.city.error or '웹 도시정보를 확인하지 못했습니다'}",
            file=sys.stderr,
        )
    selection = _auto_selection(result, args.place_count)
    handoff = build_search_to_plan(result, selection)
    print(
        f"[AUTO SELECT] flight={selection.flight_id}, stay={selection.stay_id}, "
        f"places={','.join(selection.place_ids)}",
        file=sys.stderr,
    )
    print(handoff.model_dump_json(indent=2))


def main(argv: Sequence[str] | None = None) -> None:
    """CLI 오류를 API key 없는 간결한 메시지로 종료한다."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        asyncio.run(_main(args))
    except (RuntimeError, ValueError) as error:
        parser.exit(1, f"Search Agent error: {error}\n")


if __name__ == "__main__":
    main()
