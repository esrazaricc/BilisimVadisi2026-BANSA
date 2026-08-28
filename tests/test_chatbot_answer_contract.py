from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


from src.chatbot_answer_contract import (
    ANSWER_MODE_ABSTAIN,
    ANSWER_MODE_FINANCE,
    ANSWER_MODE_NEEDS_INPUT,
    GroundedFinanceResult,
    build_grounded_answer_context,
    build_llm_grounding_payload,
)


@dataclass
class FakeRequest:

    product_id: int = 318
    bank_name: str = "Vakif Katilim"
    product_name: str = "Ihtiyac Finansmani"
    amount: Decimal = Decimal("75000")
    maturity_months: int = 24


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

    question: str
    route: str
    status: str

    rag_result: object | None = None

    finance_results: tuple = ()

    missing_fields: tuple = ()
    reasons: tuple = ()


class Status:

    def __init__(
        self,
        value,
    ):

        self.value = value


def test_unverified_finance_numbers_are_stripped():

    raw = FakeFinanceResult(
        request=FakeRequest(),
        status=Status(
            "UNVERIFIED"
        ),
        profit_share_rate=Decimal(
            "3.75"
        ),
        monthly_installment=Decimal(
            "5369.42"
        ),
        total_repayment=Decimal(
            "128866.02"
        ),
        allocation_fee=Decimal(
            "999"
        ),
        source_url=(
            "https://example.com"
        ),
        is_exact_match=False,
        is_rankable=False,
    )

    execution = FakeExecution(
        question="question",
        route="finance_compare",
        status="completed",
        finance_results=(
            raw,
        ),
    )

    context = (
        build_grounded_answer_context(
            execution
        )
    )

    assert (
        context.answer_mode
        == ANSWER_MODE_FINANCE
    )

    assert (
        context.may_claim_finance_ranking
        is False
    )

    assert (
        context.may_use_financial_numbers
        is False
    )

    item = (
        context.finance_results[0]
    )

    assert (
        item.profit_share_rate
        is None
    )

    assert (
        item.monthly_installment
        is None
    )

    assert (
        item.total_repayment
        is None
    )

    assert (
        item.allocation_fee
        is None
    )


def test_verified_exact_finance_numbers_are_allowed():

    raw = FakeFinanceResult(
        request=FakeRequest(),
        status=Status(
            "VERIFIED"
        ),
        profit_share_rate=Decimal(
            "3.75"
        ),
        monthly_installment=Decimal(
            "5369.42"
        ),
        total_repayment=Decimal(
            "128866.02"
        ),
        source_kind=(
            "official_live_calculator"
        ),
        source_url=(
            "https://example.com"
        ),
        checked_at=datetime(
            2026,
            8,
            21,
        ),
        is_exact_match=True,
        is_rankable=True,
    )

    execution = FakeExecution(
        question="question",
        route="finance_compare",
        status="completed",
        finance_results=(
            raw,
        ),
    )

    context = (
        build_grounded_answer_context(
            execution
        )
    )

    # A single verified result may expose
    # its verified numbers, but it cannot
    # establish a cross-bank ranking.
    assert (
        context.may_claim_finance_ranking
        is False
    )

    assert (
        context.may_use_financial_numbers
        is True
    )

    assert (
        context.finance_results[
            0
        ].monthly_installment
        == Decimal("5369.42")
    )


def test_no_rankable_results_blocks_best_bank_claim():

    raw = FakeFinanceResult(
        request=FakeRequest(),
        status=Status(
            "UNVERIFIED"
        ),
        is_exact_match=False,
        is_rankable=False,
    )

    execution = FakeExecution(
        question="hangi banka daha uygun",
        route="finance_compare",
        status="completed",
        finance_results=(
            raw,
        ),
    )

    context = (
        build_grounded_answer_context(
            execution
        )
    )

    payload = (
        build_llm_grounding_payload(
            context
        )
    )

    assert (
        payload[
            "permissions"
        ][
            "may_claim_finance_ranking"
        ]
        is False
    )

    assert (
        payload[
            "finance_results"
        ][0][
            "monthly_installment"
        ]
        is None
    )


def test_needs_input_blocks_generation():

    execution = FakeExecution(
        question="75 bin ihtiyac",
        route="finance_compare",
        status="needs_input",
        missing_fields=(
            "maturity",
        ),
    )

    context = (
        build_grounded_answer_context(
            execution
        )
    )

    assert (
        context.answer_mode
        == ANSWER_MODE_NEEDS_INPUT
    )

    assert (
        context.may_generate_answer
        is False
    )


def test_abstain_blocks_generation():

    execution = FakeExecution(
        question="unknown evidence",
        route="campaign_rag",
        status="abstain",
    )

    context = (
        build_grounded_answer_context(
            execution
        )
    )

    assert (
        context.answer_mode
        == ANSWER_MODE_ABSTAIN
    )

    assert (
        context.may_generate_answer
        is False
    )
