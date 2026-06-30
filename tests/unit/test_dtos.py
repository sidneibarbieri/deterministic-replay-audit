"""Unit tests for Pydantic DTOs.

Validates API contract definitions.
"""

from decimal import Decimal

import pytest  # noqa: F401

from arenawealth.api.dtos import PortfolioCreateRequest, PositionCreateRequest
from arenawealth.providers.base import Quote


class TestPortfolioCreateRequest:
    """Test portfolio creation DTO."""

    def test_valid_creation(self):
        """Should accept valid portfolio data."""
        request = PortfolioCreateRequest(
            name="My Portfolio",
            currency="USD",
            initial_cash=Decimal("10000.00"),
        )

        assert request.name == "My Portfolio"
        assert request.currency == "USD"
        assert request.initial_cash == Decimal("10000.00")

    def test_default_currency(self):
        """Should default to USD currency."""
        request = PortfolioCreateRequest(name="Test")

        assert request.currency == "USD"

    def test_default_cash(self):
        """Should default to zero cash."""
        request = PortfolioCreateRequest(name="Test")

        assert request.initial_cash == Decimal("0")

class TestPositionCreateRequest:
    """Test position creation DTO."""

    def test_valid_creation(self):
        """Should accept valid position data."""
        request = PositionCreateRequest(
            ticker="AAPL",
            name="Apple Inc",
            shares=Decimal("100"),
            average_cost_basis=Decimal("150.00"),
            current_price=Decimal("175.00"),
        )

        assert request.ticker == "AAPL"
        assert request.shares == Decimal("100")

class TestQuote:
    """Test quote DTO."""

    def test_valid_quote(self):
        """Should accept valid quote data."""
        quote = Quote(
            ticker="AAPL",
            price=Decimal("175.50"),
            change=Decimal("2.50"),
            change_percent=Decimal("1.44"),
        )

        assert quote.ticker == "AAPL"
        assert quote.price == Decimal("175.50")
