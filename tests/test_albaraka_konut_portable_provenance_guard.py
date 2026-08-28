from decimal import Decimal


from src.finance_live_compare import (
    _portable_verified_scenario_result,
)

from src.finance_live_contract import (
    LiveCalculationRequest,
    LiveCalculationStatus,
)


def _albaraka_konut_request(
    variant="mevcut_konut",
):
    return LiveCalculationRequest(
        product_id=97,
        bank_name="Albaraka T\u00fcrk",
        product_name="Konut Finansman\u0131",
        family_key="konut_finansmani",
        amount=Decimal("100000"),
        maturity_months=36,
        variant=variant,
    )


def test_mevcut_konut_historical_scenario_fails_closed():

    result = (
        _portable_verified_scenario_result(
            _albaraka_konut_request(
                "mevcut_konut"
            )
        )
    )

    assert result is not None

    assert (
        result.status
        == LiveCalculationStatus.UNVERIFIED
    )

    assert result.is_rankable is False
    assert result.is_exact_match is False

    assert result.profit_share_rate is None
    assert result.monthly_installment is None
    assert result.total_repayment is None

    assert result.allocation_fee is None
    assert result.mortgage_fee is None
    assert result.appraisal_fee is None
    assert result.total_fees is None

    assert result.source_url is None

    assert (
        "provenance_not_reproducible"
        in str(
            result.reason
            or ""
        )
    )


def test_ilk_ev_historical_scenario_fails_closed():

    result = (
        _portable_verified_scenario_result(
            _albaraka_konut_request(
                "ilk_ev"
            )
        )
    )

    assert (
        result.status
        == LiveCalculationStatus.UNVERIFIED
    )

    assert result.is_rankable is False
    assert result.profit_share_rate is None
    assert result.total_repayment is None
