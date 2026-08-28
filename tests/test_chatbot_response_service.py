from dataclasses import dataclass
from types import SimpleNamespace


from src.chatbot_response_service import (
    BansaResponseService,
)


@dataclass(frozen=True)
class Context:

    question: str

    route: str

    execution_status: str

    answer_mode: str

    may_generate_answer: bool

    evidence: tuple = ()

    finance_results: tuple = ()

    missing_fields: tuple = ()

    reasons: tuple = ()


class FakeRagRenderer:

    def __init__(self):

        self.calls = []


    def __call__(
        self,
        context,
        *,
        question=None,
    ):

        self.calls.append(
            (
                context,
                question,
            )
        )


        return SimpleNamespace(
            text=(
                "Deterministic extractive RAG answer."
            ),
            evidence_ids=(
                "E1",
            ),
            sentence_count=1,
            document_count=1,
            reasons=(
                "official_evidence_only",
                "extractive_no_paraphrase",
            ),
        )


class FakeFinanceRenderer:

    def __init__(self):

        self.calls = []


    def __call__(
        self,
        context,
    ):

        self.calls.append(
            context
        )


        return SimpleNamespace(
            text=(
                "Deterministic finance answer."
            )
        )


def service_for(
    context,
):

    rag = FakeRagRenderer()

    finance = (
        FakeFinanceRenderer()
    )


    def runner(
        question,
        *,
        finance_adapters=None,
    ):

        return context


    service = BansaResponseService(
        runner=runner,
        context_builder=(
            lambda execution:
                execution
        ),
        finance_renderer=(
            finance
        ),
        rag_renderer=(
            rag
        ),
    )


    return (
        service,
        rag,
        finance,
    )


def test_product_uses_extractive_renderer_only():

    context = Context(
        question="product",
        route="product_rag",
        execution_status="completed",
        answer_mode="rag",
        may_generate_answer=True,
        evidence=(
            "evidence",
        ),
    )


    (
        service,
        rag,
        finance,
    ) = service_for(
        context
    )


    response = service.ask(
        "product"
    )


    assert (
        response.backend
        == "deterministic_extractive_rag"
    )

    assert response.qwen_used is False

    assert (
        response.finance_renderer_used
        is False
    )

    assert len(
        rag.calls
    ) == 1

    assert not finance.calls


def test_campaign_uses_extractive_renderer_only():

    context = Context(
        question="campaign",
        route="campaign_rag",
        execution_status="completed",
        answer_mode="rag",
        may_generate_answer=True,
        evidence=(
            "evidence",
        ),
    )


    (
        service,
        rag,
        finance,
    ) = service_for(
        context
    )


    response = service.ask(
        "campaign"
    )


    assert response.qwen_used is False

    assert (
        response.backend
        == "deterministic_extractive_rag"
    )

    assert len(
        rag.calls
    ) == 1

    assert not finance.calls


def test_finance_uses_only_finance_renderer():

    context = Context(
        question="finance",
        route="finance_compare",
        execution_status="completed",
        answer_mode="finance",
        may_generate_answer=True,
        finance_results=(
            "candidate",
        ),
    )


    (
        service,
        rag,
        finance,
    ) = service_for(
        context
    )


    response = service.ask(
        "finance"
    )


    assert response.qwen_used is False

    assert (
        response.finance_renderer_used
        is True
    )

    assert (
        response.backend
        == "deterministic_finance"
    )

    assert not rag.calls

    assert len(
        finance.calls
    ) == 1


def test_hybrid_uses_extractive_and_finance():

    context = Context(
        question="hybrid",
        route="hybrid",
        execution_status="completed",
        answer_mode="hybrid",
        may_generate_answer=True,
        evidence=(
            "evidence",
        ),
        finance_results=(
            "candidate",
        ),
    )


    (
        service,
        rag,
        finance,
    ) = service_for(
        context
    )


    response = service.ask(
        "hybrid"
    )


    assert response.qwen_used is False

    assert (
        response.finance_renderer_used
        is True
    )

    assert (
        "Deterministic extractive RAG answer."
        in response.text
    )

    assert (
        "Deterministic finance answer."
        in response.text
    )

    assert len(
        rag.calls
    ) == 1

    assert len(
        finance.calls
    ) == 1


def test_needs_input_calls_neither_renderer():

    context = Context(
        question="missing",
        route="finance_compare",
        execution_status="needs_input",
        answer_mode="needs_input",
        may_generate_answer=False,
        missing_fields=(
            "amount",
            "maturity",
        ),
    )


    (
        service,
        rag,
        finance,
    ) = service_for(
        context
    )


    response = service.ask(
        "missing"
    )


    assert response.qwen_used is False

    assert (
        response.finance_renderer_used
        is False
    )

    assert "75.000 TL" in response.text

    assert "24 ay" in response.text

    assert not rag.calls

    assert not finance.calls


def test_unknown_calls_neither_renderer():

    context = Context(
        question="hello",
        route="unknown",
        execution_status="unknown",
        answer_mode="unknown",
        may_generate_answer=False,
    )


    (
        service,
        rag,
        finance,
    ) = service_for(
        context
    )


    response = service.ask(
        "hello"
    )


    assert (
        response.backend
        == "deterministic_unknown"
    )

    assert response.qwen_used is False

    assert not rag.calls

    assert not finance.calls


def test_abstain_is_fail_closed():

    context = Context(
        question="question",
        route="product_rag",
        execution_status="abstain",
        answer_mode="abstain",
        may_generate_answer=False,
    )


    (
        service,
        rag,
        finance,
    ) = service_for(
        context
    )


    response = service.ask(
        "question"
    )


    assert (
        response.backend
        == "deterministic_abstain"
    )

    assert response.qwen_used is False

    assert not rag.calls

    assert not finance.calls


def test_release_is_noop_without_llm():

    context = Context(
        question="hello",
        route="unknown",
        execution_status="unknown",
        answer_mode="unknown",
        may_generate_answer=False,
    )


    (
        service,
        _,
        _,
    ) = service_for(
        context
    )


    assert (
        service.release()
        is None
    )
