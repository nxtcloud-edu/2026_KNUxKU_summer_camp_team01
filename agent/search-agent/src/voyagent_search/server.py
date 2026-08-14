"""Search Agent HTTP/SSE adapter.

The search graph remains provider-agnostic. This module exposes it to Supervisor and
reports which providers were used so demo data is never presented as live data.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from .clients.base import ProviderBundle
from .clients.demo_enrichment import DemoEnrichedGooglePlacesProvider
from .clients.google_places import GooglePlacesClient
from .clients.mock import MockTravelProvider
from .clients.serpapi import SerpApiGoogleFlightsClient
from .clients.web_city import web_city_provider_from_env
from .contracts import SearchRequest
from .env import load_project_environment
from .graph import run_search

app = FastAPI(title="Voyagent Search Agent", version="0.1.0")
logger = logging.getLogger(__name__)

_CITY_AIRPORTS = {
    "서울": "ICN",
    "서울특별시": "ICN",
    "seoul": "ICN",
    "도쿄": "NRT",
    "동경": "NRT",
    "tokyo": "NRT",
    "오사카": "KIX",
    "osaka": "KIX",
    "파리": "CDG",
    "paris": "CDG",
    "방콕": "BKK",
    "bangkok": "BKK",
}


def _event(sequence: int, started: float, event_type: str, **values: Any) -> str:
    payload = {
        "seq": sequence,
        "at": int((time.monotonic() - started) * 1000),
        "type": event_type,
        **values,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _resolve_airports(source: dict[str, Any]) -> dict[str, Any]:
    trip_info = (
        source.get("trip_info") if isinstance(source.get("trip_info"), dict) else {}
    )
    origin_name = str(source.pop("origin", "")).strip()
    destination_name = str(trip_info.get("destination", "")).strip()
    if not source.get("origin_iata"):
        source["origin_iata"] = _CITY_AIRPORTS.get(
            origin_name.casefold()
        ) or _CITY_AIRPORTS.get(origin_name)
    if not source.get("destination_iata"):
        source["destination_iata"] = _CITY_AIRPORTS.get(
            destination_name.casefold()
        ) or _CITY_AIRPORTS.get(destination_name)
    return source


def _providers() -> tuple[ProviderBundle, dict[str, str]]:
    load_project_environment()
    mode = os.environ.get("SEARCH_PROVIDER_MODE", "auto").strip().lower()
    mock = MockTravelProvider()
    if mode == "mock":
        return ProviderBundle(flights=mock, stays=mock, places=mock, city=mock), {
            "flights": "mock",
            "stays": "mock",
            "places": "mock",
            "city": "mock",
        }

    serp_key = os.environ.get("SERPAPI_API_KEY", "")
    places_key = os.environ.get("GOOGLE_PLACES_API_KEY", "") or os.environ.get(
        "GOOGLE_MAPS_API_KEY", ""
    )
    flights = SerpApiGoogleFlightsClient.from_env() if serp_key else mock
    if places_key:
        google = DemoEnrichedGooglePlacesProvider(GooglePlacesClient(places_key))
        stays = google
        places = google
    else:
        stays = mock
        places = mock
    city = web_city_provider_from_env() if os.environ.get("GEMINI_API_KEY") else mock
    labels = {
        "flights": "serpapi" if serp_key else "mock",
        "stays": "google-places" if places_key else "mock",
        "places": "google-places" if places_key else "mock",
        "city": "gemini-google-search" if os.environ.get("GEMINI_API_KEY") else "mock",
    }
    return ProviderBundle(
        flights=flights, stays=stays, places=places, city=city
    ), labels


@app.get("/health")
async def health() -> dict[str, Any]:
    _, labels = _providers()
    return {"status": "ok", "providers": labels}


@app.post("/agent/search")
async def search(request: Request) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        started = time.monotonic()
        try:
            source = _resolve_airports(await request.json())
            parsed = SearchRequest.model_validate(source)
            providers, labels = _providers()
            yield _event(
                0, started, "status", text="항공편·숙소·장소 후보를 검색하고 있어요"
            )
            yield _event(1, started, "progress", value=0.1)
            result = await run_search(parsed, providers)
            yield _event(2, started, "progress", value=1.0)
            yield _event(
                3,
                started,
                "done",
                payload={"result": result.model_dump(mode="json"), "providers": labels},
                summary="검색 후보와 검증 근거를 준비했어요.",
            )
        except ValidationError as error:
            yield _event(
                0,
                started,
                "error",
                code="invalid_input",
                message=str(error),
                retryable=False,
            )
        except Exception as error:
            logger.exception("search agent request failed")
            yield _event(
                0,
                started,
                "error",
                code="agent_failed",
                message=str(error),
                retryable=True,
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["app"]
