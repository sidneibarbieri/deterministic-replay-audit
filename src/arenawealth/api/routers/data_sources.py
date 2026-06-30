"""Data source readiness and live health checks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from arenawealth.config.settings import ProviderKeys, load_provider_keys

router = APIRouter(prefix="/api/v1/data-sources", tags=["data-sources"])


class DataSourceHealth(BaseModel):
    provider_id: str
    name: str
    status: str
    configured: bool
    last_check: str
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataSourcesHealthResponse(BaseModel):
    timestamp: str
    live: bool
    sources: list[DataSourceHealth]
    summary: dict[str, int]


@dataclass(frozen=True)
class SourceCheck:
    provider_id: str
    name: str
    configured: Callable[[ProviderKeys], bool]
    purpose: str
    live_check: Callable[[ProviderKeys], dict[str, Any]]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def source_checks() -> tuple[SourceCheck, ...]:
    return (
        SourceCheck(
            provider_id="yahoo",
            name="Yahoo Finance",
            configured=lambda _keys: True,
            purpose="quotes, adjusted price history, fallback fundamentals",
            live_check=check_yahoo,
        ),
        SourceCheck(
            provider_id="sec_edgar",
            name="SEC EDGAR",
            configured=lambda keys: bool(keys.sec_user_agent),
            purpose="point-in-time filings for US issuers",
            live_check=check_sec_edgar,
        ),
        SourceCheck(
            provider_id="fred",
            name="FRED",
            configured=lambda keys: bool(keys.fred_api_key),
            purpose="macro regime studies",
            live_check=check_fred,
        ),
        SourceCheck(
            provider_id="fundamentals_keyed",
            name="Keyed fundamentals",
            configured=lambda keys: bool(keys.fmp_api_key or keys.alphavantage_api_key),
            purpose="optional keyed statements or overview fallback",
            live_check=check_keyed_fundamentals,
        ),
        SourceCheck(
            provider_id="patentsview",
            name="PatentsView",
            configured=lambda keys: bool(keys.patentsview_api_key),
            purpose="innovation moat research signal",
            live_check=check_patentsview,
        ),
    )


@router.get("/health", response_model=DataSourcesHealthResponse)
def data_sources_health(live: bool = Query(default=False)) -> DataSourcesHealthResponse:
    keys = load_provider_keys()
    sources = [evaluate_source(check, keys, live) for check in source_checks()]
    return DataSourcesHealthResponse(
        timestamp=utc_now(),
        live=live,
        sources=sources,
        summary={
            "total": len(sources),
            "working": sum(source.status == "working" for source in sources),
            "configured": sum(source.configured for source in sources),
            "not_configured": sum(not source.configured for source in sources),
            "errors": sum(source.status == "error" for source in sources),
        },
    )


def evaluate_source(
    check: SourceCheck,
    keys: ProviderKeys,
    live: bool,
) -> DataSourceHealth:
    configured = check.configured(keys)
    base_metadata = {"purpose": check.purpose}
    if not configured:
        return DataSourceHealth(
            provider_id=check.provider_id,
            name=check.name,
            status="not_configured",
            configured=False,
            last_check=utc_now(),
            metadata=base_metadata,
        )
    if not live:
        return DataSourceHealth(
            provider_id=check.provider_id,
            name=check.name,
            status="configured",
            configured=True,
            last_check=utc_now(),
            metadata=base_metadata,
        )
    try:
        metadata = check.live_check(keys)
    except (httpx.HTTPError, KeyError, ValueError) as error:
        return DataSourceHealth(
            provider_id=check.provider_id,
            name=check.name,
            status="error",
            configured=True,
            last_check=utc_now(),
            error=str(error),
            metadata=base_metadata,
        )
    return DataSourceHealth(
        provider_id=check.provider_id,
        name=check.name,
        status="working",
        configured=True,
        last_check=utc_now(),
        metadata={**base_metadata, **metadata},
    )


def check_yahoo(_keys: ProviderKeys) -> dict[str, Any]:
    import yfinance

    price = float(yfinance.Ticker("AAPL").fast_info.last_price)
    return {"test_ticker": "AAPL", "price": price}


def check_sec_edgar(keys: ProviderKeys) -> dict[str, Any]:
    response = httpx.get(
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        headers={
            "User-Agent": keys.sec_user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return {"test_ticker": "AAPL", "test_cik": "0000320193"}


def check_fred(keys: ProviderKeys) -> dict[str, Any]:
    response = httpx.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": "GDP", "api_key": keys.fred_api_key, "limit": 1, "file_type": "json"},
        timeout=10.0,
    )
    response.raise_for_status()
    return {"test_series": "GDP"}


def check_keyed_fundamentals(keys: ProviderKeys) -> dict[str, Any]:
    if keys.fmp_api_key:
        response = httpx.get(
            "https://financialmodelingprep.com/api/v3/profile/AAPL",
            params={"apikey": keys.fmp_api_key},
            timeout=10.0,
        )
        response.raise_for_status()
        return {"test_ticker": "AAPL", "provider": "Financial Modeling Prep"}

    response = httpx.get(
        "https://www.alphavantage.co/query",
        params={
            "function": "OVERVIEW",
            "symbol": "AAPL",
            "apikey": keys.alphavantage_api_key,
        },
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("Symbol"):
        raise ValueError("Alpha Vantage returned no overview payload")
    return {"test_ticker": "AAPL", "provider": "Alpha Vantage"}


def check_patentsview(_keys: ProviderKeys) -> dict[str, Any]:
    response = httpx.get(
        "https://api.patentsview.org/patents/query",
        params={
            "q": '{"assignees.assignee_organization":"Apple"}',
            "f": '["patent_id"]',
            "o": '{"per_page":1}',
        },
        timeout=10.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    return {"test_query": "assignee organization: Apple"}
