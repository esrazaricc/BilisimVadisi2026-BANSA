from datetime import date

from src.chatbot_market_campaign_runtime import (
    _is_strict_market_topic,
    answer_market_question,
    list_market_campaigns,
)


def test_real_market_title_matches():

    assert _is_strict_market_topic(
        title=(
            "Market ve G\u0131da "
            "Harcamalar\u0131n\u0131za "
            "Her Ay Ekstra 2.000 Mil"
        ),
        source_url=(
            "https://example.com/"
            "market-ve-gida-harcamalari"
        ),
    )


def test_yapi_market_is_not_grocery_market():

    assert not _is_strict_market_topic(
        title=(
            "Starwood Yap\u0131 Market'te "
            "Vade Farks\u0131z Taksit"
        ),
        source_url=(
            "https://example.com/"
            "starwood-yapi-markette"
        ),
    )


def test_kuveyt_real_live_market_campaign_exists():

    rows = list_market_campaigns(
        "Kuveyt T\u00fcrk",
        today=date(
            2026,
            8,
            24,
        ),
    )

    titles = {
        row[
            "title"
        ]
        for row in rows
    }

    assert (
        "Market ve G\u0131da Harcamalar\u0131n\u0131za "
        "Her Ay Ekstra 2.000 Mil'e Varan F\u0131rsat!"
        in titles
    )


def test_turkiye_finans_has_no_strict_grocery_market_match():

    rows = list_market_campaigns(
        "T\u00fcrkiye Finans",
        today=date(
            2026,
            8,
            24,
        ),
    )

    assert rows == ()


def test_turkiye_finans_market_answer_is_bank_locked():

    result = answer_market_question(
        (
            "T\u00fcrkiye Finans'\u0131n "
            "market al\u0131\u015fveri\u015fiyle ilgili "
            "hangi kampanyalar\u0131 var?"
        ),
        today=date(
            2026,
            8,
            24,
        ),
    )

    assert result is not None

    assert (
        result[
            "status"
        ]
        ==
        "NO_MATCH"
    )

    assert (
        "T\u00fcrkiye Finans"
        in result[
            "text"
        ]
    )

    assert (
        "Kuveyt T\u00fcrk"
        not in result[
            "text"
        ]
    )


def test_partial_compare_keeps_kuveyt_result():

    result = answer_market_question(
        (
            "Albaraka T\u00fcrk ile "
            "Kuveyt T\u00fcrk'\u00fcn "
            "market kampanyalar\u0131n\u0131 "
            "kar\u015f\u0131la\u015ft\u0131r."
        ),
        today=date(
            2026,
            8,
            24,
        ),
    )

    assert result is not None

    text = result[
        "text"
    ]

    assert (
        "Albaraka T\u00fcrk"
        in text
    )

    assert (
        "Kuveyt T\u00fcrk"
        in text
    )

    assert (
        "Market ve G\u0131da Harcamalar\u0131n\u0131za"
        in text
    )

    assert (
        "market/g\u0131da taraf\u0131nda avantaj sunan taraf"
        in text
    )

    assert (
        "birebir bir kazanan belirlemiyorum"
        not in text
    )
