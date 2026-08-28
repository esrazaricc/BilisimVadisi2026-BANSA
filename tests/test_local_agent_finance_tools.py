from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from src.local_agent_contract import (
    validate_agent_decision,
)

from src.local_agent_tools import (
    execute_agent_decision,
)

from src.finance_live_contract import (
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
)


def _products():

    return pd.DataFrame(
        [
            {
                "id": 1,
                "bank_name": "Albaraka T\u00fcrk",
                "product_name": "Konut Finansman\u0131",
                "product_family_key": "konut_finansmani",
                "scope": "bireysel",
            },
            {
                "id": 2,
                "bank_name": "D\u00fcnya Kat\u0131l\u0131m",
                "product_name": "Konut Finansman\u0131",
                "product_family_key": "konut_finansmani",
                "scope": "bireysel",
            },
        ]
    )


def _verified(
    product_id,
    bank,
    rate,
    installment,
    total,
):

    request = LiveCalculationRequest(
        product_id=product_id,
        bank_name=bank,
        product_name="Konut Finansman\u0131",
        family_key="konut_finansmani",
        amount=Decimal("200000"),
        maturity_months=36,
    )

    return LiveCalculationResult(
        request=request,
        status=LiveCalculationStatus.VERIFIED,
        calculated_amount=Decimal("200000"),
        calculated_maturity_months=36,
        profit_share_rate=Decimal(rate),
        monthly_installment=Decimal(installment),
        total_repayment=Decimal(total),
        allocation_fee=Decimal("1000"),
        source_kind="official_calculator",
        source_url="https://example.invalid/source",
        checked_at=datetime.now(
            timezone.utc
        ),
    )


def test_compare_finance_uses_existing_verified_engine():

    decision = validate_agent_decision(
        {
            "intent":
                "finance_compare",

            "banks": [
                "Albaraka T\u00fcrk",
                "D\u00fcnya Kat\u0131l\u0131m",
            ],

            "topic":
                "konut finansman\u0131",

            "product":
                "finansman",

            "amount":
                200000,

            "maturity_months":
                36,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    seen = {}

    def fake_compare(**kwargs):

        seen.update(
            kwargs
        )

        return [
            _verified(
                1,
                "Albaraka T\u00fcrk",
                "3.04",
                "9224.58",
                "332084.90",
            ),
            _verified(
                2,
                "D\u00fcnya Kat\u0131l\u0131m",
                "2.99",
                "9147.10",
                "329295.28",
            ),
        ]

    result = execute_agent_decision(
        decision,
        question=(
            "Albaraka T\u00fcrk ile "
            "D\u00fcnya Kat\u0131l\u0131m "
            "konut finansman\u0131n\u0131 "
            "200 bin TL ve 36 ay i\u00e7in "
            "kar\u015f\u0131la\u015ft\u0131r."
        ),
        finance_compare_fn=(
            fake_compare
        ),
        finance_products_fn=(
            _products
        ),
    )

    assert result.status == "ok"

    assert (
        result.tool_name
        ==
        "compare_finance"
    )

    assert (
        seen["family"]
        ==
        "konut_finansmani"
    )

    assert (
        seen["scope"]
        ==
        "bireysel"
    )

    assert (
        seen["bank_names"]
        ==
        (
            "Albaraka T\u00fcrk",
            "D\u00fcnya Kat\u0131l\u0131m",
        )
    )

    assert (
        result.data[
            "rankable_count"
        ]
        ==
        2
    )

    assert (
        result.data[
            "may_claim_finance_ranking"
        ]
        is True
    )

    assert (
        result.data[
            "evaluation"
        ][
            "ranking_allowed"
        ]
        is True
    )


def test_compare_finance_scope_is_inferred_from_catalog():

    decision = validate_agent_decision(
        {
            "intent":
                "finance_compare",

            "banks": [
                "Albaraka T\u00fcrk",
                "D\u00fcnya Kat\u0131l\u0131m",
            ],

            "topic":
                "konut finansman\u0131",

            "product":
                "finansman",

            "amount":
                200000,

            "maturity_months":
                36,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    def fake_compare(**kwargs):

        return [
            _verified(
                1,
                "Albaraka T\u00fcrk",
                "3.04",
                "9224.58",
                "332084.90",
            ),
            _verified(
                2,
                "D\u00fcnya Kat\u0131l\u0131m",
                "2.99",
                "9147.10",
                "329295.28",
            ),
        ]

    result = execute_agent_decision(
        decision,
        question=(
            "Albaraka T\u00fcrk ile "
            "D\u00fcnya Kat\u0131l\u0131m "
            "konut finansman\u0131n\u0131 "
            "200 bin TL ve 36 ay i\u00e7in "
            "kar\u015f\u0131la\u015ft\u0131r."
        ),
        finance_compare_fn=fake_compare,
        finance_products_fn=_products,
    )

    assert result.status == "ok"

    assert (
        result.data["scope"]
        ==
        "bireysel"
    )


def test_compare_finance_ambiguous_scope_fails_closed():

    products = _products()

    products = pd.concat(
        [
            products,
            pd.DataFrame(
                [
                    {
                        "id": 3,
                        "bank_name": "Albaraka T\u00fcrk",
                        "product_name": "Konut Ticari Test",
                        "product_family_key": "konut_finansmani",
                        "scope": "ticari",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    decision = validate_agent_decision(
        {
            "intent":
                "finance_compare",

            "banks": [
                "Albaraka T\u00fcrk",
                "D\u00fcnya Kat\u0131l\u0131m",
            ],

            "topic":
                "konut finansman\u0131",

            "product":
                "finansman",

            "amount":
                200000,

            "maturity_months":
                36,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    result = execute_agent_decision(
        decision,
        question=(
            "Albaraka T\u00fcrk ile "
            "D\u00fcnya Kat\u0131l\u0131m "
            "konut finansman\u0131n\u0131 "
            "kar\u015f\u0131la\u015ft\u0131r."
        ),
        finance_compare_fn=(
            lambda **kwargs: []
        ),
        finance_products_fn=(
            lambda: products
        ),
    )

    assert result.status == "fallback"

    assert (
        "finance_scope_ambiguous"
        in result.reasons
    )


def test_calculate_finance_uses_existing_engine_single_bank():

    decision = validate_agent_decision(
        {
            "intent":
                "finance_calculate",

            "banks": [
                "Albaraka T\u00fcrk",
            ],

            "topic":
                "konut finansman\u0131",

            "product":
                "finansman",

            "amount":
                200000,

            "maturity_months":
                36,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    seen = {}

    def fake_compare(**kwargs):

        seen.update(
            kwargs
        )

        return [
            _verified(
                1,
                "Albaraka T\u00fcrk",
                "3.04",
                "9224.58",
                "332084.90",
            )
        ]

    result = execute_agent_decision(
        decision,
        question=(
            "Albaraka T\u00fcrk "
            "Konut Finansman\u0131nda "
            "200 bin TL'yi 36 ay "
            "i\u00e7in hesapla."
        ),
        finance_compare_fn=(
            fake_compare
        ),
        finance_products_fn=(
            _products
        ),
    )

    assert result.status == "ok"

    assert (
        result.tool_name
        ==
        "calculate_finance"
    )

    assert (
        seen["family"]
        ==
        "konut_finansmani"
    )

    assert (
        seen["scope"]
        ==
        "bireysel"
    )

    assert (
        seen["bank_names"]
        ==
        (
            "Albaraka T\u00fcrk",
        )
    )

    assert (
        result.data[
            "rankable_count"
        ]
        ==
        1
    )

    assert (
        result.data[
            "may_use_financial_numbers"
        ]
        is True
    )

    assert (
        result.data[
            "may_claim_finance_ranking"
        ]
        is False
    )

    assert (
        result.data[
            "result"
        ][
            "verified"
        ]
        is True
    )

    assert (
        result.data[
            "result"
        ][
            "exact_match"
        ]
        is True
    )


def test_calculate_finance_unresolved_result_fails_closed():

    decision = validate_agent_decision(
        {
            "intent":
                "finance_calculate",

            "banks": [
                "Albaraka T\u00fcrk",
            ],

            "topic":
                "konut finansman\u0131",

            "product":
                "finansman",

            "amount":
                200000,

            "maturity_months":
                36,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    request = LiveCalculationRequest(
        product_id=1,
        bank_name="Albaraka T\u00fcrk",
        product_name="Konut Finansman\u0131",
        family_key="konut_finansmani",
        amount=Decimal("200000"),
        maturity_months=36,
    )

    unresolved = LiveCalculationResult(
        request=request,
        status=LiveCalculationStatus.UNVERIFIED,
        reason="not verified",
    )

    result = execute_agent_decision(
        decision,
        question=(
            "Albaraka T\u00fcrk "
            "Konut Finansman\u0131nda "
            "200 bin TL'yi 36 ay "
            "i\u00e7in hesapla."
        ),
        finance_compare_fn=(
            lambda **kwargs:
                [unresolved]
        ),
        finance_products_fn=(
            _products
        ),
    )

    assert result.status == "fallback"

    assert (
        "single_finance_result_not_unique_verified"
        in result.reasons
    )

