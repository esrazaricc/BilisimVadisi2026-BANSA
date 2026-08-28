import ast
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.finance_capability_registry import (
    FinanceCapabilityKind,
    matching_live_adapters,
    select_finance_capability,
)
from src.finance_live_contract import (
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
)


def _request():

    return LiveCalculationRequest(
        product_id=999,
        bank_name="Test Bank",
        product_name="Test Product",
        family_key="konut_finansmani",
        amount=Decimal("2000000"),
        maturity_months=36,
    )


def _verified(request=None):

    request = request or _request()

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
        source_kind="test_verified_source",
        source_url=(
            "https://example.test/calculator"
        ),
        checked_at=datetime.now(
            timezone.utc
        ),
    )


class MatchingAdapter:

    def can_handle(self, request):
        return True

    def calculate(self, request):
        return _verified(request)


class NonMatchingAdapter:

    def can_handle(self, request):
        return False


def test_live_adapter_has_priority():

    called = False

    def portable(request):
        nonlocal called
        called = True
        return _verified(request)

    selected = select_finance_capability(
        request=_request(),
        adapters=[MatchingAdapter()],
        portable_result_lookup=portable,
    )

    assert (
        selected.kind
        ==
        FinanceCapabilityKind.LIVE_CALCULATOR
    )

    assert isinstance(
        selected.provider,
        MatchingAdapter,
    )

    assert called is False


def test_verified_local_model_precedes_portable():

    request = _request()
    local = _verified(request)

    selected = select_finance_capability(
        request=request,
        adapters=[NonMatchingAdapter()],
        verified_local_model_lookup=(
            lambda value: local
        ),
        portable_result_lookup=(
            lambda value: _verified(value)
        ),
    )

    assert (
        selected.kind
        ==
        FinanceCapabilityKind.VERIFIED_LOCAL_MODEL
    )

    assert selected.resolved_result is local


def test_exact_portable_is_fallback():

    request = _request()
    portable = _verified(request)

    selected = select_finance_capability(
        request=request,
        adapters=[NonMatchingAdapter()],
        portable_result_lookup=(
            lambda value: portable
        ),
    )

    assert (
        selected.kind
        ==
        FinanceCapabilityKind.EXACT_PORTABLE_SNAPSHOT
    )

    assert (
        selected.resolved_result
        is portable
    )


def test_missing_capability_fails_closed():

    selected = select_finance_capability(
        request=_request(),
        adapters=[NonMatchingAdapter()],
        portable_result_lookup=(
            lambda value: None
        ),
    )

    assert (
        selected.kind
        ==
        FinanceCapabilityKind.NO_NUMERIC_CAPABILITY
    )

    assert selected.provider is None
    assert selected.resolved_result is None
    assert selected.reason


def test_multiple_live_matches_fail_closed():

    with pytest.raises(RuntimeError):

        matching_live_adapters(
            _request(),
            [
                MatchingAdapter(),
                MatchingAdapter(),
            ],
        )


def test_engine_uses_registry_and_keeps_exact_guard():

    path = Path(
        "src/finance_live_compare.py"
    )

    source = path.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        source,
        filename=str(path),
    )

    function = next(
        node
        for node in tree.body
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "compare_financing"
        )
    )

    body = (
        ast.get_source_segment(
            source,
            function,
        )
        or ""
    )

    assert (
        "FINANCE_CAPABILITY_REGISTRY_RUNTIME_V3"
        in body
    )

    assert (
        "select_finance_capability("
        in body
    )

    assert (
        "_portable_verified_scenario_result"
        in body
    )

    assert (
        "_find_adapter("
        not in body
    )

    assert (
        "result.is_exact_match"
        in body
    )
