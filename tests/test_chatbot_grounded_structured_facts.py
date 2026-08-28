import os

from src.chatbot_orchestrator import (
    run_chatbot,
)

from src.chatbot_answer_contract import (
    build_grounded_answer_context,
    build_llm_grounding_payload,
)


QUESTION = (
    "Albaraka T\u00fcrk konut "
    "finansman\u0131n\u0131n vadesi nedir?"
)


def test_real_albaraka_konut_structured_maturity():

    os.environ.pop(
        "POSTGRES_DSN",
        None,
    )

    context = (
        build_grounded_answer_context(
            run_chatbot(
                QUESTION
            )
        )
    )

    # Structured maturity questions are deterministic
    # finance facts. They do not require RAG evidence.
    assert (
        context.route
        == "finance_fact"
    )

    assert (
        context.execution_status
        == "completed"
    )

    assert not context.evidence

    assert not context.finance_results

    assert (
        "deterministic_finance_fact_lookup_executed"
        in context.reasons
    )

    assert (
        "finance_fact_status:found"
        in context.reasons
    )

    # Verify the user-visible deterministic fact as well.
    from src.chatbot_response_service import (
        ask_bansa,
    )

    response = (
        ask_bansa(
            QUESTION
        )
    )

    assert (
        response.route
        == "finance_fact"
    )

    assert (
        response.safe
        is True
    )

    assert (
        "120 ay"
        in str(
            response.text
        )
    )



def test_finance_fact_structured_maturity_does_not_require_llm_evidence():

    os.environ.pop(
        "POSTGRES_DSN",
        None,
    )

    context = (
        build_grounded_answer_context(
            run_chatbot(
                QUESTION
            )
        )
    )

    # Exact maturity questions now use the deterministic
    # finance_fact path rather than RAG/LLM evidence.
    assert (
        context.route
        == "finance_fact"
    )

    assert (
        context.execution_status
        == "completed"
    )

    assert not context.evidence

    assert not context.finance_results

    assert (
        "deterministic_finance_fact_lookup_executed"
        in context.reasons
    )

    assert (
        "finance_fact_status:found"
        in context.reasons
    )

    # Verify the actual deterministic answer instead of
    # requiring an LLM payload for a route that bypasses LLM.
    from src.chatbot_response_service import (
        ask_bansa,
    )

    response = (
        ask_bansa(
            QUESTION
        )
    )

    assert (
        response.route
        == "finance_fact"
    )

    assert (
        response.backend
        == "deterministic_finance_fact"
    )

    assert (
        response.safe
        is True
    )

    assert (
        "120 ay"
        in str(
            response.text
        )
    )



def test_wrong_product_structured_facts_do_not_enter_context():

    os.environ.pop(
        "POSTGRES_DSN",
        None,
    )

    context = (
        build_grounded_answer_context(
            run_chatbot(
                QUESTION
            )
        )
    )

    titles = {
        item.document_title
        for item in context.evidence
    }

    assert (
        "\u0130\u015f Yeri Finansman\u0131"
        not in titles
    )

    assert (
        "\u0130htiya\u00e7 Finansman\u0131"
        not in titles
    )

    assert (
        "Hac ve Umre Finansman\u0131"
        not in titles
    )
