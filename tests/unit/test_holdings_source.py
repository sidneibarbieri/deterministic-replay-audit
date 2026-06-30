import os
from pathlib import Path

from arenawealth.importers.holdings_source import latest_inbox_csv, resolve_holdings_path


def test_latest_inbox_csv_uses_newest_file(tmp_path: Path) -> None:
    older = tmp_path / "portfolio-older.csv"
    newer = tmp_path / "portfolio-newer.csv"
    older.write_text("ticker,shares,cost_basis_per_share\nAAPL,1,100\n")
    newer.write_text("ticker,shares,cost_basis_per_share\nMSFT,1,200\n")
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    assert latest_inbox_csv(tmp_path) == newer


def test_resolve_holdings_path_uses_preferred_file(tmp_path: Path) -> None:
    preferred = tmp_path / "manual.csv"
    preferred.write_text("ticker,shares,cost_basis_per_share\nAAPL,1,100\n")

    assert resolve_holdings_path(preferred) == preferred
