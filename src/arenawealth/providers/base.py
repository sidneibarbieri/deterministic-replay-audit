"""Base quote provider interface.

Defines contract for all market data providers.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class Quote:
    """Market quote for a security.

    Attributes:
        ticker: Security symbol (e.g., "AAPL").
        price: Current market price.
        currency: Price currency (e.g., "USD").
        change: Price change since previous close.
        change_percent: Percentage change.
        volume: Trading volume.
        timestamp: Quote timestamp.
    """

    ticker: str
    price: Decimal
    currency: str = "USD"
    change: Decimal | None = None
    change_percent: Decimal | None = None
    volume: int | None = None
    timestamp: str | None = None

class QuoteProvider(Protocol):
    """Protocol for market data providers.

    Implementations must provide fresh quotes for tickers.
    """

    def get_quote(self, ticker: str) -> Quote:
        """Fetch quote for single ticker.

        Args:
            ticker: Security symbol.

        Returns:
            Current market quote.

        Raises:
            QuoteError: If quote cannot be retrieved.
        """
        ...

    def get_quotes(self, tickers: list[str]) -> list[Quote]:
        """Fetch quotes for multiple tickers.

        Args:
            tickers: List of security symbols.

        Returns:
            List of quotes (may be partial if some fail).

        Raises:
            QuoteError: If batch fetch fails entirely.
        """
        ...

class QuoteError(Exception):
    """Raised when quote provider fails."""

    pass

class RateLimitError(QuoteError):
    """Provider rate limit exceeded."""

    pass

class TickerNotFoundError(QuoteError):
    """Requested ticker not found."""

    pass
