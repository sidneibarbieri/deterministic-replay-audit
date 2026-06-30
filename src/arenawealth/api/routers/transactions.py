"""Transaction API endpoints.

Routes for viewing transaction history.
"""

from fastapi import APIRouter, HTTPException, status

from arenawealth.api.dependencies import PortfolioRepoDep, TransactionRepoDep
from arenawealth.api.dtos import TransactionResponse

router = APIRouter(
    prefix="/api/v1/portfolios/{portfolio_id}/transactions",
    tags=["transactions"],
)

def _to_transaction_response(transaction) -> TransactionResponse:
    """Convert model to response DTO."""
    return TransactionResponse(
        id=transaction.id,
        portfolio_id=transaction.portfolio_id,
        position_id=transaction.position_id,
        ticker=transaction.ticker,
        transaction_type=transaction.transaction_type,
        shares=transaction.shares,
        price_per_share=transaction.price_per_share,
        total_amount=transaction.total_amount,
        fees=transaction.fees,
        executed_at=transaction.executed_at,
        broker_order_id=transaction.broker_order_id,
        notes=transaction.notes,
    )

@router.get("", response_model=list[TransactionResponse])
def list_transactions(
    portfolio_id: int,
    transaction_repo: TransactionRepoDep,
    portfolio_repo: PortfolioRepoDep,
    limit: int | None = None,
    offset: int = 0,
) -> list[TransactionResponse]:
    """List transactions for portfolio.

    Args:
        portfolio_id: Portfolio identifier.
        transaction_repo: Transaction repository.
        portfolio_repo: Portfolio repository.
        limit: Maximum results to return.
        offset: Number of results to skip.

    Returns:
        List of transactions.

    Raises:
        HTTPException: 404 if portfolio not found.
    """
    portfolio = portfolio_repo.get_by_id(portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    transactions = transaction_repo.get_by_portfolio(portfolio_id, limit=limit, offset=offset)
    return [_to_transaction_response(t) for t in transactions]

@router.get("/ticker/{ticker}", response_model=list[TransactionResponse])
def get_transactions_by_ticker(
    portfolio_id: int,
    ticker: str,
    transaction_repo: TransactionRepoDep,
    portfolio_repo: PortfolioRepoDep,
) -> list[TransactionResponse]:
    """List transactions for specific ticker.

    Args:
        portfolio_id: Portfolio identifier.
        ticker: Security ticker.
        transaction_repo: Transaction repository.
        portfolio_repo: Portfolio repository.

    Returns:
        List of transactions for ticker.

    Raises:
        HTTPException: 404 if portfolio not found.
    """
    portfolio = portfolio_repo.get_by_id(portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    transactions = transaction_repo.get_by_ticker(portfolio_id, ticker)
    return [_to_transaction_response(t) for t in transactions]

@router.get("/summary/total-fees")
def get_total_fees(
    portfolio_id: int,
    transaction_repo: TransactionRepoDep,
    portfolio_repo: PortfolioRepoDep,
) -> dict:
    """Get total fees paid.

    Args:
        portfolio_id: Portfolio identifier.
        transaction_repo: Transaction repository.
        portfolio_repo: Portfolio repository.

    Returns:
        Total fees paid.

    Raises:
        HTTPException: 404 if portfolio not found.
    """
    portfolio = portfolio_repo.get_by_id(portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    total_fees = transaction_repo.get_total_fees(portfolio_id)
    return {
        "portfolio_id": portfolio_id,
        "total_fees": float(total_fees),
        "currency": portfolio.currency,
    }

@router.get("/summary/trade-volume")
def get_trade_volume(
    portfolio_id: int,
    transaction_repo: TransactionRepoDep,
    portfolio_repo: PortfolioRepoDep,
) -> dict:
    """Get total trade volume.

    Args:
        portfolio_id: Portfolio identifier.
        transaction_repo: Transaction repository.
        portfolio_repo: Portfolio repository.

    Returns:
        Total trade volume.

    Raises:
        HTTPException: 404 if portfolio not found.
    """
    portfolio = portfolio_repo.get_by_id(portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    volume = transaction_repo.get_trade_volume(portfolio_id)
    return {
        "portfolio_id": portfolio_id,
        "trade_volume": float(volume),
        "currency": portfolio.currency,
    }
