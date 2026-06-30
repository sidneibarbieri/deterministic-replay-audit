"""Resolve the canonical holdings CSV for local analysis."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INBOX = ROOT / "data" / "inbox"
PRIVATE_HOLDINGS = ROOT / "data" / "carteira_atual.csv"
FIXTURE_HOLDINGS = ROOT / "tests" / "fixtures" / "seed_portfolio_broker.csv"


def holdings_inbox() -> Path:
    configured = os.getenv("ACTIONAUDIT_PORTFOLIO_INBOX") or os.getenv(
        "ARENAWEALTH_PORTFOLIO_INBOX"
    )
    return Path(configured or str(DEFAULT_INBOX)).expanduser()


MANUAL_PORTFOLIO_NAME = "manual-portfolio.csv"


def latest_inbox_csv(directory: Path | None = None, include_manual: bool = True) -> Path | None:
    inbox = directory or holdings_inbox()
    if not inbox.exists():
        return None
    candidates = [
        path
        for path in inbox.glob("*.csv")
        if path.is_file() and (include_manual or path.name != MANUAL_PORTFOLIO_NAME)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def manual_portfolio_path() -> Path:
    return holdings_inbox() / MANUAL_PORTFOLIO_NAME


def resolve_holdings_path(preferred: Path | None = None) -> Path:
    if preferred and preferred.exists():
        return preferred

    inbox_csv = latest_inbox_csv()
    if inbox_csv:
        return inbox_csv

    if PRIVATE_HOLDINGS.exists():
        return PRIVATE_HOLDINGS

    return FIXTURE_HOLDINGS
