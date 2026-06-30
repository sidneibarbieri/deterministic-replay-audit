"""Application settings loaded from environment or ~/.actionaudit/credentials.env.

Uses pydantic-settings pattern: environment variables override .env file values.
All keys are optional - the product works without any of them.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

CREDENTIAL_VAULT = Path.home() / ".actionaudit" / "credentials.env"


class ProviderKeys(BaseModel):
    """API keys for market data providers. Every field is optional."""

    sec_user_agent: str = ""
    fred_api_key: str = ""
    openfigi_api_key: str = ""
    alphavantage_api_key: str = ""
    fmp_api_key: str = ""
    finnhub_api_key: str = ""
    patentsview_api_key: str = ""
    openalex_mailto: str = ""
    massive_api_key: str = ""

    def has_key(self, provider_id: str) -> bool:
        field_name = f"{provider_id}_api_key"
        return bool(getattr(self, field_name, ""))


def load_provider_keys() -> ProviderKeys:
    """Load keys from environment, falling back to the credential vault file."""
    import os

    from dotenv import load_dotenv

    if CREDENTIAL_VAULT.exists():
        load_dotenv(CREDENTIAL_VAULT)

    local_env = Path(".env")
    if local_env.exists():
        load_dotenv(local_env, override=True)

    return ProviderKeys(
        sec_user_agent=os.getenv("SEC_USER_AGENT", ""),
        fred_api_key=os.getenv("FRED_API_KEY", ""),
        openfigi_api_key=os.getenv("OPENFIGI_API_KEY", ""),
        alphavantage_api_key=os.getenv("ALPHAVANTAGE_API_KEY", ""),
        fmp_api_key=os.getenv("FMP_API_KEY", "") or os.getenv("FINANCIALMODELINGPREP_API_KEY", ""),
        finnhub_api_key=os.getenv("FINNHUB_API_KEY", ""),
        patentsview_api_key=os.getenv("PATENTSVIEW_API_KEY", ""),
        openalex_mailto=os.getenv("OPENALEX_MAILTO", ""),
        massive_api_key=os.getenv("MASSIVE_API_KEY", ""),
    )
