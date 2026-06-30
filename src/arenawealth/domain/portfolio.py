"""Portfolio - an ordered collection of Positions with aggregate analytics."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, computed_field

from arenawealth.domain.money import Currency, Money
from arenawealth.domain.position import Position


class Portfolio(BaseModel, frozen=True):
    """Immutable portfolio snapshot.

    Positions are stored in insertion order. All aggregate values (total_value,
    total_gain_loss, weight_pct) are derived - no stored state to desync.
    """

    positions: tuple[Position, ...] = Field(default=())
    cash_balance_amount: Decimal = Field(default=Decimal("0"))
    currency: Currency = Currency.USD

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cash_balance(self) -> Money:
        return Money(amount=self.cash_balance_amount, currency=self.currency)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_assets(self) -> Money:
        return self.total_value + self.cash_balance

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_value(self) -> Money:
        if not self.positions:
            return Money(amount=Decimal("0"), currency=self.currency)
        result = Money(amount=Decimal("0"), currency=self.currency)
        for position in self.positions:
            result = result + position.market_value
        return result

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_cost_basis(self) -> Money:
        if not self.positions:
            return Money(amount=Decimal("0"), currency=self.currency)
        result = Money(amount=Decimal("0"), currency=self.currency)
        for position in self.positions:
            result = result + position.cost_basis_total
        return result

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_gain_loss(self) -> Money:
        return self.total_value - self.total_cost_basis

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_gain_loss_pct(self) -> Decimal:
        if self.total_cost_basis.is_zero():
            return Decimal("0")
        return (self.total_gain_loss.amount / self.total_cost_basis.amount) * 100

    def weight_pct(self, ticker: str) -> Decimal:
        """Weight of a single position as percentage of total portfolio value."""
        if self.total_value.is_zero():
            return Decimal("0")
        position = self.get_position(ticker)
        if position is None:
            return Decimal("0")
        return (position.market_value.amount / self.total_value.amount) * 100

    def get_position(self, ticker: str) -> Position | None:
        normalized = ticker.upper().strip()
        for position in self.positions:
            if position.ticker == normalized:
                return position
        return None

    @property
    def tickers(self) -> list[str]:
        return [position.ticker for position in self.positions]

    def __len__(self) -> int:
        return len(self.positions)
