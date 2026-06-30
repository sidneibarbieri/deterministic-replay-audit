"""Tests for Money value object - currency safety and arithmetic precision."""

from decimal import Decimal

import pytest

from arenawealth.domain.money import Currency, Money


class TestMoneyArithmetic:
    def test_add_same_currency(self) -> None:
        result = Money.usd("100.50") + Money.usd("200.25")
        assert result.amount == Decimal("300.75")
        assert result.currency == Currency.USD

    def test_add_different_currency_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot mix USD with BRL"):
            Money.usd("100") + Money.brl("200")

    def test_subtract(self) -> None:
        result = Money.usd("500") - Money.usd("123.45")
        assert result.amount == Decimal("376.55")

    def test_multiply_by_shares(self) -> None:
        price = Money.usd("100.00")
        shares = Decimal("50.00000")
        result = price * shares
        assert result.amount == Decimal("100.00") * Decimal("50.00000")

    def test_negate(self) -> None:
        money = Money.usd("100")
        assert (-money).amount == Decimal("-100")

class TestMoneyDisplay:
    def test_usd_display(self) -> None:
        assert Money.usd("171499.17").display() == "$ 171,499.17"

    def test_brl_display(self) -> None:
        assert Money.brl("1234.50").display() == "R$ 1,234.50"

    def test_negative_display(self) -> None:
        assert Money.usd("-3930.01").display() == "$ -3,930.01"

class TestMoneyConversion:
    def test_usd_to_brl(self) -> None:
        usd = Money.usd("1000")
        brl = usd.convert(Currency.BRL, rate="5.75")
        assert brl.currency == Currency.BRL
        assert brl.amount == Decimal("5750.00000000")

class TestMoneyComparison:
    def test_greater_than(self) -> None:
        assert Money.usd("200") > Money.usd("100")

    def test_is_zero(self) -> None:
        assert Money.usd("0").is_zero()
        assert not Money.usd("0.01").is_zero()
