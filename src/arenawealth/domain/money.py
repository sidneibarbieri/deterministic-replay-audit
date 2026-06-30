"""Immutable monetary value with currency - the fundamental unit of financial calculation.

All financial arithmetic goes through Money to prevent currency-mixing bugs at the type level.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel


class Currency(StrEnum):
    USD = "USD"
    BRL = "BRL"
    EUR = "EUR"

DISPLAY_DECIMALS = 2
INTERNAL_DECIMALS = 8
_QUANTIZE_DISPLAY = Decimal(10) ** -DISPLAY_DECIMALS
_QUANTIZE_INTERNAL = Decimal(10) ** -INTERNAL_DECIMALS

class Money(BaseModel, frozen=True):
    """Immutable monetary amount with currency enforcement.

    Uses Decimal internally for exact arithmetic (no float rounding).
    """

    amount: Decimal
    currency: Currency

    @staticmethod
    def usd(value: Decimal | float | str) -> Money:
        return Money(amount=Decimal(str(value)), currency=Currency.USD)

    @staticmethod
    def brl(value: Decimal | float | str) -> Money:
        return Money(amount=Decimal(str(value)), currency=Currency.BRL)

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot mix {self.currency} with {other.currency}. "
                f"Convert explicitly via Money.convert()."
            )

    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, factor: Decimal | float | int) -> Money:
        return Money(
            amount=self.amount * Decimal(str(factor)),
            currency=self.currency,
        )

    def __neg__(self) -> Money:
        return Money(amount=-self.amount, currency=self.currency)

    def __gt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount > other.amount

    def __lt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount < other.amount

    def __ge__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount >= other.amount

    def is_zero(self) -> bool:
        return self.amount == 0

    def display(self) -> str:
        rounded = self.amount.quantize(_QUANTIZE_DISPLAY, rounding=ROUND_HALF_UP)
        prefix = {"USD": "$", "BRL": "R$", "EUR": "\u20ac"}
        return f"{prefix[self.currency]} {rounded:,.2f}"

    def convert(self, target_currency: Currency, rate: Decimal | float) -> Money:
        """Convert to another currency using the given exchange rate."""
        return Money(
            amount=(self.amount * Decimal(str(rate))).quantize(
                _QUANTIZE_INTERNAL, rounding=ROUND_HALF_UP
            ),
            currency=target_currency,
        )
