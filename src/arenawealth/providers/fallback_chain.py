"""Fallback chain for quote providers."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from arenawealth.providers.base import QuoteError
from arenawealth.providers.protocol import Capability, QuoteProvider
from arenawealth.providers.types import QuoteResult

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ProviderAttempt:
    provider_id: str
    success: bool
    error: str | None = None

@dataclass
class FallbackResult:
    quotes: list[QuoteResult]
    attempts: list[ProviderAttempt]

    @property
    def provider_used(self) -> str | None:
        for attempt in self.attempts:
            if attempt.success:
                return attempt.provider_id
        return None

class FallbackChain:
    """Ordered list of providers for a given capability. First success wins."""

    def __init__(self, providers: list[QuoteProvider]) -> None:
        self._providers = providers

    def get_quotes(self, tickers: list[str]) -> FallbackResult:
        attempts: list[ProviderAttempt] = []

        for provider in self._providers:
            if Capability.QUOTES not in provider.info.capabilities:
                continue

            try:
                quotes = provider.get_quotes(tickers)
                attempts.append(ProviderAttempt(provider.info.provider_id, success=True))
                logger.info(
                    "quotes resolved by %s for %d tickers",
                    provider.info.provider_id,
                    len(tickers),
                )
                return FallbackResult(quotes=quotes, attempts=attempts)
            except QuoteError as error:
                attempts.append(
                    ProviderAttempt(
                        provider.info.provider_id,
                        success=False,
                        error=str(error),
                    )
                )
                logger.warning(
                    "provider %s failed for quotes: %s", provider.info.provider_id, error
                )

        logger.error("all providers failed for quotes on tickers: %s", tickers)
        return FallbackResult(quotes=[], attempts=attempts)
