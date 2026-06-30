"""Command line entry point for moat and compounding analysis.

Loads holdings from a CSV, fetches live fundamentals through the analytics
package, scores each position, and prints a deterministic deployment plan.

    python scripts/moat_compounding_analysis.py --cash 1500.00
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from arenawealth.analytics import (
    DemoFundamentalsProvider,
    DeploymentPlan,
    FundamentalsProvider,
    Holding,
    PositionAnalysis,
    analyze_holdings,
    build_fundamentals_provider,
    plan_deployment,
)
from arenawealth.analytics.scoring import COMPOUNDING_WEIGHT, MOAT_WEIGHT, VALUATION_WEIGHT
from arenawealth.analytics.universe import FINANCIAL_TICKERS, THEME_BY_TICKER

HOLDINGS_CSV = Path("data/carteira_atual.csv")
EXPORT_DIR = Path("exports")


def load_holdings(path: Path) -> tuple[Holding, ...]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    holdings = []
    for row in rows:
        ticker = row["ticker"].strip().upper()
        holdings.append(
            Holding(
                ticker=ticker,
                name=row["name"].strip(),
                shares=float(row["shares"]),
                average_cost=float(row["cost_basis_per_share"]),
                broker_price=float(row["current_price"]),
                theme=THEME_BY_TICKER.get(ticker, "Other"),
                is_financial=ticker in FINANCIAL_TICKERS,
            )
        )
    return tuple(holdings)


def percent(value: float | None, decimals: int = 1) -> str:
    return f"{value * 100:.{decimals}f}%" if value is not None else "n/a"


def number(value: float | None, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}" if value is not None else "n/a"


def render_report(analyses: Sequence[PositionAnalysis], plan: DeploymentPlan, cash: float) -> None:
    total_market_value = sum(analysis.market_value for analysis in analyses)
    ranked = sorted(analyses, key=lambda analysis: analysis.composite_score, reverse=True)

    print("=" * 96)
    print(f"MOAT + COMPOUNDING ANALYSIS   {datetime.now():%Y-%m-%d %H:%M}")
    print(
        f"Holdings {total_market_value:,.0f}  Cash {cash:,.2f}  "
        f"Total {total_market_value + cash:,.0f}"
    )
    print(
        f"Weights  Moat {MOAT_WEIGHT:.0%}  Compounding {COMPOUNDING_WEIGHT:.0%}  "
        f"Valuation {VALUATION_WEIGHT:.0%}"
    )
    print("=" * 96)
    print(
        f"{'TKR':<6}{'Wt%':>6}{'P&L%':>8}  {'MOAT':<10}{'COMPOUND':<12}"
        f"{'ROIC':>6}{'EPSg':>6}{'FCFg':>6}{'fPE':>6}  {'TOT':>5}"
    )
    print("-" * 96)
    for analysis in ranked:
        return_metric = analysis.roic if analysis.roic is not None else analysis.roe
        print(
            f"{analysis.holding.ticker:<6}{analysis.weight_pct:>6.1f}{analysis.pnl_pct:>8.1f}  "
            f"{analysis.moat_class:<10}{analysis.compounding_class:<12}"
            f"{percent(return_metric, 0):>6}{percent(analysis.eps_cagr, 0):>6}"
            f"{percent(analysis.fcf_cagr, 0):>6}{number(analysis.forward_pe, 0):>6}  "
            f"{analysis.composite_score:>5.0f}"
        )

    print("\n" + "=" * 96)
    print(f"DETERMINISTIC DEPLOYMENT for {cash:,.2f}")
    print("=" * 96)
    print(f"Excluded as overweight: {', '.join(plan.excluded_overweight) or 'none'}")
    print(f"Excluded by theme rule: {', '.join(plan.excluded_theme) or 'none'}")
    candidates = ", ".join(f"{ticker}({score:.0f})" for ticker, score in plan.top_candidates)
    print(f"Top eligible: {candidates}")
    print()
    for order in plan.orders:
        print(
            f"  BUY {order.ticker:<6}{order.amount:>9.2f}  "
            f"{order.shares:>9.4f} sh  fee {order.fee:.2f}"
        )
    deployed = sum(order.amount for order in plan.orders)
    fee_pct = (plan.total_fee / deployed * 100) if deployed > 0 else 0.0
    print(
        f"  TOTAL {deployed:>9.2f}  fee {plan.total_fee:.2f} "
        f"({fee_pct:.2f}%)  cash left {cash - deployed:.2f}"
    )


def write_snapshot(
    analyses: Sequence[PositionAnalysis], plan: DeploymentPlan, cash: float
) -> Path:
    EXPORT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    ranked = sorted(analyses, key=lambda analysis: analysis.composite_score, reverse=True)
    payload = {
        "generated_utc": stamp,
        "cash": cash,
        "weights": {
            "moat": MOAT_WEIGHT,
            "compounding": COMPOUNDING_WEIGHT,
            "valuation": VALUATION_WEIGHT,
        },
        "positions": [
            {
                "ticker": analysis.holding.ticker,
                "theme": analysis.holding.theme,
                "weight_pct": analysis.weight_pct,
                "pnl_pct": analysis.pnl_pct,
                "moat_class": analysis.moat_class,
                "compounding_class": analysis.compounding_class,
                "composite_score": analysis.composite_score,
            }
            for analysis in ranked
        ],
        "orders": [
            {
                "ticker": order.ticker,
                "amount": order.amount,
                "shares": order.shares,
                "fee": order.fee,
            }
            for order in plan.orders
        ],
    }
    path = EXPORT_DIR / f"moat_compounding_{stamp}.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Moat and compounding portfolio analysis.")
    parser.add_argument("--cash", type=float, default=1500.00, help="Cash available to deploy.")
    parser.add_argument("--holdings", type=Path, default=HOLDINGS_CSV, help="Holdings CSV path.")
    parser.add_argument(
        "--offline-demo",
        action="store_true",
        help="Use deterministic demo fundamentals instead of live market data.",
    )
    return parser.parse_args()


def select_provider(
    arguments: argparse.Namespace, holdings: Sequence[Holding]
) -> FundamentalsProvider:
    if arguments.offline_demo:
        return DemoFundamentalsProvider(holdings)
    return build_fundamentals_provider()


def main() -> None:
    load_dotenv()  # makes optional API keys (e.g. FMP) available when present
    arguments = parse_arguments()
    holdings = load_holdings(arguments.holdings)
    provider = select_provider(arguments, holdings)

    analyses = analyze_holdings(holdings, provider)
    plan = plan_deployment(analyses, arguments.cash)
    render_report(analyses, plan, arguments.cash)
    snapshot = write_snapshot(analyses, plan, arguments.cash)
    print(f"\nSnapshot {snapshot}")


if __name__ == "__main__":
    main()
