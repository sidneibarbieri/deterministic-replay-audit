"""Pure fee contract shared by deployment and experiment provenance checks."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class FeeParameters:
    """Immutable parameters for the fixed fee per started tranche."""

    tranche_size_usd: float = 1000.0
    fee_per_tranche_usd: float = 2.50
    max_fee_impact_pct: float = 1.0

    @property
    def min_order_amount_usd(self) -> float:
        """Return the order size where the fixed fee reaches the tolerance."""
        return self.fee_per_tranche_usd / (self.max_fee_impact_pct / 100)


def compute_order_fee(amount_usd: float, fee_params: FeeParameters) -> float:
    """Return the fee for one order under the supplied tranche schedule."""
    if amount_usd <= 0:
        return 0.0
    tranches_used = math.ceil(amount_usd / fee_params.tranche_size_usd)
    return tranches_used * fee_params.fee_per_tranche_usd


_DEFAULT_FEE_PARAMS = FeeParameters()
MIN_ORDER_AMOUNT: float = _DEFAULT_FEE_PARAMS.min_order_amount_usd
TRANCHE_SIZE: float = _DEFAULT_FEE_PARAMS.tranche_size_usd
FEE_PER_TRANCHE: float = _DEFAULT_FEE_PARAMS.fee_per_tranche_usd


def order_fee(amount: float) -> float:
    """Return the fee for one order under the artifact's default schedule."""
    return compute_order_fee(amount, _DEFAULT_FEE_PARAMS)
