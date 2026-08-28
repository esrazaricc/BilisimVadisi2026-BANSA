from dataclasses import dataclass
from decimal import Decimal


from src.chatbot_orchestrator import (
    STATUS_COMPLETED,
    STATUS_NEEDS_INPUT,
    STATUS_PARTIAL,
    run_chatbot,
)


@dataclass
class FakeDecision:

    route: str

    family: str | None = None
    purpose: str | None = None

    amount: Decimal | None = None
    maturity: int | None = None

    missing_fields: tuple = ()

    @property
    def ready_for_finance_compare(
        self,
    ):

        return (
            self.family is not None
            and self.amount is not None
            and self.maturity is not None
            and not self.missing_fields
        )


@dataclass
class FakeFinanceResult:

    is_rankable: bool = False


@dataclass
class FakeRagResult:

    status: str = "pass"
    reasons: tuple = (
        "official_source_present",
    )


def test_finance_route_calls_deterministic_engine():

    captured = {}

    def fake_compare(**kwargs):

        captured.update(
            kwargs
        )

        return [
            FakeFinanceResult(
                is_rankable=True
            )
        ]

    decision = FakeDecision(
        route="finance_compare",
        family="ihtiyac_finansmani",
        purpose="genel_ihtiyac",
        amount=Decimal("75000"),
        maturity=24,
    )

    result = run_chatbot(
        "question",
        route_decision=decision,
        finance_compare_fn=(
            fake_compare
        ),
        finance_adapters={},
    )

    assert (
        result.status
        == STATUS_COMPLETED
    )

    assert (
        result.finance_executed
        is True
    )

    assert (
        result.rankable_finance_count
        == 1
    )

    assert (
        captured["family"]
        == "ihtiyac_finansmani"
    )

    assert (
        captured["purpose"]
        == "genel_ihtiyac"
    )

    assert (
        captured["amount"]
        == Decimal("75000")
    )

    assert (
        captured["maturity"]
        == 24
    )

    assert (
        captured["adapters"]
        == {}
    )


def test_missing_finance_fields_fail_closed():

    decision = FakeDecision(
        route="finance_compare",
        family="ihtiyac_finansmani",
        amount=Decimal("75000"),
        maturity=24,
        purpose=None,
        missing_fields=(
            "purpose",
        ),
    )

    result = run_chatbot(
        "question",
        route_decision=decision,
    )

    assert (
        result.status
        == STATUS_NEEDS_INPUT
    )

    assert (
        result.finance_executed
        is False
    )

    assert (
        result.missing_fields
        == ("purpose",)
    )


def test_campaign_route_does_not_call_finance():

    called = {
        "finance":
            False,
    }

    def fake_compare(**kwargs):

        called["finance"] = True

        return []

    def fake_rag(
        question,
        **kwargs,
    ):

        return FakeRagResult()

    decision = FakeDecision(
        route="campaign_rag",
    )

    result = run_chatbot(
        "question",
        route_decision=decision,
        rag_runner=fake_rag,
        finance_compare_fn=(
            fake_compare
        ),
    )

    assert (
        result.status
        == STATUS_COMPLETED
    )

    assert (
        called["finance"]
        is False
    )


def test_hybrid_runs_both_lanes():

    calls = {
        "rag":
            0,
        "finance":
            0,
    }

    def fake_rag(
        question,
        **kwargs,
    ):

        calls["rag"] += 1

        return FakeRagResult()

    def fake_compare(**kwargs):

        calls["finance"] += 1

        return [
            FakeFinanceResult(
                is_rankable=False
            )
        ]

    decision = FakeDecision(
        route="hybrid",
        family="ihtiyac_finansmani",
        purpose="genel_ihtiyac",
        amount=Decimal("75000"),
        maturity=24,
    )

    result = run_chatbot(
        "question",
        route_decision=decision,
        rag_runner=fake_rag,
        finance_compare_fn=(
            fake_compare
        ),
        finance_adapters={},
    )

    assert (
        calls["rag"]
        == 1
    )

    assert (
        calls["finance"]
        == 1
    )

    assert (
        result.finance_executed
        is True
    )

    assert (
        result.status
        == STATUS_COMPLETED
    )


def test_hybrid_missing_finance_is_partial():

    def fake_rag(
        question,
        **kwargs,
    ):

        return FakeRagResult()

    decision = FakeDecision(
        route="hybrid",
        family="ihtiyac_finansmani",
        amount=Decimal("75000"),
        maturity=None,
        purpose="genel_ihtiyac",
        missing_fields=(
            "maturity",
        ),
    )

    result = run_chatbot(
        "question",
        route_decision=decision,
        rag_runner=fake_rag,
    )

    assert (
        result.status
        == STATUS_PARTIAL
    )

    assert (
        result.finance_executed
        is False
    )

    assert (
        result.missing_fields
        == ("maturity",)
    )
