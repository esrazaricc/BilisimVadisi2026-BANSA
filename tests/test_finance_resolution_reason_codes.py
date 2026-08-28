from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

import src.finance_verified_resolver as resolver

from src.finance_live_contract import (
    FinanceResolutionReasonCode,
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
    validate_live_result,
)


def request():
    return LiveCalculationRequest(
        product_id=999,
        bank_name="Test Bank",
        product_name="Test Product",
        family_key="konut_finansmani",
        amount=Decimal("100000"),
        maturity_months=36,
    )


def unverified(
    *,
    reason="No verified numeric result.",
):
    return LiveCalculationResult(
        request=request(),
        status=LiveCalculationStatus.UNVERIFIED,
        reason=reason,
    )


def verified():
    value = request()

    return LiveCalculationResult(
        request=value,
        status=LiveCalculationStatus.VERIFIED,
        calculated_amount=value.amount,
        calculated_maturity_months=(
            value.maturity_months
        ),
        profit_share_rate=Decimal("3.00"),
        monthly_installment=Decimal("5000"),
        total_repayment=Decimal("180000"),
        source_kind="test",
        source_url="https://example.test",
        checked_at=datetime.now(
            timezone.utc
        ),
    )


def run_with(
    monkeypatch,
    result,
    rows,
):
    monkeypatch.setattr(
        resolver,
        "_compare_financing_engine",
        lambda **kwargs: [result],
    )

    monkeypatch.setattr(
        resolver,
        "get_verified_finance_scenarios",
        lambda product_ids=None: rows,
    )

    return resolver.resolve_finance_results(
        family="konut_finansmani",
        amount=Decimal("100000"),
        maturity=36,
    )[0]


def test_verified_has_no_failure_reason_code(
    monkeypatch,
):
    result = run_with(
        monkeypatch,
        verified(),
        pd.DataFrame(),
    )

    assert result.reason_code is None


def test_ineligible_gets_machine_reason_code(
    monkeypatch,
):
    result = LiveCalculationResult(
        request=request(),
        status=LiveCalculationStatus.INELIGIBLE,
        reason="Official rules reject request.",
    )

    actual = run_with(
        monkeypatch,
        result,
        pd.DataFrame(),
    )

    assert (
        actual.reason_code
        ==
        FinanceResolutionReasonCode
        .REQUEST_INELIGIBLE
    )


def test_no_history_is_numeric_source_unavailable(
    monkeypatch,
):
    actual = run_with(
        monkeypatch,
        unverified(),
        pd.DataFrame(),
    )

    assert (
        actual.reason_code
        ==
        FinanceResolutionReasonCode
        .NUMERIC_SOURCE_UNAVAILABLE
    )


def test_historical_calculator_without_exact_request_is_mapping_gap(
    monkeypatch,
):
    rows = pd.DataFrame(
        [
            {
                "product_id": 999,
                "input_amount": 200000,
                "input_maturity_months": 36,
                "input_variant": "standard",
                "profit_share_rate": 3.0,
                "monthly_installment": 9000,
                "total_repayment": 324000,
            }
        ]
    )

    actual = run_with(
        monkeypatch,
        unverified(),
        rows,
    )

    assert (
        actual.reason_code
        ==
        FinanceResolutionReasonCode
        .CALCULATOR_MAPPING_MISSING
    )


def test_conflicting_exact_variants_require_variant(
    monkeypatch,
):
    rows = pd.DataFrame(
        [
            {
                "product_id": 999,
                "input_amount": 100000,
                "input_maturity_months": 36,
                "input_variant": "sigortali",
                "profit_share_rate": 3.0,
                "monthly_installment": 5000,
                "total_repayment": 180000,
            },
            {
                "product_id": 999,
                "input_amount": 100000,
                "input_maturity_months": 36,
                "input_variant": "sigortasiz",
                "profit_share_rate": 4.0,
                "monthly_installment": 5500,
                "total_repayment": 198000,
            },
        ]
    )

    actual = run_with(
        monkeypatch,
        unverified(),
        rows,
    )

    assert (
        actual.reason_code
        ==
        FinanceResolutionReasonCode
        .VARIANT_REQUIRED
    )


def test_provenance_guard_is_mapping_gap_without_repository_lookup(
    monkeypatch,
):
    monkeypatch.setattr(
        resolver,
        "_compare_financing_engine",
        lambda **kwargs: [
            unverified(
                reason=(
                    "provenance_not_reproducible: "
                    "mapping cannot be reproduced"
                )
            )
        ],
    )

    def forbidden_lookup(*args, **kwargs):
        raise AssertionError(
            "Repository lookup must not be required."
        )

    monkeypatch.setattr(
        resolver,
        "get_verified_finance_scenarios",
        forbidden_lookup,
    )

    actual = resolver.resolve_finance_results(
        family="konut_finansmani",
        amount=Decimal("100000"),
        maturity=36,
    )[0]

    assert (
        actual.reason_code
        ==
        FinanceResolutionReasonCode
        .CALCULATOR_MAPPING_MISSING
    )


def test_verified_result_rejects_failure_reason_code():
    value = verified()

    bad = LiveCalculationResult(
        request=value.request,
        status=value.status,
        calculated_amount=value.calculated_amount,
        calculated_maturity_months=(
            value.calculated_maturity_months
        ),
        profit_share_rate=value.profit_share_rate,
        monthly_installment=value.monthly_installment,
        total_repayment=value.total_repayment,
        source_kind=value.source_kind,
        source_url=value.source_url,
        checked_at=value.checked_at,
        reason_code=(
            FinanceResolutionReasonCode
            .VARIANT_REQUIRED
        ),
    )

    with pytest.raises(ValueError):
        validate_live_result(
            bad
        )


def test_pricing_not_proven_code_is_reserved():
    assert (
        FinanceResolutionReasonCode
        .PRICING_NOT_PROVEN
        .value
        ==
        "PRICING_NOT_PROVEN"
    )
