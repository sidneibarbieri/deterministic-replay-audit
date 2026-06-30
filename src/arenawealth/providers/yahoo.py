"""Yahoo Finance provider - tier 0, no API key required.

This is the default fallback that ensures the product works without any
credential setup. Uses yfinance library which scrapes Yahoo Finance.
"""

from __future__ import annotations

from decimal import Decimal

import yfinance

from arenawealth.providers.protocol import (
    Capability,
    ProviderInfo,
    ProviderTier,
)
from arenawealth.providers.types import QuoteResult

_INFO = ProviderInfo(
    provider_id="yahoo",
    display_name="Yahoo Finance",
    tier=ProviderTier.FREE,
    capabilities=frozenset({Capability.QUOTES, Capability.HISTORICAL_PRICES}),
    requires_api_key=False,
)

class YahooProvider:
    @property
    def info(self) -> ProviderInfo:
        return _INFO

    def get_quotes(self, tickers: list[str]) -> list[QuoteResult]:
        results: list[QuoteResult] = []
        raw = yfinance.Tickers(" ".join(tickers))

        for ticker in tickers:
            info = raw.tickers[ticker].fast_info
            price = Decimal(str(info.last_price))
            prev_close = Decimal(str(info.previous_close))
            change = price - prev_close
            change_pct = (change / prev_close * 100) if prev_close else Decimal("0")

            results.append(
                QuoteResult(
                    ticker=ticker,
                    price=price,
                    change=change,
                    change_pct=change_pct,
                    high_52w=Decimal(str(info.year_high)) if info.year_high else None,
                    low_52w=Decimal(str(info.year_low)) if info.year_low else None,
                    provider_id=_INFO.provider_id,
                )
            )

        return results
