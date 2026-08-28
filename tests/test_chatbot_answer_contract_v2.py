from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


from src.chatbot_answer_contract import (
    build_grounded_answer_context,
)


@dataclass
class FakeRequest:

    product_id: int
    bank_name: str
    product_name: str

    amount: Decimal = Decimal("75000")
    maturity_months: int = 24


class FakeStatus:

    def __init__(
        self,
        value,
    ):
        self.value = value


@dataclass
class FakeFinanceResult:

    request: FakeRequest
    status: object

    profit_share_rate: Decimal | None = None
    monthly_installment: Decimal | None = None
    total_repayment: Decimal | None = None

    allocation_fee: Decimal | None = None
    mortgage_fee: Decimal | None = None
    appraisal_fee: Decimal | None = None
    total_fees: Decimal | None = None

    source_kind: str | None = None
    source_url: str | None = None
    checked_at: datetime | None = None
    reason: str | None = None

    is_exact_match: bool = False
    is_rankable: bool = False


@dataclass
class FakeExecution:

    question: str = "hangi banka daha uygun"
    route: str = "finance_compare"
    status: str = "completed"

    rag_result: object | None = None

    finance_results: tuple = ()

    missing_fields: tuple = ()
    reasons: tuple = ()


def verified(
    product_id,
    bank_name,
    total,
):

    return FakeFinanceResult(
        request=FakeRequest(
            product_id=product_id,
            bank_name=bank_name,
            product_name="Ihtiyac Finansmani",
        ),
        status=FakeStatus(
            "VERIFIED"
        ),
        profit_share_rate=Decimal(
            "3.50"
        ),
        monthly_installment=Decimal(
            "5000.00"
        ),
        total_repayment=Decimal(
            str(total)
        ),
        source_kind=(
            "official_live_calculator"
        ),
        source_url=(
            "https://example.com"
        ),
        is_exact_match=True,
        is_rankable=True,
    )


def unverified(
    product_id,
    bank_name,
):

    return FakeFinanceResult(
        request=FakeRequest(
            product_id=product_id,
            bank_name=bank_name,
            product_name="Ihtiyac Finansmani",
        ),
        status=FakeStatus(
            "UNVERIFIED"
        ),
        is_exact_match=False,
        is_rankable=False,
        reason=(
            "No verified adapter."
        ),
    )


def ineligible(
    product_id,
    bank_name,
):

    return FakeFinanceResult(
        request=FakeRequest(
            product_id=product_id,
            bank_name=bank_name,
            product_name="Ihtiyac Finansmani",
        ),
        status=FakeStatus(
            "INELIGIBLE"
        ),
        is_exact_match=False,
        is_rankable=False,
        reason=(
            "Official rules reject scenario."
        ),
    )


def test_one_verified_plus_unverified_blocks_global_ranking():

    execution = FakeExecution(
        finance_results=(
            verified(
                318,
                "Vakif Katilim",
                "128866.02",
            ),
            unverified(
                4,
                "Dunya Katilim",
            ),
        )
    )

    context = (
        build_grounded_answer_context(
            execution
        )
    )

    assert (
        context.may_use_financial_numbers
        is True
    )

    assert (
        context.may_claim_finance_ranking
        is False
    )

    assert (
        "unresolved_finance_candidates_present"
        in context.reasons
    )


def test_two_verified_no_unresolved_allows_ranking():

    execution = FakeExecution(
        finance_results=(
            verified(
                318,
                "Vakif Katilim",
                "128866.02",
            ),
            verified(
                273,
                "Emlak Katilim",
                "131171.63",
            ),
        )
    )

    context = (
        build_grounded_answer_context(
            execution
        )
    )

    assert (
        context.may_use_financial_numbers
        is True
    )

    assert (
        context.may_claim_finance_ranking
        is True
    )


def test_two_verified_plus_unverified_blocks_ranking():

    execution = FakeExecution(
        finance_results=(
            verified(
                318,
                "Vakif Katilim",
                "128866.02",
            ),
            verified(
                273,
                "Emlak Katilim",
                "131171.63",
            ),
            unverified(
                4,
                "Dunya Katilim",
            ),
        )
    )

    context = (
        build_grounded_answer_context(
            execution
        )
    )

    assert (
        context.may_use_financial_numbers
        is True
    )

    assert (
        context.may_claim_finance_ranking
        is False
    )


def test_ineligible_candidate_does_not_block_verified_comparison():

    execution = FakeExecution(
        finance_results=(
            verified(
                318,
                "Vakif Katilim",
                "128866.02",
            ),
            verified(
                273,
                "Emlak Katilim",
                "131171.63",
            ),
            ineligible(
                121,
                "Albaraka Turk",
            ),
        )
    )

    context = (
        build_grounded_answer_context(
            execution
        )
    )

    assert (
        context.may_claim_finance_ranking
        is True
    )


def test_single_verified_result_never_claims_cross_bank_ranking():

    execution = FakeExecution(
        finance_results=(
            verified(
                318,
                "Vakif Katilim",
                "128866.02",
            ),
        )
    )

    context = (
        build_grounded_answer_context(
            execution
        )
    )

    assert (
        context.may_use_financial_numbers
        is True
    )

    assert (
        context.may_claim_finance_ranking
        is False
    )
