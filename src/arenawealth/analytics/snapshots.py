"""Timestamped fundamentals snapshots for reproducible, auditable analysis.

A snapshot freezes the fundamentals (and FX rates) used for a decision so the
exact run can be replayed offline. Replaying yields byte-identical scores, which
is how the determinism claim is verified and how decisions stay auditable.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, fields
from datetime import UTC, datetime
from pathlib import Path

from arenawealth.analytics.models import Fundamentals

SNAPSHOT_DIR = Path("data/snapshots")
_SERIES_FIELDS = {field.name for field in fields(Fundamentals) if field.name.endswith("_series")}


class SnapshotProvider:
    """Replay a recorded snapshot offline. No network, fully deterministic."""

    def __init__(
        self,
        fundamentals_by_ticker: dict[str, Fundamentals],
        fx_rates: dict[str, float] | None = None,
    ) -> None:
        self._fundamentals = fundamentals_by_ticker
        self._fx_rates = fx_rates or {}

    def get_fundamentals(self, ticker: str) -> Fundamentals:
        return self._fundamentals[ticker]

    def exchange_rate(self, base: str, quote: str) -> float:
        return self._fx_rates[f"{base}{quote}"]


def _to_dict(fund: Fundamentals) -> dict[str, object]:
    return asdict(fund)


def _from_dict(payload: dict[str, object]) -> Fundamentals:
    restored = {
        key: tuple(value) if key in _SERIES_FIELDS and value is not None else value
        for key, value in payload.items()
    }
    return Fundamentals(**restored)


def _required_fx_pairs(
    fundamentals_by_ticker: dict[str, Fundamentals],
) -> set[tuple[str, str]]:
    pairs = set()
    for fund in fundamentals_by_ticker.values():
        base = fund.financial_currency
        quote = fund.trading_currency
        if base and quote and base != quote:
            pairs.add((base, quote))
    return pairs


def record_snapshot(
    fundamentals_by_ticker: dict[str, Fundamentals],
    exchange_rate: Callable[[str, str], float],
    directory: Path = SNAPSHOT_DIR,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    captured = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    fx_rates = {
        f"{base}{quote}": exchange_rate(base, quote)
        for base, quote in _required_fx_pairs(fundamentals_by_ticker)
    }
    payload = {
        "captured_utc": captured,
        "fx_rates": fx_rates,
        "fundamentals": {
            ticker: _to_dict(fund) for ticker, fund in fundamentals_by_ticker.items()
        },
    }
    path = directory / f"snapshot_{captured}.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_snapshot(path: Path) -> SnapshotProvider:
    payload = json.loads(path.read_text())
    fundamentals = {
        ticker: _from_dict(data) for ticker, data in payload["fundamentals"].items()
    }
    fx_rates = {str(key): float(value) for key, value in payload.get("fx_rates", {}).items()}
    return SnapshotProvider(fundamentals, fx_rates)


def latest_snapshot_path(directory: Path = SNAPSHOT_DIR) -> Path | None:
    if not directory.exists():
        return None
    snapshots = sorted(directory.glob("snapshot_*.json"))
    return snapshots[-1] if snapshots else None
