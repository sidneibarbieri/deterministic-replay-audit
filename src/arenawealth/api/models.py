"""API models - DTOs for request/response serialization."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PositionView(BaseModel):
    """Position as seen by the API/frontend."""

    ticker: str
    name: str
    shares: float
    cost_basis_per_share: float
    current_price: float
    market_value: float
    cost_basis_total: float
    gain_loss: float
    gain_loss_pct: float
    weight_pct: float
    currency: str

class QuoteView(BaseModel):
    """Quote data for a ticker."""

    ticker: str
    price: float
    change: float
    change_pct: float
    high_52w: float | None = None
    low_52w: float | None = None

class PortfolioSummary(BaseModel):
    """High-level portfolio metrics."""

    total_value: float
    total_cost_basis: float
    total_gain_loss: float
    total_gain_loss_pct: float
    position_count: int
    currency: str

class AllocationItem(BaseModel):
    """Single allocation slice (sector, country, etc)."""

    name: str
    value: float
    weight_pct: float

class DashboardData(BaseModel):
    """Complete dashboard response."""

    summary: PortfolioSummary
    positions: list[PositionView]
    quotes: list[QuoteView]
    allocation: list[AllocationItem] = Field(default_factory=list)
