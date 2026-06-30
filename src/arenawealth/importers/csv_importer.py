"""CSV portfolio importer - flexible column mapping for any broker export.

Handles the common case: a user exports positions from a broker as CSV. Column
names are mapped via aliases so the user does not need to rename anything.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

import polars as pl

from arenawealth.domain.money import Currency
from arenawealth.domain.position import Position

TICKER_ALIASES = {"ticker", "symbol", "código", "codigo", "ativo", "stock"}
NAME_ALIASES = {"name", "nome", "description", "descrição", "descricao", "company"}
SHARES_ALIASES = {
    "shares",
    "quantity",
    "total_quantity",
    "available_quantity",
    "quantidade",
    "qtd",
    "qty",
    "cotas",
}
COST_BASIS_ALIASES = {
    "cost_basis",
    "cost_basis_per_share",
    "avg_price",
    "preco_medio",
    "preço_médio",
    "average_price",
    "custo_medio",
}
CURRENT_PRICE_ALIASES = {
    "current_price",
    "price",
    "last_price",
    "preco",
    "preço",
    "cotacao",
    "cotação",
}


def _find_column(columns: list[str], aliases: set[str]) -> str | None:
    normalized = {col.lower().strip().replace(" ", "_"): col for col in columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def import_csv(
    path: Path | str,
    currency: Currency = Currency.USD,
) -> list[Position]:
    """Import positions from a CSV file with flexible column detection."""
    dataframe = pl.read_csv(str(path), infer_schema_length=0)
    columns = dataframe.columns

    ticker_col = _find_column(columns, TICKER_ALIASES)
    name_col = _find_column(columns, NAME_ALIASES)
    shares_col = _find_column(columns, SHARES_ALIASES)
    cost_basis_col = _find_column(columns, COST_BASIS_ALIASES)
    current_price_col = _find_column(columns, CURRENT_PRICE_ALIASES)

    if ticker_col is None:
        raise ValueError(
            f"No ticker column found. Expected one of: {sorted(TICKER_ALIASES)}. "
            f"Found columns: {columns}"
        )
    if shares_col is None:
        raise ValueError(
            f"No shares column found. Expected one of: {sorted(SHARES_ALIASES)}. "
            f"Found columns: {columns}"
        )

    positions: list[Position] = []

    for row in dataframe.iter_rows(named=True):
        ticker = str(row[ticker_col]).upper().strip()
        if not ticker:
            continue

        name = str(row[name_col]).strip() if name_col else ticker

        try:
            shares = Decimal(str(row[shares_col]).replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError(
                f"Invalid shares value for {ticker}: {row[shares_col]}"
            ) from exc

        cost_basis = Decimal("0")
        if cost_basis_col and row[cost_basis_col]:
            raw = str(row[cost_basis_col]).replace(",", "").replace("$", "").strip()
            if raw:
                cost_basis = Decimal(raw)

        # current_price is optional: live pricing overrides it. When the column
        # is absent we fall back to cost basis so an offline snapshot reads flat
        # instead of -100%.
        current_price = cost_basis
        if current_price_col and row[current_price_col]:
            raw = str(row[current_price_col]).replace(",", "").replace("$", "").strip()
            if raw:
                current_price = Decimal(raw)

        positions.append(
            Position(
                ticker=ticker,
                name=name,
                shares=shares,
                cost_basis_per_share=cost_basis,
                current_price=current_price,
                currency=currency,
            )
        )

    return positions
