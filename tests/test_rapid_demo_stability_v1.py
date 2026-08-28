from types import SimpleNamespace

import src.chatbot_response_service as service


def test_maturity_phrase_normalization():

    question = (
        "Vak\u0131f Kat\u0131l\u0131m "
        "Motosiklet Finansman\u0131 "
        "en fazla ka\u00e7 ay vadeli?"
    )

    result = (
        service
        ._rapid_preprocess_question_v1(
            question
        )
    )

    assert (
        "Azami vade ka\u00e7 aya kadar?"
        in result
    )


def test_two_bank_identity_preserved():

    question = (
        "Albaraka T\u00fcrk ile "
        "D\u00fcnya Kat\u0131l\u0131m\u0131n "
        "konut finansmanlar\u0131n\u0131 "
        "kar\u015f\u0131la\u015ft\u0131r. "
        "150.000 TL, 36 ay."
    )

    result = (
        service
        ._rapid_preprocess_question_v1(
            question
        )
    )

    assert "Bankalar:" in result

    assert (
        "Albaraka T\u00fcrk"
        in result
    )

    assert (
        "D\u00fcnya Kat\u0131l\u0131m"
        in result
    )


def test_market_wrong_bank_rejected():

    evidence = SimpleNamespace(
        bank_name="Ziraat Kat\u0131l\u0131m",
        document_title="Market Kampanyas\u0131",
        source_url="https://example.com/market",
        structured_fields={
            "campaign_end_date":
                "2099-12-31",
            "is_active":
                1,
        },
    )

    assert not (
        service
        ._rapid_campaign_allowed_v1(
            evidence,
            (
                "T\u00fcrkiye Finans",
            ),
        )
    )


def test_market_expired_rejected():

    evidence = SimpleNamespace(
        bank_name="T\u00fcrkiye Finans",
        document_title="Market Kampanyas\u0131",
        source_url="https://example.com/market",
        structured_fields={
            "campaign_end_date":
                "2026-08-07",
            "is_active":
                1,
        },
    )

    assert not (
        service
        ._rapid_campaign_allowed_v1(
            evidence,
            (
                "T\u00fcrkiye Finans",
            ),
        )
    )


def test_market_current_matching_allowed():

    evidence = SimpleNamespace(
        bank_name="T\u00fcrkiye Finans",
        document_title=(
            "Market ve G\u0131da Kampanyas\u0131"
        ),
        source_url="https://example.com/market",
        structured_fields={
            "campaign_end_date":
                "2099-12-31",
            "is_active":
                1,
        },
    )

    assert (
        service
        ._rapid_campaign_allowed_v1(
            evidence,
            (
                "T\u00fcrkiye Finans",
            ),
        )
    )
