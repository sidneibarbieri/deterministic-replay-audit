"""Unit tests for quote providers.

Tests Chain of Responsibility fallback pattern.
"""

from decimal import Decimal
from unittest.mock import MagicMock

from arenawealth.providers.base import Quote, QuoteError
from arenawealth.providers.composite import CompositeQuoteProvider


class TestCompositeQuoteProvider:
    """Test composite provider fallback chain."""

    def test_single_provider_success(self):
        """Should return quote when primary succeeds."""
        mock_provider = MagicMock()
        mock_provider.get_quote.return_value = Quote(ticker="AAPL", price=Decimal("175.00"))

        composite = CompositeQuoteProvider()
        composite._providers = [mock_provider]

        result = composite.get_quote("AAPL")

        assert result.ticker == "AAPL"
        assert result.price == Decimal("175.00")

    def test_fallback_to_secondary(self):
        """Should try secondary when primary fails."""
        primary = MagicMock()
        primary.get_quote.side_effect = QuoteError("Primary failed")
        primary.__class__.__name__ = "PrimaryProvider"

        secondary = MagicMock()
        secondary.get_quote.return_value = Quote(ticker="AAPL", price=Decimal("175.00"))

        composite = CompositeQuoteProvider()
        composite._providers = [primary, secondary]

        result = composite.get_quote("AAPL")

        assert result.price == Decimal("175.00")
        primary.get_quote.assert_called_once()
        secondary.get_quote.assert_called_once()

    def test_all_providers_fail(self):
        """Should raise QuoteError when all fail."""
        provider = MagicMock()
        provider.get_quote.side_effect = QuoteError("Failed")
        provider.__class__.__name__ = "MockProvider"

        composite = CompositeQuoteProvider()
        composite._providers = [provider]

        try:
            composite.get_quote("AAPL")
            raise AssertionError("Should have raised")
        except QuoteError as error:
            assert "AAPL" in str(error)
            assert "MockProvider" in str(error)

    def test_get_quotes_partial_success(self):
        """Should return partial results when some tickers fail."""
        mock_provider = MagicMock()
        mock_provider.get_quote.side_effect = [
            Quote(ticker="AAPL", price=Decimal("175.00")),
            QuoteError("Failed"),
            Quote(ticker="MSFT", price=Decimal("380.00")),
        ]

        composite = CompositeQuoteProvider()
        composite._providers = [mock_provider]

        results = composite.get_quotes(["AAPL", "BAD", "MSFT"])

        assert len(results) == 2
        tickers = [q.ticker for q in results]
        assert "AAPL" in tickers
        assert "MSFT" in tickers
