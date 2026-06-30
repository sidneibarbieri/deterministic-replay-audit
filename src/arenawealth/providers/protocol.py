"""Provider protocol - the contract every market data source must satisfy.

Providers are pluggable: Yahoo (tier 0, no key), Finnhub (tier 1), etc.
The fallback chain tries providers in order until one succeeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from arenawealth.providers.types import QuoteResult


class ProviderTier(StrEnum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"

class Capability(StrEnum):
    QUOTES = "quotes"
    FUNDAMENTALS = "fundamentals"
    HISTORICAL_PRICES = "historical_prices"
    MACRO = "macro"
    NEWS = "news"

@dataclass(frozen=True)
class ProviderInfo:
    provider_id: str
    display_name: str
    tier: ProviderTier
    capabilities: frozenset[Capability]
    requires_api_key: bool

class QuoteProvider(Protocol):
    """Any source that can return current quotes for a list of tickers."""

    @property
    def info(self) -> ProviderInfo: ...

    def get_quotes(self, tickers: list[str]) -> list[QuoteResult]: ...
