"""Portfolio service - orchestrates complex portfolio operations.

Implements business logic and coordinates between repositories.
"""

from decimal import Decimal

from sqlmodel import Session

from arenawealth.models.database import Position
from arenawealth.repositories.portfolio_repository import PortfolioRepository
from arenawealth.repositories.position_repository import PositionRepository
from arenawealth.repositories.transaction_repository import TransactionRepository


class InsufficientCashError(Exception):
    """Raised when portfolio has insufficient cash for operation."""

    pass

class PositionNotFoundError(Exception):
    """Raised when position does not exist."""

    pass

class PortfolioService:
    """Service for portfolio business operations."""

    def __init__(
        self,
        session: Session,
        portfolio_repo: PortfolioRepository | None = None,
        position_repo: PositionRepository | None = None,
        transaction_repo: TransactionRepository | None = None,
    ) -> None:
        """Initialize service with dependencies.

        Args:
            session: Database session.
            portfolio_repo: Optional portfolio repository.
            position_repo: Optional position repository.
            transaction_repo: Optional transaction repository.
        """
        self._session = session
        self._portfolio_repo = portfolio_repo or PortfolioRepository(session)
        self._position_repo = position_repo or PositionRepository(session)
        self._transaction_repo = transaction_repo or TransactionRepository(session)

    def buy_shares(
        self,
        portfolio_id: int,
        ticker: str,
        name: str,
        shares: Decimal,
        price_per_share: Decimal,
        fees: Decimal = Decimal("0"),
        isin: str | None = None,
    ) -> Position:
        """Execute buy operation - adds shares or creates position.

        Args:
            portfolio_id: Portfolio identifier.
            ticker: Security ticker symbol.
            name: Security name.
            shares: Number of shares to buy.
            price_per_share: Purchase price per share.
            fees: Transaction fees.
            isin: ISIN code (optional).

        Returns:
            Updated or created position.

        Raises:
            InsufficientCashError: If portfolio lacks cash for purchase.
            ValueError: If shares or price is not positive.
        """
        if shares <= 0:
            raise ValueError("Shares must be positive")
        if price_per_share <= 0:
            raise ValueError("Price must be positive")

        total_cost = (shares * price_per_share) + fees

        portfolio = self._portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        if portfolio.available_cash < total_cost:
            raise InsufficientCashError(
                f"Cash available: {portfolio.available_cash}, required: {total_cost}"
            )

        existing_position = self._position_repo.get_by_ticker(portfolio_id, ticker)

        if existing_position:
            position = self._position_repo.add_shares(
                existing_position.id,
                shares,
                price_per_share,
            )
            position_id = existing_position.id
        else:
            position = self._position_repo.create(
                portfolio_id=portfolio_id,
                ticker=ticker,
                name=name,
                shares=shares,
                average_cost_basis=price_per_share,
                current_price=price_per_share,
                isin=isin,
            )
            position_id = position.id

        self._transaction_repo.create(
            portfolio_id=portfolio_id,
            ticker=ticker,
            transaction_type="BUY",
            shares=shares,
            price_per_share=price_per_share,
            fees=fees,
            position_id=position_id,
        )

        new_cash_balance = portfolio.available_cash - total_cost
        self._portfolio_repo.update(portfolio_id, available_cash=new_cash_balance)

        self._portfolio_repo.recalculate_totals(portfolio_id)

        return position

    def sell_shares(
        self,
        portfolio_id: int,
        ticker: str,
        shares: Decimal,
        price_per_share: Decimal,
        fees: Decimal = Decimal("0"),
    ) -> Position | None:
        """Execute sell operation - removes shares and adds cash.

        Args:
            portfolio_id: Portfolio identifier.
            ticker: Security ticker symbol.
            shares: Number of shares to sell.
            price_per_share: Sale price per share.
            fees: Transaction fees.

        Returns:
            Updated position or None if fully closed.

        Raises:
            PositionNotFoundError: If position does not exist.
            ValueError: If shares or price is not positive.
        """
        if shares <= 0:
            raise ValueError("Shares must be positive")
        if price_per_share <= 0:
            raise ValueError("Price must be positive")

        position = self._position_repo.get_by_ticker(portfolio_id, ticker)
        if position is None:
            raise PositionNotFoundError(
                f"Position for {ticker} not found in portfolio {portfolio_id}"
            )

        if position.shares < shares:
            raise ValueError(f"Cannot sell {shares} shares, only {position.shares} available")

        proceeds = (shares * price_per_share) - fees

        updated_position = self._position_repo.remove_shares(position.id, shares)

        self._transaction_repo.create(
            portfolio_id=portfolio_id,
            ticker=ticker,
            transaction_type="SELL",
            shares=shares,
            price_per_share=price_per_share,
            fees=fees,
            position_id=position.id if updated_position else None,
        )

        portfolio = self._portfolio_repo.get_by_id(portfolio_id)
        new_cash_balance = portfolio.available_cash + proceeds
        self._portfolio_repo.update(portfolio_id, available_cash=new_cash_balance)

        self._portfolio_repo.recalculate_totals(portfolio_id)

        return updated_position

    def update_prices(self, portfolio_id: int, price_map: dict[str, Decimal]) -> int:
        """Update current prices for multiple positions.

        Args:
            portfolio_id: Portfolio identifier.
            price_map: Dictionary mapping tickers to prices.

        Returns:
            Number of positions updated.
        """
        positions = self._position_repo.get_by_portfolio(portfolio_id)
        updated_count = 0

        for position in positions:
            ticker = position.ticker.upper()
            if ticker in price_map:
                new_price = price_map[ticker]
                self._position_repo.update_price(position.id, new_price)
                updated_count += 1

        if updated_count > 0:
            self._portfolio_repo.recalculate_totals(portfolio_id)

        return updated_count

    def get_portfolio_value(self, portfolio_id: int) -> dict:
        """Calculate portfolio valuation.

        Args:
            portfolio_id: Portfolio identifier.

        Returns:
            Dictionary with value breakdown.
        """
        portfolio = self._portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        positions = self._position_repo.get_by_portfolio(portfolio_id)

        total_market_value = Decimal("0")
        total_cost_basis = Decimal("0")

        position_values = []
        for position in positions:
            market_value = position.shares * position.current_price
            cost_basis = position.shares * position.average_cost_basis
            total_market_value += market_value
            total_cost_basis += cost_basis

            position_values.append(
                {
                    "ticker": position.ticker,
                    "shares": position.shares,
                    "price": position.current_price,
                    "market_value": market_value,
                    "cost_basis": cost_basis,
                    "unrealized_pnl": market_value - cost_basis,
                    "unrealized_pnl_pct": (
                        ((market_value - cost_basis) / cost_basis * 100)
                        if cost_basis > 0
                        else Decimal("0")
                    ),
                }
            )

        unrealized_gain = total_market_value - total_cost_basis

        return {
            "portfolio_id": portfolio_id,
            "total_market_value": total_market_value,
            "total_cost_basis": total_cost_basis,
            "unrealized_gain": unrealized_gain,
            "unrealized_gain_percent": (
                (unrealized_gain / total_cost_basis * 100)
                if total_cost_basis > 0
                else Decimal("0")
            ),
            "available_cash": portfolio.available_cash,
            "total_value": total_market_value + portfolio.available_cash,
            "position_count": len(positions),
            "positions": position_values,
        }

    def get_rebalance_suggestions(
        self,
        portfolio_id: int,
        target_weights: dict[str, Decimal] | None = None,
    ) -> list[dict]:
        """Generate rebalancing suggestions.

        Args:
            portfolio_id: Portfolio identifier.
            target_weights: Optional target allocations by ticker.

        Returns:
            List of suggestions with action and amounts.
        """
        valuation = self.get_portfolio_value(portfolio_id)
        total_value = valuation["total_market_value"]
        positions = valuation["positions"]

        if total_value == 0:
            return []

        suggestions = []
        position_count = len(positions)
        equal_weight = Decimal("100") / position_count if position_count > 0 else Decimal("0")

        for position_value in positions:
            ticker = position_value["ticker"]
            current_weight = (position_value["market_value"] / total_value) * 100

            if target_weights and ticker in target_weights:
                target = target_weights[ticker]
            else:
                target = equal_weight

            weight_diff = current_weight - target

            if abs(weight_diff) > 5:
                suggested_value = (target / 100) * total_value
                current_value = position_value["market_value"]
                action = "BUY" if weight_diff < 0 else "SELL"
                amount = abs(suggested_value - current_value)

                suggestions.append(
                    {
                        "ticker": ticker,
                        "current_weight": current_weight,
                        "target_weight": target,
                        "action": action,
                        "suggested_amount": amount,
                        "reason": f"Weight deviation: {weight_diff:+.1f}% from target",
                    }
                )

        return sorted(
            suggestions,
            key=lambda suggestion: abs(
                suggestion["current_weight"] - suggestion["target_weight"]
            ),
            reverse=True,
        )
