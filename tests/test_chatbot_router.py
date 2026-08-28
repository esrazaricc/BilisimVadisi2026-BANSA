from decimal import Decimal

from src.chatbot_router import (
    ROUTE_CAMPAIGN_RAG,
    ROUTE_FINANCE_COMPARE,
    ROUTE_HYBRID,
    ROUTE_PRODUCT_RAG,
    route_question,
)


def test_campaign_question_routes_to_rag():
    result = route_question(
        "Albaraka'n\u0131n \u00f6\u011frencilere "
        "kampanyas\u0131 var m\u0131?"
    )

    assert result.route == ROUTE_CAMPAIGN_RAG


def test_product_information_routes_to_product_rag():
    result = route_question(
        "Vak\u0131f Kat\u0131l\u0131m "
        "ihtiya\u00e7 finansman\u0131 "
        "ka\u00e7 aya kadar?"
    )

    # Structured maturity facts belong to the deterministic
    # finance_fact path, not product RAG.
    assert result.route == "finance_fact"
    assert result.family == "ihtiyac_finansmani"


def test_exact_general_needs_comparison():
    result = route_question(
        "75 bin TL 24 ay genel "
        "ihtiya\u00e7 finansman\u0131 "
        "i\u00e7in hangi banka daha uygun?"
    )

    assert result.route == ROUTE_FINANCE_COMPARE
    assert result.family == "ihtiyac_finansmani"
    assert result.purpose == "genel_ihtiyac"
    assert result.amount == Decimal("75000")
    assert result.maturity == 24
    assert result.missing_fields == ()
    assert result.ready_for_finance_compare


def test_hybrid_question_does_not_invent_missing_maturity():
    result = route_question(
        "75 bin TL genel "
        "ihtiya\u00e7 finansman\u0131 istiyorum, "
        "bana uygun kampanya da var m\u0131?"
    )

    assert result.route == ROUTE_HYBRID
    assert result.amount == Decimal("75000")
    assert result.family == "ihtiyac_finansmani"
    assert result.purpose == "genel_ihtiyac"
    assert result.maturity is None
    assert "maturity" in result.missing_fields
    assert not result.ready_for_finance_compare


def test_needs_comparison_requires_semantic_purpose():
    result = route_question(
        "75 bin TL 24 ay "
        "ihtiya\u00e7 finansman\u0131 "
        "hangi banka?"
    )

    assert result.route == ROUTE_FINANCE_COMPARE
    assert result.family == "ihtiyac_finansmani"
    assert result.amount == Decimal("75000")
    assert result.maturity == 24
    assert result.purpose is None
    assert "purpose" in result.missing_fields
    assert not result.ready_for_finance_compare


def test_motorcycle_semantic_purpose():
    result = route_question(
        "100 bin TL 12 ay motosiklet "
        "i\u00e7in hangi "
        "ihtiya\u00e7 finansman\u0131 "
        "daha uygun?"
    )

    assert result.route == ROUTE_FINANCE_COMPARE
    assert result.family == "ihtiyac_finansmani"
    assert result.purpose == "motosiklet"
    assert result.amount == Decimal("100000")
    assert result.maturity == 12
    assert result.missing_fields == ()
    assert result.ready_for_finance_compare

# ROUTER_PRODUCT_CAMPAIGN_ADVANTAGE_REGRESSION_V1

def test_product_advantages_question_routes_to_product_rag():

    question = (
        "Albaraka T\u00fcrk e\u011fitim "
        "finansman\u0131n\u0131n "
        "avantajlar\u0131 nelerdir?"
    )

    result = route_question(
        question
    )

    assert (
        result.route
        == ROUTE_PRODUCT_RAG
    )

    assert (
        "product_signal"
        in result.reasons
    )

    assert (
        "campaign_signal"
        not in result.reasons
    )


def test_explicit_campaign_advantages_still_routes_to_campaign_rag():

    question = (
        "Albaraka T\u00fcrk e\u011fitim "
        "kampanyas\u0131n\u0131n "
        "avantajlar\u0131 nelerdir?"
    )

    result = route_question(
        question
    )

    assert (
        result.route
        == ROUTE_CAMPAIGN_RAG
    )

    assert (
        "campaign_signal"
        in result.reasons
    )


def test_campaign_keyword_still_routes_to_campaign_rag():

    question = (
        "Albaraka T\u00fcrk hangi "
        "kampanyalar\u0131 sunuyor?"
    )

    result = route_question(
        question
    )

    assert (
        result.route
        == ROUTE_CAMPAIGN_RAG
    )


def test_product_duration_question_still_routes_to_product_rag():

    question = (
        "Albaraka T\u00fcrk e\u011fitim "
        "finansman\u0131 ka\u00e7 aya kadar?"
    )

    result = route_question(
        question
    )

    # Exact maturity questions are structured finance facts.
    assert (
        result.route
        == "finance_fact"
    )


def test_numeric_finance_compare_route_is_unchanged():

    question = (
        "75 bin TL 24 ay genel "
        "ihtiya\u00e7 finansman\u0131 "
        "i\u00e7in hangi banka daha uygun?"
    )

    result = route_question(
        question
    )

    assert (
        result.route
        == ROUTE_FINANCE_COMPARE
    )

    assert (
        result.family
        == "ihtiyac_finansmani"
    )

    assert (
        result.purpose
        == "genel_ihtiyac"
    )

    assert (
        result.amount
        == Decimal("75000")
    )

    assert (
        result.maturity
        == 24
    )

