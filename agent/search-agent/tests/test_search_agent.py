"""Search Agent의 계약·병렬 실행·부분 실패·live 요청 경계를 검증한다."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from voyagent_search.aggregate import build_search_to_plan
from voyagent_search.__main__ import _build_request, build_parser
from voyagent_search.clients.demo_enrichment import DemoEnrichedGooglePlacesProvider
from voyagent_search.clients.serpapi import SerpApiGoogleFlightsClient
from voyagent_search.clients.base import ProviderBundle
from voyagent_search.clients.google_places import GooglePlacesClient
from voyagent_search.clients.mock import MockTravelProvider
from voyagent_search.clients.web_city import GeminiGoogleSearchCityInfoClient, web_city_provider_from_env
from voyagent_search.clients.web_sources import OfficialWebSourcesClient
from voyagent_search.contracts import Persona, SearchRequest, SearchSelection, TripInfo
from voyagent_search.graph import hybrid_demo_provider_bundle, mock_provider_bundle, run_search
from voyagent_search.schema_registry import load_schema, validate_search_to_plan


class FailingFlightProvider:
    """항공 공급자만 실패시켜 병렬 오류 격리를 확인한다."""

    async def search_flights(self, _request: SearchRequest) -> list[dict]:
        raise TimeoutError("flight provider timeout")


class EvidenceMissingFlightProvider(MockTravelProvider):
    """출처가 없는 원문이 사실 검증 단계에서 제거되는지 확인한다."""

    async def search_flights(self, request: SearchRequest) -> list[dict]:
        rows = await super().search_flights(request)
        for row in rows:
            row.pop("_source", None)
        return rows


class MixedFlightProvider(MockTravelProvider):
    """정상 row와 손상 row가 섞였을 때 부분 진단이 남는지 확인한다."""

    async def search_flights(self, request: SearchRequest) -> list[dict]:
        rows = await super().search_flights(request)
        return [*rows, {"id": "broken", "itineraries": [], "price": {}}]


class ManyPlacesProvider(MockTravelProvider):
    """25개 원문을 만들어 결과 상한 20건을 확인한다."""

    async def search_places(self, request: SearchRequest) -> list[dict]:
        seed = (await super().search_places(request))[0]
        rows = []
        for index in range(25):
            row = deepcopy(seed)
            row["id"] = f"place-{index:02d}"
            row["displayName"] = {"text": f"장소 {index:02d}"}
            row["location"] = {
                "latitude": seed["location"]["latitude"] + index * 0.0001,
                "longitude": seed["location"]["longitude"] + index * 0.0001,
            }
            row["_source"]["record_id"] = row["id"]
            row["_source"]["title"] = f"장소 {index:02d} mock record"
            rows.append(row)
        return rows


class ConcurrentMockProvider(MockTravelProvider):
    """네 provider 호출이 실제로 겹치는지 최대 동시 실행 수를 기록한다."""

    def __init__(self) -> None:
        self.active = 0
        self.peak = 0

    async def _barrier(self) -> None:
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.05)
        self.active -= 1

    async def search_flights(self, request: SearchRequest) -> list[dict]:
        await self._barrier()
        return await super().search_flights(request)

    async def search_stays(self, request: SearchRequest) -> list[dict]:
        await self._barrier()
        return await super().search_stays(request)

    async def search_places(self, request: SearchRequest) -> list[dict]:
        await self._barrier()
        return await super().search_places(request)

    async def search_city_info(self, request: SearchRequest) -> list[dict]:
        await self._barrier()
        return await super().search_city_info(request)


def make_trip_info(**overrides: object) -> TripInfo:
    values = {
        "destination": "도쿄",
        "start_date": "2026-06-15",
        "end_date": "2026-06-17",
        "num_travelers": 2,
        "budget_total": 1_200_000,
        "budget_currency": "KRW",
        "budget_includes": ["숙소", "식사", "관광지"],
        "transport_mode": "대중교통",
        "day_start_time": "09:00",
        "day_end_time": "22:00",
        "persona": Persona(
            description="역사 명소와 맛집을 선호하는 여행",
            must_visit=["센소지"],
            avoid=["장시간 도보"],
            pace="보통",
            max_walking_level="중간",
        ),
    }
    values.update(overrides)
    return TripInfo.model_validate(values)


def make_request(**overrides: object) -> SearchRequest:
    values = {
        "trip_info": make_trip_info(),
        "origin_iata": "ICN",
        "destination_iata": "NRT",
        "include_flights": True,
        "include_stays": True,
        "max_results": 20,
    }
    values.update(overrides)
    return SearchRequest.model_validate(values)


class FakeGooglePlacesProvider:
    """wrapper와 hybrid wiring을 네트워크 없이 검증하는 실제 Places 형태의 fake."""

    def __init__(self) -> None:
        source_time = "2026-06-01T00:00:00+00:00"
        self.stay_rows = [{
            "id": "paris-hotel-1",
            "displayName": {"text": "Hôtel de Test Paris"},
            "formattedAddress": "1 Rue de Test, Paris",
            "location": {"latitude": 48.8566, "longitude": 2.3522},
            "primaryType": "hotel",
            "types": ["hotel", "lodging"],
            "rating": 4.6,
            "priceLevel": "PRICE_LEVEL_MODERATE",
            "_source": {
                "provider": "google-places",
                "record_id": "paris-hotel-1",
                "title": "Google Places Text Search record",
                "url": "https://maps.google.com/?q=paris-hotel-1",
                "retrieved_at": source_time,
            },
        }]
        self.place_rows = [{
            "id": "paris-place-1",
            "displayName": {"text": "Musée de Test"},
            "formattedAddress": "2 Avenue de Test, Paris",
            "location": {"latitude": 48.8606, "longitude": 2.3376},
            "primaryType": "museum",
            "types": ["museum", "tourist_attraction"],
            "rating": 4.8,
            "regularOpeningHours": {"weekdayDescriptions": ["월요일: 오전 9:00~오후 6:00"]},
            "_source": {
                "provider": "google-places",
                "record_id": "paris-place-1",
                "title": "Google Places Text Search record",
                "url": "https://maps.google.com/?q=paris-place-1",
                "retrieved_at": source_time,
            },
        }]

    async def search_stays(self, _request: SearchRequest) -> list[dict]:
        return deepcopy(self.stay_rows)

    async def search_places(self, _request: SearchRequest) -> list[dict]:
        return deepcopy(self.place_rows)


class DemoEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrapper_preserves_google_fields_and_adds_only_explicit_demo_fields(self) -> None:
        delegate = FakeGooglePlacesProvider()
        original_stays = deepcopy(delegate.stay_rows)
        original_places = deepcopy(delegate.place_rows)
        provider = DemoEnrichedGooglePlacesProvider(delegate)
        request = make_request(
            trip_info=make_trip_info(destination="파리"),
            destination_iata="CDG",
            max_results=3,
        )

        stays_first = await provider.search_stays(request)
        stays_second = await provider.search_stays(request)
        places = await provider.search_places(request)

        self.assertEqual(delegate.stay_rows, original_stays)
        self.assertEqual(delegate.place_rows, original_places)
        self.assertEqual(stays_first[0]["_source"], original_stays[0]["_source"])
        self.assertEqual(places[0]["_source"], original_places[0]["_source"])
        self.assertEqual(stays_first[0]["estimatedPrice"], stays_second[0]["estimatedPrice"])
        self.assertEqual(stays_first[0]["displayName"], original_stays[0]["displayName"])
        self.assertEqual(places[0]["regularOpeningHours"], original_places[0]["regularOpeningHours"])
        self.assertNotIn("openingHoursText", places[0])
        self.assertEqual(stays_first[0]["formattedAddress"], original_stays[0]["formattedAddress"])
        self.assertEqual(places[0]["formattedAddress"], original_places[0]["formattedAddress"])
        self.assertIn("[DEMO DATA]", stays_first[0]["_demo_note"])
        self.assertIn("[DEMO DATA]", places[0]["_demo_note"])
        self.assertEqual(stays_first[0]["_demo_enrichment"]["provider"], "voyagent-demo-enrichment")
        self.assertIn("estimatedPrice", stays_first[0]["_demo_enrichment"]["fields"])
        self.assertIn("expectedDurationMin", places[0]["_demo_enrichment"]["fields"])

    async def test_non_tokyo_hybrid_graph_uses_google_identity_and_demo_provenance(self) -> None:
        google_demo = DemoEnrichedGooglePlacesProvider(FakeGooglePlacesProvider())
        providers = hybrid_demo_provider_bundle(
            flights=MockTravelProvider(),
            enriched_places=google_demo,
            city=MockTravelProvider(),
        )
        request = make_request(
            trip_info=make_trip_info(destination="파리"),
            destination_iata="CDG",
            max_results=3,
        )

        result = await run_search(request, providers)

        self.assertEqual(result.stays.status, "success")
        self.assertEqual(result.places.status, "success")
        self.assertEqual(result.stays.candidates[0].stay.name, "Hôtel de Test Paris")
        self.assertEqual(result.places.candidates[0].place.name, "Musée de Test")
        self.assertIn("[DEMO DATA]", result.stays.candidates[0].stay.note)
        providers_used = {item.provider for item in result.places.candidates[0].verification.evidence}
        self.assertEqual(providers_used, {"google-places", "voyagent-demo-enrichment"})
        self.assertTrue(any(
            issue.code == "demo_enrichment"
            for issue in result.places.candidates[0].verification.issues
        ))

        handoff = build_search_to_plan(
            result,
            SearchSelection(
                flight_id=result.flights.candidates[0].offer.id,
                stay_id=result.stays.candidates[0].stay.id,
                place_ids=[result.places.candidates[0].place.id],
            ),
        )
        payload = validate_search_to_plan(handoff)
        self.assertEqual(payload["trip_info"]["destination"], "파리")
        self.assertEqual(payload["selected"]["stay"]["name"], "Hôtel de Test Paris")
        self.assertIn("[DEMO DATA]", payload["selected"]["places"][0]["note"])


class SearchAgentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_end_to_end_and_canonical_projection(self) -> None:
        result = await run_search(make_request(), mock_provider_bundle())

        self.assertEqual(result.flights.status, "success")
        self.assertEqual(result.stays.status, "success")
        self.assertEqual(result.places.status, "success")
        self.assertEqual(result.city.status, "success")
        self.assertTrue(result.city.city_info)
        self.assertTrue(all(candidate.verification.accepted for candidate in result.flights.candidates))
        self.assertTrue(all(candidate.verification.evidence for candidate in result.places.candidates))

        handoff = build_search_to_plan(
            result,
            SearchSelection(
                flight_id=result.flights.candidates[0].offer.id,
                stay_id=result.stays.candidates[0].stay.id,
                place_ids=[result.places.candidates[0].place.id],
            ),
        )
        payload = validate_search_to_plan(handoff)
        self.assertEqual(set(payload), {"schema_version", "trip_info", "selected"})
        self.assertEqual(set(payload["selected"]), {"flight", "stay", "places"})
        self.assertNotIn("city", payload)
        self.assertNotIn("verification", payload["selected"]["places"][0])
        self.assertIn("[DEMO DATA]", payload["selected"]["stay"]["note"])
        self.assertTrue(all("[DEMO DATA]" in place["note"] for place in payload["selected"]["places"]))

    async def test_mock_bundle_rejects_tokyo_fixture_for_other_destinations(self) -> None:
        request = make_request(
            trip_info=make_trip_info(destination="파리"),
            destination_iata="CDG",
        )

        result = await run_search(request, mock_provider_bundle())

        self.assertEqual(result.stays.status, "error")
        self.assertEqual(result.places.status, "error")
        self.assertEqual(result.stays.candidates, [])
        self.assertEqual(result.places.candidates, [])
        self.assertIn("도쿄 전용", result.stays.error or "")

    async def test_provider_bundle_is_required_to_prevent_mock_fail_open(self) -> None:
        with self.assertRaisesRegex(ValueError, "ProviderBundle"):
            await run_search(make_request())

    async def test_optional_searches_are_skipped_and_nullable(self) -> None:
        request = make_request(
            include_flights=False,
            include_stays=False,
            origin_iata=None,
            destination_iata=None,
            max_results=2,
        )
        result = await run_search(request, mock_provider_bundle())

        self.assertEqual(result.flights.status, "skipped")
        self.assertEqual(result.stays.status, "skipped")
        self.assertLessEqual(len(result.places.candidates), 2)
        self.assertEqual(result.city.status, "success")

        handoff = build_search_to_plan(
            result,
            SearchSelection(place_ids=[result.places.candidates[0].place.id]),
        )
        self.assertIsNone(handoff.selected.flight)
        self.assertIsNone(handoff.selected.stay)
        validate_search_to_plan(handoff)

    async def test_one_provider_failure_does_not_cancel_other_subagents(self) -> None:
        mock = MockTravelProvider()
        providers = ProviderBundle(flights=FailingFlightProvider(), stays=mock, places=mock, city=mock)
        result = await run_search(make_request(), providers)

        self.assertEqual(result.flights.status, "error")
        self.assertIn("timeout", result.flights.error or "")
        self.assertEqual(result.stays.status, "success")
        self.assertEqual(result.places.status, "success")
        self.assertEqual(result.city.status, "success")

    async def test_missing_evidence_rejects_all_flight_candidates(self) -> None:
        mock = MockTravelProvider()
        providers = ProviderBundle(flights=EvidenceMissingFlightProvider(), stays=mock, places=mock, city=mock)
        result = await run_search(make_request(), providers)

        self.assertEqual(result.flights.status, "error")
        self.assertEqual(result.flights.candidates, [])
        self.assertTrue(any("missing_evidence" in issue for issue in result.flights.issues))

    async def test_malformed_row_is_reported_without_dropping_valid_rows(self) -> None:
        mock = MockTravelProvider()
        providers = ProviderBundle(flights=MixedFlightProvider(), stays=mock, places=mock, city=mock)
        result = await run_search(make_request(), providers)

        self.assertEqual(result.flights.status, "success")
        self.assertGreater(len(result.flights.candidates), 0)
        self.assertTrue(any("broken" in issue and "정규화 실패" in issue for issue in result.flights.issues))

    async def test_place_result_is_capped_at_twenty(self) -> None:
        mock = MockTravelProvider()
        providers = ProviderBundle(flights=mock, stays=mock, places=ManyPlacesProvider(), city=mock)
        result = await run_search(make_request(max_results=20), providers)

        self.assertEqual(result.places.status, "success")
        self.assertEqual(len(result.places.candidates), 20)
        self.assertEqual(len({item.place.id for item in result.places.candidates}), 20)

    async def test_four_subagents_actually_run_concurrently(self) -> None:
        provider = ConcurrentMockProvider()
        bundle = ProviderBundle(flights=provider, stays=provider, places=provider, city=provider)
        result = await run_search(make_request(), bundle)

        self.assertEqual(provider.peak, 4)
        self.assertEqual(result.places.status, "success")

    async def test_unknown_selection_is_rejected(self) -> None:
        result = await run_search(make_request(), mock_provider_bundle())
        with self.assertRaisesRegex(ValueError, "검증된 후보"):
            build_search_to_plan(result, SearchSelection(place_ids=["unknown-place"]))


class LiveAdapterBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_serpapi_round_trip_query_mapping_and_provenance(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.params.get("departure_token"):
                return httpx.Response(
                    200,
                    json={
                        "best_flights": [{
                            "flights": [{
                                "departure_airport": {
                                    "id": "NRT",
                                    "time": "2026-06-17 18:00",
                                },
                                "arrival_airport": {
                                    "id": "ICN",
                                    "time": "2026-06-17 20:30",
                                },
                                "duration": 150,
                                "flight_number": "KE 702",
                            }],
                            "total_duration": 150,
                            "price": 500000,
                        }],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "best_flights": [{
                        "flights": [{
                            "departure_airport": {
                                "id": "ICN",
                                "time": "2026-06-15 09:00",
                            },
                            "arrival_airport": {
                                "id": "NRT",
                                "time": "2026-06-15 11:30",
                            },
                            "duration": 150,
                            "flight_number": "KE 701",
                        }],
                        "total_duration": 150,
                        "price": 500000,
                        "departure_token": "outbound-token",
                    }],
                },
            )

        client = SerpApiGoogleFlightsClient("test-key", transport=httpx.MockTransport(handler))
        request = make_request(max_results=3)
        rows = await client.search_flights(request)

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].url.path, "/search.json")
        self.assertEqual(requests[0].url.params["engine"], "google_flights")
        self.assertEqual(requests[0].url.params["departure_id"], "ICN")
        self.assertEqual(requests[0].url.params["arrival_id"], "NRT")
        self.assertEqual(requests[0].url.params["return_date"], "2026-06-17")
        self.assertEqual(requests[0].url.params["adults"], "2")
        self.assertEqual(requests[0].url.params["currency"], "KRW")
        self.assertEqual(requests[0].url.params["no_cache"], "true")
        self.assertEqual(requests[1].url.params["departure_token"], "outbound-token")
        self.assertEqual(rows[0]["_source"]["provider"], "serpapi-google-flights")
        self.assertNotIn("api_key", rows[0]["_source"]["url"])
        self.assertEqual(len(rows[0]["itineraries"]), 2)
        self.assertEqual(rows[0]["price"], {"grandTotal": "500000.0", "currency": "KRW"})

        from voyagent_search.tools.flight_search import normalize_flight_offers

        candidates, issues = normalize_flight_offers(rows, request)
        self.assertEqual(issues, [])
        self.assertEqual(len(candidates), 1)
        self.assertIsNotNone(candidates[0].offer.inbound)

    async def test_google_places_headers_body_without_fabricated_plan_fields(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"places": [{
                "id": "google-1",
                "displayName": {"text": "테스트 호텔"},
                "location": {"latitude": 35.0, "longitude": 139.0},
                "priceLevel": "PRICE_LEVEL_MODERATE",
                "googleMapsUri": "https://maps.google.com/?q=google-1",
            }]})

        client = GooglePlacesClient("key", transport=httpx.MockTransport(handler))
        request = make_request(max_results=7)
        rows = await client.search_stays(request)

        body = json.loads(requests[0].content)
        self.assertEqual(requests[0].url.path, "/v1/places:searchText")
        self.assertEqual(requests[0].headers["X-Goog-Api-Key"], "key")
        self.assertIn("places.id", requests[0].headers["X-Goog-FieldMask"])
        self.assertEqual(body["pageSize"], 7)
        self.assertNotIn("estimatedPrice", rows[0])
        self.assertNotIn("checkInTime", rows[0])

        from voyagent_search.tools.stay_search import normalize_stays

        candidates, issues = normalize_stays(rows, request)
        self.assertEqual(candidates, [])
        self.assertTrue(any("정규화 실패" in issue for issue in issues))

    async def test_google_places_is_currency_agnostic_without_price_fabrication(self) -> None:
        client = GooglePlacesClient(
            "key",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"places": []})),
        )
        request = make_request(trip_info=make_trip_info(budget_currency="USD"))
        self.assertEqual(await client.search_places(request), [])

    async def test_gemini_city_agent_uses_google_search_and_citation_sources(self) -> None:
        requests: list[httpx.Request] = []
        draft = {
            "city_id": "paris",
            "city_name": "파리",
            "country_name": "프랑스",
            "timezone": "Europe/Paris",
            "currency": "EUR",
            "languages": ["프랑스어"],
            "overview": "프랑스의 수도이자 문화·예술 중심지입니다.",
            "weather": {
                "summary": "10월은 선선하며 출발 직전 공식 예보 확인이 필요합니다.",
                "packing_tips": ["겹쳐 입을 옷", "우산"],
            },
            "transport": {
                "summary": "메트로와 RER 중심으로 이동할 수 있습니다.",
                "tips": ["공식 교통 앱에서 운행 정보를 확인하세요."],
            },
            "safety": {
                "summary": "혼잡 지역에서 소지품을 주의하세요.",
                "emergency_numbers": ["112"],
                "tips": ["여권 사본을 별도로 보관하세요."],
            },
            "etiquette_tips": ["상점에 들어갈 때 인사하세요."],
            "practical_tips": ["공식 관광 안내를 확인하세요."],
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 2:
                return httpx.Response(200, json={
                    "steps": [
                        {
                            "type": "google_search_call",
                            "arguments": {"queries": ["파리 공식 관광청 교통 안전"]},
                        },
                        {
                            "type": "model_output",
                            "content": [{
                                "type": "text",
                                "text": "파리 공식 여행 출처를 확인했습니다.",
                                "annotations": [{
                                    "type": "url_citation",
                                    "url": "https://parisjetaime.com/",
                                    "title": "Paris je t'aime",
                                }],
                            }],
                        },
                    ],
                })
            return httpx.Response(200, json={
                "steps": [
                    {
                        "type": "google_search_call",
                        "arguments": {"queries": ["파리 공식 관광 교통 안전 날씨"]},
                    },
                    {
                        "type": "model_output",
                        "content": [{
                            "type": "text",
                            "text": json.dumps(draft, ensure_ascii=False),
                            "annotations": [],
                        }],
                    },
                ],
            })

        client = GeminiGoogleSearchCityInfoClient(
            "gemini-key",
            transport=httpx.MockTransport(handler),
        )
        request = make_request(
            trip_info=make_trip_info(destination="파리", budget_currency="EUR"),
            destination_iata="CDG",
        )
        rows = await client.search_city_info(request)

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].url.path, "/v1beta/interactions")
        self.assertEqual(requests[0].headers["x-goog-api-key"], "gemini-key")
        body = json.loads(requests[0].content)
        self.assertEqual(body["tools"], [{"type": "google_search"}])
        self.assertEqual(body["response_format"]["mime_type"], "application/json")
        self.assertNotIn("gemini-key", str(requests[0].url))
        self.assertEqual(len(rows[0]["sources"]), 1)
        self.assertEqual(rows[0]["_source"]["provider"], "gemini-google-search")
        self.assertEqual(len(rows[0]["_sources"]), 1)

        from voyagent_search.tools.city_info import normalize_city_info

        result = normalize_city_info(rows)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.city_info.city_name if result.city_info else None, "파리")
        evidence_providers = {item.provider for item in result.verification.evidence} if result.verification else set()
        self.assertEqual(evidence_providers, {"gemini-google-search", "google-search-citation"})
        self.assertTrue(result.verification and any(
            issue.code == "limited_web_sources" and issue.severity == "warning"
            for issue in result.verification.issues
        ))

    async def test_gemini_city_agent_rejects_ungrounded_output(self) -> None:
        client = GeminiGoogleSearchCityInfoClient(
            "key",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
                "steps": [{
                    "type": "model_output",
                    "content": [{"type": "text", "text": "{}", "annotations": []}],
                }],
            })),
        )
        with self.assertRaisesRegex(ValueError, "Google Search"):
            await client.search_city_info(make_request())

    async def test_missing_gemini_key_is_isolated_to_city_provider(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            provider = web_city_provider_from_env()
        with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
            await provider.search_city_info(make_request())

    async def test_official_sources_require_allowlist_and_reject_redirect(self) -> None:
        with self.assertRaises(ValueError):
            OfficialWebSourcesClient({}, allowed_hosts=set())

        profile = {
            "도쿄": {
                "city_id": "tokyo",
                "sources": [{"title": "JNTO", "url": "https://www.japan.travel/", "publisher": "JNTO"}],
            }
        }
        redirect_client = OfficialWebSourcesClient(
            profile,
            allowed_hosts={"www.japan.travel"},
            transport=httpx.MockTransport(lambda _: httpx.Response(302, headers={"location": "http://127.0.0.1"})),
        )
        with self.assertRaisesRegex(ValueError, "redirect"):
            await redirect_client.search_city_info(make_request())

        blocked_client = OfficialWebSourcesClient(
            {"도쿄": {"sources": [{"title": "bad", "url": "https://127.0.0.1/", "publisher": "bad"}]}},
            allowed_hosts={"127.0.0.1"},
            transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        )
        with self.assertRaisesRegex(ValueError, "사설"):
            await blocked_client.search_city_info(make_request())


class SearchAgentContractTests(unittest.TestCase):
    def test_hybrid_cli_accepts_non_tokyo_with_explicit_iata(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "--mode", "hybrid",
            "--destination", "파리",
            "--destination-iata", "CDG",
            "--start-date", "2026-10-15",
            "--end-date", "2026-10-17",
        ])

        request = _build_request(args)

        self.assertEqual(request.trip_info.destination, "파리")
        self.assertEqual(request.destination_iata, "CDG")
        self.assertEqual(request.trip_info.persona.must_visit, [])
        self.assertNotIn("센소지", request.trip_info.persona.description)

    def test_cli_keeps_mock_tokyo_only_and_requires_non_tokyo_hybrid_iata(self) -> None:
        parser = build_parser()
        mock_args = parser.parse_args(["--mode", "mock", "--destination", "파리"])
        with self.assertRaisesRegex(ValueError, "도쿄 전용"):
            _build_request(mock_args)

        hybrid_args = parser.parse_args([
            "--mode", "hybrid",
            "--destination", "파리",
            "--start-date", "2026-10-15",
            "--end-date", "2026-10-17",
        ])
        with self.assertRaisesRegex(ValueError, "destination-iata"):
            _build_request(hybrid_args)

    def test_selection_requires_unique_non_empty_places(self) -> None:
        with self.assertRaises(ValidationError):
            SearchSelection(place_ids=[])
        with self.assertRaises(ValidationError):
            SearchSelection(place_ids=["same", "same"])

    def test_canonical_unique_items_are_rejected_before_search(self) -> None:
        with self.assertRaises(ValidationError):
            Persona(description="x", must_visit=["A", "A"], avoid=[], pace="보통", max_walking_level="중간")
        with self.assertRaises(ValidationError):
            make_trip_info(budget_includes=["숙소", "숙소"])

    def test_flight_search_requires_airports_only_when_enabled(self) -> None:
        with self.assertRaises(ValidationError):
            make_request(origin_iata=None)
        request = make_request(include_flights=False, origin_iata=None, destination_iata=None)
        self.assertFalse(request.include_flights)

    def test_result_limit_is_one_to_twenty(self) -> None:
        for invalid in (0, 21):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                make_request(max_results=invalid)

    def test_schema_rejects_unknown_root_field(self) -> None:
        payload = {
            "schema_version": "1.0",
            "trip_info": make_trip_info().model_dump(mode="json"),
            "selected": {"flight": None, "stay": None, "places": []},
            "cityInfo": {},
        }
        with self.assertRaisesRegex(ValueError, "schema validation failed"):
            validate_search_to_plan(payload)

    def test_packaged_schema_matches_repository_canonical_schema(self) -> None:
        repository_schema = json.loads(
            (Path(__file__).resolve().parents[2] / "schemas" / "search-to-plan.schema.json").read_text(encoding="utf-8")
        )
        packaged_schema = json.loads(
            (Path(__file__).resolve().parents[1] / "src" / "voyagent_search" / "schemas" / "search-to-plan.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(packaged_schema, repository_schema)
        self.assertEqual(load_schema("search-to-plan.schema.json"), repository_schema)

    def test_live_clients_require_credentials_and_official_base_url(self) -> None:
        with self.assertRaises(ValueError):
            SerpApiGoogleFlightsClient("")
        with self.assertRaises(ValueError):
            SerpApiGoogleFlightsClient("key", base_url="http://example.com")
        with self.assertRaises(ValueError):
            GooglePlacesClient("")
        with self.assertRaises(ValueError):
            GeminiGoogleSearchCityInfoClient("")


if __name__ == "__main__":
    unittest.main()
