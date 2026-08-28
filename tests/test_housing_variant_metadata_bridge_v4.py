from types import SimpleNamespace
from decimal import Decimal

from src.chatbot_answer_contract import (
    GroundedFinanceResult,
    build_grounded_answer_context,
)

import src.chatbot_finance_renderer as renderer


def _raw_result(
    *,
    product_id=3,
    bank="D\u00fcnya Kat\u0131l\u0131m",
    status="VERIFIED",
    exact=True,
    variants=(
        "yeni_konut",
        "2el_konut",
    ),
):

    return SimpleNamespace(

        request=SimpleNamespace(
            product_id=product_id,
            bank_name=bank,
            product_name="Konut Finansman\u0131",
            amount=Decimal("100000"),
            maturity_months=36,
        ),

        status=SimpleNamespace(
            value=status,
        ),

        profit_share_rate=Decimal(
            "2.99"
        ),

        monthly_installment=Decimal(
            "4573.55"
        ),

        total_repayment=Decimal(
            "164647.67"
        ),

        allocation_fee=None,
        mortgage_fee=None,
        appraisal_fee=None,
        total_fees=None,

        source_kind=(
            "official_live_calculator_endpoint"
        ),

        source_url=(
            "https://example.com"
        ),

        checked_at=None,

        reason=None,

        is_exact_match=exact,

        is_rankable=(
            status == "VERIFIED"
            and exact
        ),

        raw_output={
            "collapsed_housing_variants":
                list(
                    variants
                ),
            "secret_raw_field":
                "must_not_cross",
        },
    )


def _execution(
    result,
):

    return SimpleNamespace(
        question=(
            "100.000 TL 36 ay konut "
            "finansmanlarini karsilastir"
        ),
        route="finance_compare",
        status="completed",
        rag_result=None,
        finance_results=(
            result,
        ),
        missing_fields=(),
        reasons=(),
    )


def test_verified_exact_variant_keys_cross_grounding_boundary():

    context = (
        build_grounded_answer_context(
            _execution(
                _raw_result()
            )
        )
    )

    item = (
        context.finance_results[
            0
        ]
    )

    assert (
        item.presentation_variants
        ==
        (
            "yeni_konut",
            "2el_konut",
        )
    )

    assert not hasattr(
        item,
        "raw_output",
    )


def test_unverified_variant_keys_do_not_cross_boundary():

    context = (
        build_grounded_answer_context(
            _execution(
                _raw_result(
                    status="UNVERIFIED",
                    exact=False,
                )
            )
        )
    )

    item = (
        context.finance_results[
            0
        ]
    )

    assert (
        item.presentation_variants
        ==
        ()
    )

    assert (
        item.profit_share_rate
        is None
    )


def test_grounded_finance_result_default_is_backward_compatible():

    item = GroundedFinanceResult(
        product_id=1,
        bank_name="Bank",
        product_name="Product",
        status="UNVERIFIED",
        requested_amount=Decimal(
            "100000"
        ),
        requested_maturity_months=36,
        verified=False,
        exact_match=False,
        rankable=False,
        profit_share_rate=None,
        monthly_installment=None,
        total_repayment=None,
        allocation_fee=None,
        mortgage_fee=None,
        appraisal_fee=None,
        total_fees=None,
        source_kind=None,
        source_url=None,
        checked_at=None,
        reason=None,
    )

    assert (
        item.presentation_variants
        ==
        ()
    )


def test_renderer_builds_dunya_and_albaraka_sections():

    dunya_context = (
        build_grounded_answer_context(
            _execution(
                _raw_result()
            )
        )
    )

    dunya_items = (
        renderer
        ._hv4_items(
            dunya_context
        )
    )

    assert len(
        dunya_items
    ) == 1

    text = (
        renderer
        ._hv4_section(
            *dunya_items[0]
        )
    )

    assert (
        "Yeni / s\u0131f\u0131r konut"
        in text
    )

    assert (
        "\u0130kinci el konut"
        in text
    )


    albaraka_context = (
        build_grounded_answer_context(
            _execution(
                _raw_result(
                    product_id=97,
                    bank="Albaraka T\u00fcrk",
                    variants=(
                        "ilk_ev",
                        "mevcut_konut",
                    ),
                )
            )
        )
    )

    albaraka_items = (
        renderer
        ._hv4_items(
            albaraka_context
        )
    )

    assert len(
        albaraka_items
    ) == 1

    text = (
        renderer
        ._hv4_section(
            *albaraka_items[0]
        )
    )

    assert "\u0130lk Evim" in text

    assert (
        "2. ve sonraki konut"
        in text
    )
