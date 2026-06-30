"""Portfolio API endpoints.

RESTful routes for portfolio management.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from arenawealth.api.dependencies import (
    PortfolioRepoDep,
    PortfolioServiceDep,
)
from arenawealth.api.dtos import (
    PortfolioAnalysisResponse,
    PortfolioCreateRequest,
    PortfolioMetrics,
    PortfolioResponse,
    PortfolioSummary,
    PortfolioUpdateRequest,
    RebalanceSuggestion,
)
from arenawealth.services.portfolio_service import (
    InsufficientCashError,
    PositionNotFoundError,
)

router = APIRouter(
    prefix="/api/v1/portfolios",
    tags=["portfolios"],
)

def _to_portfolio_response(portfolio) -> PortfolioResponse:
    """Convert model to response DTO."""
    return PortfolioResponse(
        id=portfolio.id,
        name=portfolio.name,
        description=portfolio.description,
        currency=portfolio.currency,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
        total_market_value=portfolio.total_market_value,
        total_cost_basis=portfolio.total_cost_basis,
        total_gain_loss=portfolio.total_market_value - portfolio.total_cost_basis,
        available_cash=portfolio.available_cash,
        position_count=0,
    )

@router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    request: PortfolioCreateRequest,
    repo: PortfolioRepoDep,
) -> PortfolioResponse:
    """Create new portfolio.

    Args:
        request: Portfolio creation data.
        repo: Portfolio repository.

    Returns:
        Created portfolio data.
    """
    portfolio = repo.create(
        name=request.name,
        currency=request.currency,
        initial_cash=request.initial_cash,
    )
    return _to_portfolio_response(portfolio)

@router.get("", response_model=list[PortfolioSummary])
def list_portfolios(repo: PortfolioRepoDep) -> list[PortfolioSummary]:
    """List all portfolios.

    Args:
        repo: Portfolio repository.

    Returns:
        List of portfolio summaries.
    """
    portfolios = repo.get_all()
    return [
        PortfolioSummary(
            id=portfolio.id,
            name=portfolio.name,
            currency=portfolio.currency,
            total_market_value=portfolio.total_market_value,
            total_gain_loss=portfolio.total_market_value - portfolio.total_cost_basis,
            position_count=0,
        )
        for portfolio in portfolios
    ]

@router.get("/{portfolio_id}", response_model=PortfolioResponse)
def get_portfolio(
    portfolio_id: int,
    repo: PortfolioRepoDep,
) -> PortfolioResponse:
    """Get portfolio by ID.

    Args:
        portfolio_id: Portfolio identifier.
        repo: Portfolio repository.

    Returns:
        Portfolio data.

    Raises:
        HTTPException: 404 if portfolio not found.
    """
    portfolio = repo.get_by_id(portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )
    return _to_portfolio_response(portfolio)

@router.patch("/{portfolio_id}", response_model=PortfolioResponse)
def update_portfolio(
    portfolio_id: int,
    request: PortfolioUpdateRequest,
    repo: PortfolioRepoDep,
) -> PortfolioResponse:
    """Update portfolio metadata.

    Args:
        portfolio_id: Portfolio identifier.
        request: Update data.
        repo: Portfolio repository.

    Returns:
        Updated portfolio data.

    Raises:
        HTTPException: 404 if portfolio not found.
    """
    update_data = request.model_dump(exclude_unset=True)
    portfolio = repo.update(portfolio_id, **update_data)

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    return _to_portfolio_response(portfolio)

@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(
    portfolio_id: int,
    repo: PortfolioRepoDep,
) -> None:
    """Delete portfolio.

    Args:
        portfolio_id: Portfolio identifier.
        repo: Portfolio repository.

    Raises:
        HTTPException: 404 if portfolio not found.
    """
    deleted = repo.delete(portfolio_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

@router.get("/{portfolio_id}/analysis", response_model=PortfolioAnalysisResponse)
def analyze_portfolio(
    portfolio_id: int,
    service: PortfolioServiceDep,
) -> PortfolioAnalysisResponse:
    """Get portfolio analysis.

    Args:
        portfolio_id: Portfolio identifier.
        service: Portfolio service.

    Returns:
        Analysis with metrics and suggestions.

    Raises:
        HTTPException: 404 if portfolio not found.
    """
    try:
        valuation = service.get_portfolio_value(portfolio_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    pf = service._portfolio_repo.get_by_id(portfolio_id)
    if pf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    total_value = valuation["total_market_value"]
    total_cost = valuation["total_cost_basis"]
    unrealized = valuation["unrealized_gain"]

    gain_pct = (unrealized / total_cost * 100) if total_cost > 0 else Decimal("0")

    metrics = PortfolioMetrics(
        total_value=total_value,
        total_cost=total_cost,
        unrealized_gain=unrealized,
        unrealized_gain_percent=gain_pct,
        day_change=Decimal("0"),
        day_change_percent=Decimal("0"),
        diversification_score=Decimal("0"),
        concentration_risk="MEDIUM",
    )

    suggestions_raw = service.get_rebalance_suggestions(portfolio_id)
    suggestions = [
        RebalanceSuggestion(
            ticker=item["ticker"],
            current_weight=item["current_weight"],
            suggested_weight=item["target_weight"],
            action=item["action"],
            suggested_amount=item["suggested_amount"],
            reason=item["reason"],
        )
        for item in suggestions_raw
    ]

    return PortfolioAnalysisResponse(
        portfolio=_to_portfolio_response(pf),
        positions=[],
        metrics=metrics,
        rebalance_suggestions=suggestions,
        last_updated=valuation.get("last_updated") or pf.updated_at,
    )

@router.post("/{portfolio_id}/buy")
def buy_shares(
    portfolio_id: int,
    ticker: str,
    shares: Annotated[Decimal, Query(gt=0)],
    price: Annotated[Decimal, Query(gt=0)],
    name: str,
    service: PortfolioServiceDep,
    fees: Annotated[Decimal, Query(ge=0)] = Decimal("0"),
) -> dict:
    """Execute buy order for portfolio.

    Args:
        portfolio_id: Portfolio identifier.
        ticker: Security ticker.
        shares: Number of shares.
        price: Price per share.
        name: Security name.
        service: Portfolio service.
        fees: Transaction fees.

    Returns:
        Transaction confirmation.

    Raises:
        HTTPException: 400 for validation errors, 404 if not found.
    """
    try:
        position = service.buy_shares(
            portfolio_id=portfolio_id,
            ticker=ticker,
            name=name,
            shares=shares,
            price_per_share=price,
            fees=fees,
        )
        return {
            "status": "success",
            "action": "buy",
            "ticker": ticker,
            "shares": float(shares),
            "price": float(price),
            "position_id": position.id,
        }
    except InsufficientCashError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

@router.post("/{portfolio_id}/sell")
def sell_shares(
    portfolio_id: int,
    ticker: str,
    shares: Annotated[Decimal, Query(gt=0)],
    price: Annotated[Decimal, Query(gt=0)],
    service: PortfolioServiceDep,
    fees: Annotated[Decimal, Query(ge=0)] = Decimal("0"),
) -> dict:
    """Execute sell order for portfolio.

    Args:
        portfolio_id: Portfolio identifier.
        ticker: Security ticker.
        shares: Number of shares.
        price: Price per share.
        service: Portfolio service.
        fees: Transaction fees.

    Returns:
        Transaction confirmation.

    Raises:
        HTTPException: 400 for validation errors, 404 if not found.
    """
    try:
        position = service.sell_shares(
            portfolio_id=portfolio_id,
            ticker=ticker,
            shares=shares,
            price_per_share=price,
            fees=fees,
        )
        return {
            "status": "success",
            "action": "sell",
            "ticker": ticker,
            "shares": float(shares),
            "price": float(price),
            "position_closed": position is None,
        }
    except PositionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
