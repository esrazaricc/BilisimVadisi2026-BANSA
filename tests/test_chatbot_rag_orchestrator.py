from dataclasses import dataclass


from src.chatbot_rag_orchestrator import (
    RAG_STATUS_NOT_APPLICABLE,
    ROUTE_CAMPAIGN_RAG,
    ROUTE_FINANCE_COMPARE,
    ROUTE_HYBRID,
    ROUTE_PRODUCT_RAG,
    expected_source_kind_for_route,
    route_requires_rag,
)


def test_campaign_route_uses_campaign_corpus():

    assert (
        expected_source_kind_for_route(
            ROUTE_CAMPAIGN_RAG
        )
        == "campaign"
    )

    assert route_requires_rag(
        ROUTE_CAMPAIGN_RAG
    )


def test_product_route_uses_product_corpus():

    assert (
        expected_source_kind_for_route(
            ROUTE_PRODUCT_RAG
        )
        == "standard_product"
    )

    assert route_requires_rag(
        ROUTE_PRODUCT_RAG
    )


def test_hybrid_rag_side_is_campaign():

    assert (
        expected_source_kind_for_route(
            ROUTE_HYBRID
        )
        == "campaign"
    )

    assert route_requires_rag(
        ROUTE_HYBRID
    )


def test_finance_compare_does_not_use_rag():

    assert (
        expected_source_kind_for_route(
            ROUTE_FINANCE_COMPARE
        )
        is None
    )

    assert not route_requires_rag(
        ROUTE_FINANCE_COMPARE
    )


def test_real_router_campaign_classification():

    from src.chatbot_router import (
        route_question,
    )

    decision = route_question(
        (
            "Albaraka'nin "
            "ogrencilere kampanyasi "
            "var mi?"
        )
    )

    assert (
        decision.route
        == ROUTE_CAMPAIGN_RAG
    )


def test_real_router_product_classification():

    from src.chatbot_router import (
        route_question,
    )

    decision = route_question(
        (
            "Vakif Katilim "
            "ihtiyac finansmani "
            "kac aya kadar?"
        )
    )

    assert (
        decision.route
        == "finance_fact"
    )

    assert (
        decision.family
        == "ihtiyac_finansmani"
    )


def test_real_router_finance_classification():

    from src.chatbot_router import (
        route_question,
    )

    decision = route_question(
        (
            "75 bin TL 24 ay "
            "genel ihtiyac finansmani "
            "icin hangi banka "
            "daha uygun?"
        )
    )

    assert (
        decision.route
        == ROUTE_FINANCE_COMPARE
    )
