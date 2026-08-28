from datetime import datetime, timezone
from decimal import Decimal

import pytest

import src.finance_verified_resolver as resolver
from src.finance_live_contract import (
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
)


def _request():
    return LiveCalculationRequest(
        product_id=999,
        bank_name="Test Bank",
        product_name="Test Finance",
        family_key="konut_finansmani",
        amount=Decimal("2000000"),
        maturity_months=36,
    )


def _verified():
    request = _request()

    return LiveCalculationResult(
        request=request,
        status=LiveCalculationStatus.VERIFIED,
        calculated_amount=request.amount,
        calculated_maturity_months=(
            request.maturity_months
        ),
        profit_share_rate=Decimal("3.00"),
        monthly_installment=Decimal("90000"),
        total_repayment=Decimal("3240000"),
        source_kind=(
            "official_live_calculator_endpoint"
        ),
        source_url=(
            "https://example.test/calculator"
        ),
        checked_at=datetime.now(
            timezone.utc
        ),
    )


def _unverified():
    return LiveCalculationResult(
        request=_request(),
        status=LiveCalculationStatus.UNVERIFIED,
        reason="No verified pricing capability.",
    )


def test_resolver_delegates_one_common_request(
    monkeypatch,
):
    captured = {}

    def fake_compare_financing(**kwargs):
        captured.update(kwargs)
        return [_verified()]

    monkeypatch.setattr(
        resolver,
        "_compare_financing_engine",
        fake_compare_financing,
    )

    results = resolver.resolve_finance_results(
        family="konut_finansmani",
        amount=Decimal("2000000"),
        maturity=36,
        scope="bireysel",
        bank_names=["Test Bank"],
    )

    assert len(results) == 1
    assert results[0].is_rankable

    assert (
        captured["family"]
        ==
        "konut_finansmani"
    )

    assert (
        Decimal(
            str(
                captured["amount"]
            )
        )
        ==
        Decimal("2000000")
    )

    assert captured["maturity"] == 36

    assert captured["bank_names"] == [
        "Test Bank"
    ]


def test_verified_result_must_match_exact_request(
    monkeypatch,
):
    request = _request()

    bad = LiveCalculationResult(
        request=request,
        status=LiveCalculationStatus.VERIFIED,
        calculated_amount=Decimal("100000"),
        calculated_maturity_months=36,
        profit_share_rate=Decimal("3.00"),
        monthly_installment=Decimal("5000"),
        total_repayment=Decimal("180000"),
        source_kind=(
            "official_live_calculator_endpoint"
        ),
        source_url=(
            "https://example.test/calculator"
        ),
        checked_at=datetime.now(
            timezone.utc
        ),
    )

    monkeypatch.setattr(
        resolver,
        "_compare_financing_engine",
        lambda **kwargs: [bad],
    )

    with pytest.raises(
        ValueError,
    ):
        resolver.resolve_finance_results(
            family="konut_finansmani",
            amount=Decimal("2000000"),
            maturity=36,
        )


def test_nonverified_numeric_leak_is_rejected(
    monkeypatch,
):
    request = _request()

    leaked = LiveCalculationResult(
        request=request,
        status=LiveCalculationStatus.UNVERIFIED,
        profit_share_rate=Decimal("3.00"),
        monthly_installment=Decimal("90000"),
        total_repayment=Decimal("3240000"),
        reason="Should fail closed.",
    )

    monkeypatch.setattr(
        resolver,
        "_compare_financing_engine",
        lambda **kwargs: [leaked],
    )

    with pytest.raises(
        ValueError,
    ):
        resolver.resolve_finance_results(
            family="konut_finansmani",
            amount=Decimal("2000000"),
            maturity=36,
        )


def test_scenario_bridge_contains_only_verified():
    frame = (
        resolver
        .verified_results_to_scenario_frame(
            [
                _verified(),
                _unverified(),
            ]
        )
    )

    assert len(frame) == 1

    row = frame.iloc[0]

    assert row["product_id"] == 999

    assert (
        Decimal(
            str(
                row["input_amount"]
            )
        )
        ==
        Decimal("2000000")
    )

    assert (
        row[
            "input_maturity_months"
        ]
        ==
        36
    )

    assert (
        row["scenario_status"]
        ==
        "verified_runtime_resolution"
    )

    assert (
        row["source_kind"]
        ==
        "official_live_calculator_endpoint"
    )


def test_unresolved_results_never_include_verified():
    values = resolver.unresolved_results(
        [
            _verified(),
            _unverified(),
        ]
    )

    assert len(values) == 1

    assert (
        values[0].status
        ==
        LiveCalculationStatus.UNVERIFIED
    )
