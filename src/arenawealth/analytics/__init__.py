"""Analytics - moat and compounding scoring with deterministic deployment."""

from arenawealth.analytics.backtest import (
    BacktestComparison,
    BacktestResult,
    compare_backtests,
    normalize_weights,
    run_backtest,
)
from arenawealth.analytics.deployment import (
    FEE_PER_TRANCHE,
    MIN_ORDER_AMOUNT,
    TRANCHE_SIZE,
    ConcentrationLimits,
    FeeParameters,
    compute_order_fee,
    order_fee,
    plan_deployment,
)
from arenawealth.analytics.fundamentals import (
    DemoFundamentalsProvider,
    FinnhubFundamentalsProvider,
    FMPFundamentalsProvider,
    FundamentalsProvider,
    YahooFundamentalsProvider,
    build_fundamentals_provider,
)
from arenawealth.analytics.models import (
    DeploymentPlan,
    Fundamentals,
    FundamentalScore,
    Holding,
    Order,
    PositionAnalysis,
)
from arenawealth.analytics.portfolio_review import (
    AdditionReview,
    PortfolioReview,
    ReplacementReview,
    TrimReview,
    review_portfolio,
)
from arenawealth.analytics.price_backtest import (
    AlignedReturnSeries,
    PriceBacktestReport,
    PriceBacktestStudy,
    align_price_history,
    equal_weights,
    run_price_backtest,
    run_price_backtest_study,
    run_price_backtest_study_from_aligned_returns,
)
from arenawealth.analytics.scoring import analyze, score_fundamentals
from arenawealth.analytics.screening import CandidateAnalysis, screen_candidates
from arenawealth.analytics.sec_facts import (
    PointInTimeFact,
    annual_series_as_of,
    fact_entries,
    facts_available_as_of,
    latest_fact_as_of,
)
from arenawealth.analytics.snapshots import SnapshotProvider, load_snapshot, record_snapshot
from arenawealth.analytics.workflow import analyze_holdings, fetch_fundamentals

__all__ = [
    "FEE_PER_TRANCHE",
    "MIN_ORDER_AMOUNT",
    "TRANCHE_SIZE",
    "AdditionReview",
    "AlignedReturnSeries",
    "BacktestComparison",
    "BacktestResult",
    "CandidateAnalysis",
    "ConcentrationLimits",
    "DemoFundamentalsProvider",
    "DeploymentPlan",
    "FMPFundamentalsProvider",
    "FeeParameters",
    "FinnhubFundamentalsProvider",
    "FundamentalScore",
    "Fundamentals",
    "FundamentalsProvider",
    "Holding",
    "Order",
    "PointInTimeFact",
    "PortfolioReview",
    "PositionAnalysis",
    "PriceBacktestReport",
    "PriceBacktestStudy",
    "ReplacementReview",
    "SnapshotProvider",
    "TrimReview",
    "YahooFundamentalsProvider",
    "align_price_history",
    "analyze",
    "analyze_holdings",
    "annual_series_as_of",
    "build_fundamentals_provider",
    "compare_backtests",
    "compute_order_fee",
    "equal_weights",
    "fact_entries",
    "facts_available_as_of",
    "fetch_fundamentals",
    "latest_fact_as_of",
    "load_snapshot",
    "normalize_weights",
    "order_fee",
    "plan_deployment",
    "record_snapshot",
    "review_portfolio",
    "run_backtest",
    "run_price_backtest",
    "run_price_backtest_study",
    "run_price_backtest_study_from_aligned_returns",
    "score_fundamentals",
    "screen_candidates",
]
