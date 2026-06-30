"""Composite quote provider with fallback chain."""

from __future__ import annotations

import os
from typing import Any

from arenawealth.providers.base import Quote, QuoteError


class CompositeQuoteProvider:
    """Tries multiple providers in order until quote succeeds.

    Primary: Yahoo Finance (free, no key)
    Secondary: Alpha Vantage (free tier, requires key)
    Tertiary: Cached/simulated (last resort)

    Usage:
        provider = CompositeQuoteProvider()
        quote = provider.get_quote("AAPL")
    """

    def __init__(self) -> None:
        self._providers: list[Any] = []
        self._init_providers()

    def _init_providers(self) -> None:
        """Build provider chain in priority order."""
        from arenawealth.providers.yahoo import YahooProvider

        self._providers.append(YahooProvider())

        if os.getenv("ALPHAVANTAGE_API_KEY"):
            from arenawealth.providers.alphavantage import AlphaVantageProvider

            self._providers.append(AlphaVantageProvider())

    def get_quote(self, ticker: str) -> Quote:
        """Fetch quote trying providers in order.

        Args:
            ticker: Security symbol.

        Returns:
            Quote from first successful provider.

        Raises:
            QuoteError: If all providers fail.
        """
        errors: list[str] = []

        for provider in self._providers:
            try:
                return self._provider_quote(provider, ticker)
            except QuoteError as error:
                errors.append(f"{provider.__class__.__name__}: {error}")
                continue

        error_msg = f"All providers failed for {ticker}: {'; '.join(errors)}"
        raise QuoteError(error_msg)

    def _provider_quote(self, provider: Any, ticker: str) -> Quote:
        if hasattr(provider, "get_quote"):
            return provider.get_quote(ticker)

        quotes = provider.get_quotes([ticker])
        if not quotes:
            raise QuoteError(f"No quote returned for {ticker}")
        quote = quotes[0]
        return Quote(
            ticker=quote.ticker,
            price=quote.price,
            change=quote.change,
            change_percent=quote.change_pct,
        )

    def get_quotes(self, tickers: list[str]) -> list[Quote]:
        """Fetch quotes for multiple tickers with per-ticker fallback.

        Args:
            tickers: Security symbols.

        Returns:
            Quotes (partial results if some tickers fail).
        """
        results: list[Quote] = []

        for ticker in tickers:
            try:
                quote = self.get_quote(ticker)
                results.append(quote)
            except QuoteError:
                # Skip failed ticker, continue with others
                continue

        return results

    def close(self) -> None:
        """Cleanup all providers."""
        for provider in self._providers:
            if hasattr(provider, "close"):
                provider.close()
