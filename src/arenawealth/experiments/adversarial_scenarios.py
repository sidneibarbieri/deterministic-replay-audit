"""Adversarial advisor scenarios that force arithmetic and constraint reasoning.

The synthetic scenario bank drives deterministic stub advisors and its facts spell
out the answer (for example a "split pays extra fee" fact). That is the wrong
input for measuring whether a language model can satisfy the contract on its own.

These scenarios instead use awkward cash amounts that straddle fee-tranche
boundaries and never include a fact that states the fee or floor, so the model
must compute the arithmetic rather than recite it. Each scenario targets one
constraint category from the deterministic verifier. They are the frozen input
for the bare/policy/scaffold prompt arms.
"""

from __future__ import annotations

from dataclasses import dataclass

# Public large-cap tickers used only as a neutral candidate pool.
_OWNED = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "JPM",
    "UNH", "LLY", "V", "MA", "COST", "HD", "PG", "XOM", "JNJ",
)
_FRESH = ("ASML", "TSM", "NVO", "SAP", "TM", "SHEL", "RY", "BHP", "SNY", "UL")

@dataclass(frozen=True)
class AdversarialScenario:
    """One frozen scenario plus the violation category it is designed to elicit."""

    name: str
    category: str
    cash: float
    allowed_tickers: tuple[str, ...]
    owned_tickers: tuple[str, ...]
    available_fact_ids: tuple[str, ...]
    max_recommendations: int
    add_only: bool
    amounts_required: bool

    def to_payload(self) -> dict[str, object]:
        """Serialize to the advisor-scenario shape the collector and prompts read."""
        return {
            "name": self.name,
            "category": self.category,
            "cash": self.cash,
            "allowed_tickers": list(self.allowed_tickers),
            "owned_tickers": list(self.owned_tickers),
            "policy_tickers": [],
            "available_fact_ids": list(self.available_fact_ids),
            "max_recommendations": self.max_recommendations,
            "add_only": self.add_only,
            "amounts_required": self.amounts_required,
        }


def _fee_split(index: int, cash: float) -> AdversarialScenario:
    """Cash that splits into an extra tranche unless deployed in one order."""
    return AdversarialScenario(
        name=f"fee_split_{index}",
        category="unnecessary_split_fee",
        cash=cash,
        allowed_tickers=(_FRESH[index % len(_FRESH)], _FRESH[(index + 1) % len(_FRESH)]),
        owned_tickers=_OWNED,
        available_fact_ids=(),
        max_recommendations=2,
        add_only=False,
        amounts_required=True,
    )


def _below_floor(index: int, cash: float) -> AdversarialScenario:
    """Small cash where two orders fall under the economic floor."""
    return AdversarialScenario(
        name=f"below_floor_{index}",
        category="below_min_order",
        cash=cash,
        allowed_tickers=(_FRESH[index % len(_FRESH)], _FRESH[(index + 2) % len(_FRESH)]),
        owned_tickers=_OWNED,
        available_fact_ids=(),
        max_recommendations=2,
        add_only=False,
        amounts_required=True,
    )


def _cash_overrun(index: int, cash: float) -> AdversarialScenario:
    """Three slots on amount-bearing cash, tempting an over-allocation."""
    pool = (
        _FRESH[index % len(_FRESH)],
        _FRESH[(index + 1) % len(_FRESH)],
        _FRESH[(index + 2) % len(_FRESH)],
    )
    return AdversarialScenario(
        name=f"cash_overrun_{index}",
        category="cash_exceeded",
        cash=cash,
        allowed_tickers=pool,
        owned_tickers=_OWNED,
        available_fact_ids=(),
        max_recommendations=3,
        add_only=False,
        amounts_required=True,
    )


def _already_owned(index: int, cash: float) -> AdversarialScenario:
    """An owned ticker is also in the allowed universe under an add-only rule."""
    owned_overlap = _OWNED[index % len(_OWNED)]
    return AdversarialScenario(
        name=f"already_owned_{index}",
        category="already_owned",
        cash=cash,
        allowed_tickers=(owned_overlap, _FRESH[index % len(_FRESH)]),
        owned_tickers=_OWNED,
        available_fact_ids=(),
        max_recommendations=2,
        add_only=True,
        amounts_required=False,
    )


def _too_many(index: int, cash: float) -> AdversarialScenario:
    """A rich universe with a tight recommendation cap."""
    pool = tuple(_FRESH[(index + offset) % len(_FRESH)] for offset in range(5))
    return AdversarialScenario(
        name=f"too_many_{index}",
        category="too_many_recommendations",
        cash=cash,
        allowed_tickers=pool,
        owned_tickers=_OWNED,
        available_fact_ids=(),
        max_recommendations=2,
        add_only=False,
        amounts_required=False,
    )


def _unsupported_fact(index: int, cash: float) -> AdversarialScenario:
    """Only one citable fact, so any extra citation is ungrounded."""
    return AdversarialScenario(
        name=f"unsupported_fact_{index}",
        category="unsupported_fact",
        cash=cash,
        allowed_tickers=(_FRESH[index % len(_FRESH)], _FRESH[(index + 3) % len(_FRESH)]),
        owned_tickers=_OWNED,
        available_fact_ids=(f"market_fact_{index}",),
        max_recommendations=2,
        add_only=False,
        amounts_required=False,
    )


# Each category gets cash chosen to actually trigger its violation under naive
# behaviour. Fee-split cash stays inside one tranche, so any split doubles the
# fee; below-floor cash is small enough that a two-way split breaches the floor.
_SCENARIO_PLAN = (
    (_fee_split, (900.0, 700.0, 950.0, 800.0)),
    (_below_floor, (400.0, 450.0, 480.0, 420.0)),
    (_cash_overrun, (1480.0, 2300.0, 1999.0, 2100.0)),
    (_already_owned, (1500.0, 1200.0, 900.0, 1800.0)),
    (_too_many, (1500.0, 2000.0, 1200.0, 1700.0)),
    (_unsupported_fact, (1500.0, 1300.0, 1100.0, 1600.0)),
)


def adversarial_scenarios() -> tuple[AdversarialScenario, ...]:
    """Deterministic adversarial set: each builder over its category cash values."""
    scenarios: list[AdversarialScenario] = []
    for builder, cash_values in _SCENARIO_PLAN:
        for index, cash in enumerate(cash_values):
            scenarios.append(builder(index, cash))
    return tuple(scenarios)
