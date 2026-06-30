"""Provider status routes."""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

from arenawealth.config.settings import load_provider_keys

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


class ProviderStatusResponse(BaseModel):
    provider_id: str
    display_name: str
    env_var: str | None
    configured: bool
    required_for: str
    free_tier: bool


PROVIDERS = (
    ("yahoo", "Yahoo Finance", None, True, "quotes, historical prices, fallback fundamentals"),
    ("sec_edgar", "SEC EDGAR", "SEC_USER_AGENT", True, "point-in-time US filings"),
    ("finnhub", "Finnhub", "FINNHUB_API_KEY", True, "optional live quote and metrics fallback"),
    ("fred", "FRED", "FRED_API_KEY", True, "future macro regime studies"),
    ("patentsview", "PatentsView", "PATENTSVIEW_API_KEY", True, "future innovation moat signal"),
    ("openfigi", "OpenFIGI", "OPENFIGI_API_KEY", True, "future issuer and instrument mapping"),
    ("openalex", "OpenAlex", "OPENALEX_MAILTO", True, "future research and citation context"),
)


@router.get("/status", response_model=list[ProviderStatusResponse])
def provider_status() -> list[ProviderStatusResponse]:
    keys = load_provider_keys()
    configured = {
        "SEC_USER_AGENT": bool(os.getenv("SEC_USER_AGENT")),
        "FINNHUB_API_KEY": bool(keys.finnhub_api_key),
        "FRED_API_KEY": bool(keys.fred_api_key),
        "PATENTSVIEW_API_KEY": bool(keys.patentsview_api_key),
        "OPENFIGI_API_KEY": bool(keys.openfigi_api_key),
        "OPENALEX_MAILTO": bool(keys.openalex_mailto),
    }
    return [
        ProviderStatusResponse(
            provider_id=provider_id,
            display_name=display_name,
            env_var=env_var,
            configured=True if env_var is None else configured.get(env_var, False),
            required_for=required_for,
            free_tier=free_tier,
        )
        for provider_id, display_name, env_var, free_tier, required_for in PROVIDERS
    ]
