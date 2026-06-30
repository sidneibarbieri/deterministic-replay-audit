"""Database models and connection management."""

import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Field, Session, SQLModel, create_engine

ROOT = Path(__file__).resolve().parents[3]
DATABASE_PATH = Path(
    os.getenv("ACTIONAUDIT_DATABASE_PATH")
    or os.getenv("ARENAWEALTH_DATABASE_PATH")
    or str(ROOT / "data" / "actionaudit.db")
).expanduser()
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Portfolio(SQLModel, table=True):
    __tablename__ = "portfolios"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: str | None = None
    currency: str = Field(default="USD")
    created_at: datetime = Field(default_factory=utc_now_naive)
    updated_at: datetime = Field(default_factory=utc_now_naive)

    total_market_value: Decimal = Field(default=Decimal("0"))
    total_cost_basis: Decimal = Field(default=Decimal("0"))
    available_cash: Decimal = Field(default=Decimal("0"))


class Position(SQLModel, table=True):
    __tablename__ = "positions"

    id: int | None = Field(default=None, primary_key=True)
    portfolio_id: int = Field(foreign_key="portfolios.id", index=True)

    ticker: str = Field(index=True)
    name: str
    isin: str | None = None

    shares: Decimal = Field(decimal_places=8)
    average_cost_basis: Decimal = Field(decimal_places=4)
    current_price: Decimal = Field(default=Decimal("0"), decimal_places=4)

    opened_at: datetime = Field(default_factory=utc_now_naive)
    updated_at: datetime = Field(default_factory=utc_now_naive)

    @property
    def market_value(self) -> Decimal:
        """Calculate current market value."""
        return self.shares * self.current_price

    @property
    def cost_basis_total(self) -> Decimal:
        """Calculate total cost basis."""
        return self.shares * self.average_cost_basis

    @property
    def gain_loss(self) -> Decimal:
        """Calculate unrealized gain/loss."""
        return self.market_value - self.cost_basis_total

    @property
    def gain_loss_percent(self) -> Decimal:
        """Calculate gain/loss percentage."""
        if self.cost_basis_total == 0:
            return Decimal("0")
        return (self.gain_loss / self.cost_basis_total) * 100


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)
    portfolio_id: int = Field(foreign_key="portfolios.id", index=True)
    position_id: int | None = Field(foreign_key="positions.id")

    ticker: str = Field(index=True)
    transaction_type: str
    shares: Decimal = Field(decimal_places=8)
    price_per_share: Decimal = Field(decimal_places=4)
    total_amount: Decimal = Field(decimal_places=2)
    fees: Decimal = Field(default=Decimal("0"), decimal_places=2)

    executed_at: datetime = Field(default_factory=utc_now_naive)
    broker_order_id: str | None = None
    notes: str | None = None


class QuoteHistory(SQLModel, table=True):
    __tablename__ = "quote_history"

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    price: Decimal = Field(decimal_places=4)
    volume: int | None = None
    change_percent: Decimal | None = Field(default=None, decimal_places=4)
    recorded_at: datetime = Field(default_factory=utc_now_naive, index=True)

    high_52_week: Decimal | None = Field(default=None, decimal_places=4)
    low_52_week: Decimal | None = Field(default=None, decimal_places=4)


class DecisionLog(SQLModel, table=True):
    __tablename__ = "decision_logs"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now_naive, index=True)
    policy_version: str
    portfolio_source: str
    provider_mode: str
    cash: Decimal = Field(decimal_places=2)
    order_count: int
    total_order_amount: Decimal = Field(decimal_places=2)
    payload_json: str


def init_database() -> None:
    """Create tables if they do not exist."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    """Return a database session."""
    return Session(engine)


@event.listens_for(Portfolio, "before_update")
def update_portfolio_timestamp(_mapper, _connection, target: Portfolio) -> None:
    target.updated_at = utc_now_naive()


@event.listens_for(Position, "before_update")
def update_position_timestamp(_mapper, _connection, target: Position) -> None:
    target.updated_at = utc_now_naive()
