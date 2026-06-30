"""Transaction repository implementation.

Handles all transaction-related database operations.
"""

from datetime import datetime
from decimal import Decimal

from sqlmodel import Session, desc, select

from arenawealth.models.database import Transaction


class TransactionRepository:
    """Repository for Transaction entity operations."""

    def __init__(self, session: Session) -> None:
        """Initialize with database session.

        Args:
            session: SQLModel session for database operations.
        """
        self._session = session

    def get_by_id(self, transaction_id: int) -> Transaction | None:
        """Retrieve transaction by ID.

        Args:
            transaction_id: Transaction identifier.

        Returns:
            Transaction instance or None if not found.
        """
        statement = select(Transaction).where(Transaction.id == transaction_id)
        return self._session.exec(statement).first()

    def get_by_portfolio(
        self,
        portfolio_id: int,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Transaction]:
        """Retrieve transactions for a portfolio.

        Args:
            portfolio_id: Portfolio identifier.
            limit: Maximum number of results (None for all).
            offset: Number of results to skip.

        Returns:
            List of transaction entities, ordered by execution date desc.
        """
        statement = (
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id)
            .order_by(desc(Transaction.executed_at))
        )

        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        return list(self._session.exec(statement).all())

    def get_by_ticker(
        self,
        portfolio_id: int,
        ticker: str,
    ) -> list[Transaction]:
        """Retrieve transactions for a specific ticker.

        Args:
            portfolio_id: Portfolio identifier.
            ticker: Security ticker symbol.

        Returns:
            List of transaction entities.
        """
        statement = (
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id)
            .where(Transaction.ticker == ticker.upper())
            .order_by(desc(Transaction.executed_at))
        )
        return list(self._session.exec(statement).all())

    def create(
        self,
        portfolio_id: int,
        ticker: str,
        transaction_type: str,
        shares: Decimal,
        price_per_share: Decimal,
        fees: Decimal = Decimal("0"),
        position_id: int | None = None,
        broker_order_id: str | None = None,
        notes: str | None = None,
    ) -> Transaction:
        """Create new transaction record.

        Args:
            portfolio_id: Portfolio identifier.
            ticker: Security ticker symbol.
            transaction_type: Type (BUY, SELL, DIVIDEND, SPLIT).
            shares: Number of shares.
            price_per_share: Price per share.
            fees: Transaction fees.
            position_id: Related position (optional).
            broker_order_id: Broker order reference (optional).
            notes: Additional notes (optional).

        Returns:
            Created transaction entity.
        """
        total_amount = (shares * price_per_share) + fees

        transaction = Transaction(
            portfolio_id=portfolio_id,
            position_id=position_id,
            ticker=ticker.upper(),
            transaction_type=transaction_type.upper(),
            shares=shares,
            price_per_share=price_per_share,
            total_amount=total_amount,
            fees=fees,
            broker_order_id=broker_order_id,
            notes=notes,
        )
        self._session.add(transaction)
        self._session.commit()
        self._session.refresh(transaction)
        return transaction

    def get_total_fees(
        self,
        portfolio_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> Decimal:
        """Calculate total fees paid.

        Args:
            portfolio_id: Portfolio identifier.
            start_date: Optional start filter.
            end_date: Optional end filter.

        Returns:
            Sum of all transaction fees.
        """
        statement = (
            select(Transaction.fees)
            .where(Transaction.portfolio_id == portfolio_id)
        )

        if start_date:
            statement = statement.where(Transaction.executed_at >= start_date)
        if end_date:
            statement = statement.where(Transaction.executed_at <= end_date)

        results = self._session.exec(statement).all()
        return sum(f for f in results if f)

    def get_trade_volume(
        self,
        portfolio_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> Decimal:
        """Calculate total trade volume.

        Args:
            portfolio_id: Portfolio identifier.
            start_date: Optional start filter.
            end_date: Optional end filter.

        Returns:
            Sum of all transaction amounts.
        """
        statement = (
            select(Transaction.total_amount)
            .where(Transaction.portfolio_id == portfolio_id)
        )

        if start_date:
            statement = statement.where(Transaction.executed_at >= start_date)
        if end_date:
            statement = statement.where(Transaction.executed_at <= end_date)

        results = self._session.exec(statement).all()
        return sum(t for t in results if t)
