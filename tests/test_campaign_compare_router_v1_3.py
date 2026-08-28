from src.chatbot_router import (
    route_question,
)


def test_market_bank_advantage_becomes_campaign_compare():

    decision = route_question(
        "Market alisverisinde "
        "hangi banka daha avantajli?"
    )

    assert (
        decision.route
        == "campaign_compare"
    )


def test_market_explicit_compare_becomes_campaign_compare():

    decision = route_question(
        "Market kampanyalarini "
        "karsilastir"
    )

    assert (
        decision.route
        == "campaign_compare"
    )


def test_education_compare_becomes_campaign_compare():

    decision = route_question(
        "Egitim kampanyalarini "
        "karsilastir"
    )

    assert (
        decision.route
        == "campaign_compare"
    )


def test_explicit_campaign_fact_stays_campaign_rag():

    decision = route_question(
        "Emlak Katilim market "
        "kampanyasi var mi?"
    )

    assert (
        decision.route
        == "campaign_rag"
    )


def test_campaign_advantages_stay_campaign_rag():

    decision = route_question(
        "Albaraka kampanyasinin "
        "avantajlari neler?"
    )

    assert (
        decision.route
        == "campaign_rag"
    )


def test_generic_product_list_stays_product_rag():

    decision = route_question(
        "Konut finansmanlari nelerdir?"
    )

    assert (
        decision.route
        == "product_rag"
    )


def test_finance_compare_is_never_stolen():

    decision = route_question(
        "100000 TL 36 ay konut "
        "finansmaninda hangi banka "
        "daha avantajli?"
    )

    assert (
        decision.route
        == "finance_compare"
    )


def test_vehicle_finance_compare_is_never_stolen():

    decision = route_question(
        "100000 TL 36 ay tasit "
        "finansmanlarini karsilastir"
    )

    assert (
        decision.route
        == "finance_compare"
    )


def test_plain_market_question_without_comparison_not_forced():

    decision = route_question(
        "Market alisverisi icin "
        "hangi kampanyalar var?"
    )

    assert (
        decision.route
        != "campaign_compare"
    )


def test_plain_education_question_without_comparison_not_forced():

    decision = route_question(
        "Egitim kampanyalari neler?"
    )

    assert (
        decision.route
        != "campaign_compare"
    )
