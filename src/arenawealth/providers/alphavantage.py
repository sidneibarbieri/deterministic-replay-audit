"""Alpha Vantage quote provider.

Real-time and historical data via Alpha Vantage API.
Free tier: 25 requests/day.
"""

import os
from decimal import Decimal

import httpx

from arenawealth.providers.base import Quote, QuoteError, RateLimitError, TickerNotFoundError


class AlphaVantageProvider:
    """Alpha Vantage API implementation.

    Uses Global Quote endpoint for real-time data.
    Requires API key from environment: ALPHAVANTAGE_API_KEY.
    """

    BASE_URL = "https://www.alphavantage.co/query"
    RATE_LIMIT_REQUESTS = 25  # Free tier daily limit

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize with API key.

        Args:
            api_key: Alpha Vantage API key. Falls back to env var.

        Raises:
            QuoteError: If no API key available.
        """
        self._api_key = api_key or os.getenv("ALPHAVANTAGE_API_KEY")
        if not self._api_key:
            raise QuoteError("Alpha Vantage API key required")

        self._client = httpx.Client(timeout=30.0, base_url=self.BASE_URL)

    def get_quote(self, ticker: str) -> Quote:
        """Fetch global quote for ticker.

        Args:
            ticker: Security symbol.

        Returns:
            Current market quote.

        Raises:
            TickerNotFoundError: If ticker invalid.
            RateLimitError: If API limit exceeded.
            QuoteError: For other failures.
        """
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": ticker,
            "apikey": self._api_key,
        }

        response = self._client.get("", params=params)

        if response.status_code == 429:
            raise RateLimitError("Alpha Vantage rate limit exceeded (25/day)")

        response.raise_for_status()
        data = response.json()

        # Check for rate limit in response
        if "Note" in data and "rate limit" in data["Note"]:
            raise RateLimitError("Alpha Vantage rate limit exceeded")

        quote_data = data.get("Global Quote", {})
        if not quote_data:
            raise TickerNotFoundError(f"Ticker {ticker} not found")

        return self._parse_quote(ticker, quote_data)

    def get_quotes(self, tickers: list[str]) -> list[Quote]:
        """Fetch quotes for multiple tickers.

        Note: Alpha Vantage free tier has strict rate limits.
        Consider batching or using premium tier for multiple tickers.

        Args:
            tickers: List of security symbols.

        Returns:
            Successfully fetched quotes.
        """
        results: list[Quote] = []

        for ticker in tickers:
            try:
                quote = self.get_quote(ticker)
                results.append(quote)
            except QuoteError:
                # Skip failed tickers, continue with partial results
                continue

        return results

    def _parse_quote(self, ticker: str, data: dict) -> Quote:
        """Parse Alpha Vantage response into Quote.

        Args:
            ticker: Security symbol.
            data: Raw API response data.

        Returns:
            Normalized Quote instance.
        """
        # Alpha Vantage uses keys like "01. symbol", "05. price"
        price = Decimal(data.get("05. price", "0"))
        change = Decimal(data.get("09. change", "0"))
        change_percent_str = data.get("10. change percent", "0%").replace("%", "")
        change_percent = Decimal(change_percent_str)
        volume = int(float(data.get("06. volume", "0")))

        return Quote(
            ticker=ticker.upper(),
            price=price,
            currency="USD",
            change=change,
            change_percent=change_percent,
            volume=volume,
            timestamp=data.get("07. latest trading day"),
        )

    def close(self) -> None:
        """Close HTTP client."""
        self._client.close()
