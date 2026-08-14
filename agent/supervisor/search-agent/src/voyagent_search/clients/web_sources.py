"""사전에 승인한 공식 웹 출처를 확인해 cityInfo 원문을 공급하는 어댑터."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx

from ..contracts import SearchRequest


class OfficialWebSourcesClient:
    """명시적 HTTPS host allowlist에 포함된 공식 URL만 확인한다.

    범용 웹 검색이나 LLM 추측으로 도시 사실을 만들지 않는다. redirect를 따르지 않아
    승인 host에서 사설망으로 우회하는 SSRF 경로도 차단한다.
    """

    def __init__(
        self,
        profiles: Mapping[str, dict[str, Any]],
        *,
        allowed_hosts: set[str],
        timeout_seconds: float = 15.0,
        max_response_bytes: int = 1_000_000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not allowed_hosts:
            raise ValueError("공식 출처 allowed_hosts가 필요합니다")
        self._profiles = dict(profiles)
        self._allowed_hosts = {host.lower() for host in allowed_hosts}
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._transport = transport

    def _validate_source_url(self, value: str) -> None:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not hostname:
            raise ValueError("공식 출처 URL은 hostname이 있는 HTTPS여야 합니다")
        if hostname not in self._allowed_hosts:
            raise ValueError(f"허용되지 않은 공식 출처 host입니다: {hostname}")
        try:
            address = ip_address(hostname)
        except ValueError:
            return
        if not address.is_global:
            raise ValueError("사설·loopback·link-local IP 출처는 허용하지 않습니다")

    async def search_city_info(self, request: SearchRequest) -> list[dict[str, Any]]:
        city = request.trip_info.destination
        if city not in self._profiles:
            raise LookupError(f"승인된 공식 도시 프로필이 없습니다: {city}")

        profile = deepcopy(self._profiles[city])
        sources = profile.get("sources", [])
        if not sources:
            raise ValueError("도시 프로필에는 공식 출처가 한 개 이상 필요합니다")
        for source in sources:
            self._validate_source_url(str(source["url"]))

        now = datetime.now(timezone.utc).isoformat()
        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            for source in sources:
                response = await client.get(source["url"], headers={"User-Agent": "VoyagentSearch/0.1"})
                if response.is_redirect:
                    raise ValueError("공식 출처 redirect는 허용하지 않습니다")
                response.raise_for_status()
                if len(response.content) > self._max_response_bytes:
                    raise ValueError("공식 출처 응답 크기 제한을 초과했습니다")
                source["retrieved_at"] = now

        profile["fetched_at"] = now
        first = sources[0]
        profile["_source"] = {
            "provider": "official-web",
            "record_id": str(profile.get("city_id", city)),
            "title": first["title"],
            "url": first["url"],
            "retrieved_at": now,
        }
        return [profile]
