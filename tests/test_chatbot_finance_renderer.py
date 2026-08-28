from dataclasses import dataclass
from decimal import Decimal


from src.chatbot_answer_contract import (
    GroundedAnswerContext,
    GroundedFinanceResult,
)

from src.chatbot_finance_renderer import (
    render_finance_answer,
)


def item(
    *,
    product_id,
    bank,
    status,
    verified=False,
    exact=False,
    rankable=False,
    rate=None,
    monthly=None,
    total=None,
):

    return GroundedFinanceResult(
        product_id=product_id,
        bank_name=bank,
        product_name="Ihtiyac Finansmani",
        status=status,
        requested_amount=Decimal(
            "75000"
        ),
        requested_maturity_months=24,
        verified=verified,
        exact_match=exact,
        rankable=rankable,
        profit_share_rate=(
            rate
        ),
        monthly_installment=(
            monthly
        ),
        total_repayment=(
            total
        ),
        allocation_fee=None,
        mortgage_fee=None,
        appraisal_fee=None,
        total_fees=None,
        source_kind=None,
        source_url=None,
        checked_at=None,
        reason=None,
    )


def context(
    finance,
    *,
    may_numbers,
    may_rank,
):

    return GroundedAnswerContext(
        question="question",
        route="finance_compare",
        execution_status="completed",
        answer_mode="finance",
        may_generate_answer=True,
        may_claim_finance_ranking=(
            may_rank
        ),
        may_use_financial_numbers=(
            may_numbers
        ),
        evidence=tuple(),
        finance_results=tuple(
            finance
        ),
        missing_fields=tuple(),
        reasons=tuple(),
    )


def test_all_unverified_contains_no_financial_values():

    ctx = context(
        [
            item(
                product_id=4,
                bank="Dunya",
                status="UNVERIFIED",
            ),
            item(
                product_id=318,
                bank="Vakif",
                status="UNVERIFIED",
            ),
        ],
        may_numbers=False,
        may_rank=False,
    )

    rendered = render_finance_answer(
        ctx
    )

    assert (
        rendered.ranking_claimed
        is False
    )

    assert (
        rendered.numeric_product_ids
        == ()
    )

    assert (
        "75.000"
        not in rendered.text
    )

    assert (
        "128.866"
        not in rendered.text
    )


def test_one_verified_exposes_numbers_but_not_ranking():

    ctx = context(
        [
            item(
                product_id=318,
                bank="Vakif",
                status="VERIFIED",
                verified=True,
                exact=True,
                rankable=True,
                rate=Decimal("3.75"),
                monthly=Decimal(
                    "5369.42"
                ),
                total=Decimal(
                    "128866.02"
                ),
            ),
        ],
        may_numbers=True,
        may_rank=False,
    )

    rendered = render_finance_answer(
        ctx
    )

    assert (
        "5.369,42 TL"
        in rendered.text
    )

    assert (
        "128.866,02 TL"
        in rendered.text
    )

    assert (
        rendered.ranking_claimed
        is False
    )


def test_verified_plus_unverified_does_not_rank():

    ctx = context(
        [
            item(
                product_id=318,
                bank="Vakif",
                status="VERIFIED",
                verified=True,
                exact=True,
                rankable=True,
                total=Decimal(
                    "128866.02"
                ),
            ),
            item(
                product_id=4,
                bank="Dunya",
                status="UNVERIFIED",
            ),
        ],
        may_numbers=True,
        may_rank=False,
    )

    rendered = render_finance_answer(
        ctx
    )

    assert (
        rendered.ranking_claimed
        is False
    )

    assert (
        rendered.unresolved_product_ids
        == (4,)
    )


def test_two_verified_can_rank_only_by_total_repayment():

    ctx = context(
        [
            item(
                product_id=318,
                bank="Vakif",
                status="VERIFIED",
                verified=True,
                exact=True,
                rankable=True,
                total=Decimal(
                    "128866.02"
                ),
            ),
            item(
                product_id=273,
                bank="Emlak",
                status="VERIFIED",
                verified=True,
                exact=True,
                rankable=True,
                total=Decimal(
                    "131171.63"
                ),
            ),
        ],
        may_numbers=True,
        may_rank=True,
    )

    rendered = render_finance_answer(
        ctx
    )

    assert (
        rendered.ranking_claimed
        is True
    )

    assert (
        rendered.ranking_metric
        == "total_repayment"
    )

    assert (
        "128.866,02 TL"
        in rendered.text
    )


def test_unverified_fake_numbers_are_not_rendered():

    # Even if a malformed upstream object
    # somehow carries numbers, renderer
    # must ignore them unless verified,
    # exact and rankable are all true.
    ctx = context(
        [
            item(
                product_id=4,
                bank="Dunya",
                status="UNVERIFIED",
                verified=False,
                exact=False,
                rankable=False,
                rate=Decimal("99"),
                monthly=Decimal("1"),
                total=Decimal("2"),
            ),
        ],
        may_numbers=False,
        may_rank=False,
    )

    rendered = render_finance_answer(
        ctx
    )

    assert (
        "99"
        not in rendered.text
    )

    assert (
        "1,00 TL"
        not in rendered.text
    )

    assert (
        "2,00 TL"
        not in rendered.text
    )
