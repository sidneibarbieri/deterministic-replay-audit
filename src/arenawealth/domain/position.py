"""A single holding in a portfolio - ticker, shares, cost basis, and current price."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, computed_field

from arenawealth.domain.money import Currency, Money


class Position(BaseModel, frozen=True):
    """Immutable snapshot of one holding.

    Core invariant: market_value, gain_loss, and gain_loss_pct are always
    consistent with shares * current_price and cost_basis.
    """

    ticker: str = Field(min_length=1, max_length=10)
    name: str
    shares: Decimal = Field(gt=0)
    cost_basis_per_share: Decimal = Field(ge=0)
    current_price: Decimal = Field(ge=0)
    currency: Currency = Currency.USD

    @computed_field  # type: ignore[prop-decorator]
    @property
    def market_value(self) -> Money:
        return Money(amount=self.shares * self.current_price, currency=self.currency)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cost_basis_total(self) -> Money:
        return Money(amount=self.shares * self.cost_basis_per_share, currency=self.currency)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gain_loss(self) -> Money:
        return self.market_value - self.cost_basis_total

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gain_loss_pct(self) -> Decimal:
        if self.cost_basis_total.is_zero():
            return Decimal("0")
        return (self.gain_loss.amount / self.cost_basis_total.amount) * 100
