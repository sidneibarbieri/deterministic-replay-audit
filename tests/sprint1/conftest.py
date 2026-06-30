import pytest


# Minimal conftest - no external dependencies
@pytest.fixture
def fee_params_standard():
    from arenawealth.analytics.deployment import FeeParameters
    return FeeParameters(
        tranche_size_usd=1000,
        fee_per_tranche_usd=2.50,
        min_order_amount=250,
    )

@pytest.fixture
def concentration_limits_standard():
    from arenawealth.analytics.deployment import ConcentrationLimits
    return ConcentrationLimits(
        theme_cap=20,
        overweight_multiple=1.3,
    )
