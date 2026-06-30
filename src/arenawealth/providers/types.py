"""Shared types for provider results - DTOs that cross the provider boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class QuoteResult:
    ticker: str
    price: Decimal
    change: Decimal
    change_pct: Decimal
    high_52w: Decimal | None = None
    low_52w: Decimal | None = None
    volume: int | None = None
    timestamp: datetime | None = None
    provider_id: str = ""
