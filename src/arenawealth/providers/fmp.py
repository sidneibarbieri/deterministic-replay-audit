"""Financial Modeling Prep (FMP) API provider.

Best source for historical structured data and Moat metrics.
Free tier available; paid tiers for real-time data.
"""

import os
from decimal import Decimal
from typing import Any

import httpx

from arenawealth.providers.base import QuoteError, RateLimitError


class FMPError(QuoteError):
    """FMP API specific error."""

    pass

class FMPProvider:
    """Financial Modeling Prep API implementation.

    Best for: 30 years of historical financial statements,
    Moat metrics (ROIC, margins), and Compounding data.

    Requires API key from environment: FMP_API_KEY
    Free tier: 250 requests/day
    """

    BASE_URL = "https://financialmodelingprep.com/api/v3"
    DAILY_LIMIT = 250

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize with API key.

        Args:
            api_key: FMP API key. Falls back to env var.

        Raises:
            FMPError: If no API key available.
        """
        self._api_key = api_key or os.getenv("FMP_API_KEY")
        if not self._api_key:
            raise FMPError("FMP_API_KEY environment variable required")

        self._client = httpx.Client(
            timeout=60.0,
            base_url=self.BASE_URL,
            params={"apikey": self._api_key},
        )

    def get_income_statement(
        self, ticker: str, period: str = "annual", limit: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch income statements.

        Args:
            ticker: Stock symbol.
            period: "annual" or "quarter".
            limit: Number of periods (max 30 years for annual).

        Returns:
            List of income statement data.

        Raises:
            FMPError: If request fails.
        """
        endpoint = f"/income-statement/{ticker}"
        params = {"period": period, "limit": limit}

        response = self._client.get(endpoint, params=params)

        if response.status_code == 429:
            raise RateLimitError(f"FMP rate limit exceeded ({self.DAILY_LIMIT}/day)")

        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            raise FMPError(f"Invalid response for {ticker}: {data}")

        return data

    def get_balance_sheet(
        self, ticker: str, period: str = "annual", limit: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch balance sheets.

        Args:
            ticker: Stock symbol.
            period: "annual" or "quarter".
            limit: Number of periods.

        Returns:
            List of balance sheet data.
        """
        endpoint = f"/balance-sheet-statement/{ticker}"
        params = {"period": period, "limit": limit}

        response = self._client.get(endpoint, params=params)
        response.raise_for_status()

        return response.json()

    def get_cash_flow(
        self, ticker: str, period: str = "annual", limit: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch cash flow statements.

        Args:
            ticker: Stock symbol.
            period: "annual" or "quarter".
            limit: Number of periods.

        Returns:
            List of cash flow data.
        """
        endpoint = f"/cash-flow-statement/{ticker}"
        params = {"period": period, "limit": limit}

        response = self._client.get(endpoint, params=params)
        response.raise_for_status()

        return response.json()

    def get_key_metrics(
        self, ticker: str, period: str = "annual", limit: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch key metrics including Moat indicators.

        Includes: ROIC, ROE, ROA, margins, and efficiency ratios.

        Args:
            ticker: Stock symbol.
            period: "annual" or "quarter".
            limit: Number of periods.

        Returns:
            List of key metrics.
        """
        endpoint = f"/key-metrics/{ticker}"
        params = {"period": period, "limit": limit}

        response = self._client.get(endpoint, params=params)
        response.raise_for_status()

        return response.json()

    def get_financial_growth(
        self, ticker: str, period: str = "annual", limit: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch growth metrics for Compounding analysis.

        Includes: Revenue growth, FCF growth, EPS growth, book value growth.

        Args:
            ticker: Stock symbol.
            period: "annual" or "quarter".
            limit: Number of periods.

        Returns:
            List of growth metrics.
        """
        endpoint = f"/financial-growth/{ticker}"
        params = {"period": period, "limit": limit}

        response = self._client.get(endpoint, params=params)
        response.raise_for_status()

        return response.json()

    def get_historical_price(
        self, ticker: str, from_date: str, to_date: str
    ) -> list[dict[str, Any]]:
        """Fetch historical end-of-day prices.

        Args:
            ticker: Stock symbol.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).

        Returns:
            List of daily prices.
        """
        endpoint = f"/historical-price-full/{ticker}"
        params = {"from": from_date, "to": to_date}

        response = self._client.get(endpoint, params=params)
        response.raise_for_status()

        data = response.json()
        return data.get("historical", [])

    def close(self) -> None:
        """Close HTTP client."""
        self._client.close()

    @staticmethod
    def _parse_decimal(value: str | float | None) -> Decimal | None:
        """Parse value to Decimal safely.

        Args:
            value: Raw value from API.

        Returns:
            Decimal or None if invalid.
        """
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (ValueError, TypeError):
            return None
