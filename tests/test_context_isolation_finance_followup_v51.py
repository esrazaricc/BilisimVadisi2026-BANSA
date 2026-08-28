from src.chat_followup_context import (
    resolve_followup_question,
)


Q_FINANCE = (
    "Albaraka T\u00fcrk ile "
    "D\u00fcnya Kat\u0131l\u0131m\u0131n "
    "konut finansmanlar\u0131n\u0131 "
    "kar\u015f\u0131la\u015ft\u0131r. "
    "150.000 TL, 36 ay."
)


def test_explicit_new_bank_does_not_inherit_vakif():

    result = resolve_followup_question(
        (
            "Adil Kat\u0131l\u0131m Ticari Finansman\u0131n "
            "k\u00e2r pay\u0131 oran\u0131 nedir?"
        ),
        [
            (
                "Vak\u0131f Kat\u0131l\u0131m Motosiklet "
                "Finansman\u0131 en fazla ka\u00e7 ay vadeli?"
            ),
        ],
    )

    assert result.used_context is False

    assert (
        "Vak\u0131f Kat\u0131l\u0131m"
        not in result.resolved_question
    )

    assert (
        "Motosiklet"
        not in result.resolved_question
    )

    assert (
        "Adil Kat\u0131l\u0131m"
        in result.resolved_question
    )


def test_unknown_bank_like_name_also_blocks_stale_inheritance():

    result = resolve_followup_question(
        (
            "Ornek Kat\u0131l\u0131m Konut Finansman\u0131 "
            "k\u00e2r pay\u0131 oran\u0131 nedir?"
        ),
        [
            (
                "Vak\u0131f Kat\u0131l\u0131m Motosiklet "
                "Finansman\u0131 en fazla ka\u00e7 ay vadeli?"
            ),
        ],
    )

    assert result.used_context is False

    assert (
        "Vak\u0131f Kat\u0131l\u0131m"
        not in result.resolved_question
    )


def test_numeric_followup_reuses_latest_finance_compare():

    result = resolve_followup_question(
        (
            "Peki 200.000 TL, 36 ay olursa?"
        ),
        [
            Q_FINANCE,
        ],
    )

    assert result.used_context is True

    text = result.resolved_question

    assert (
        "Albaraka T\u00fcrk"
        in text
    )

    assert (
        "D\u00fcnya Kat\u0131l\u0131m"
        in text
    )

    assert (
        "200000 TL"
        in text
    )

    assert (
        "36 ay"
        in text
    )

    assert (
        "konut finansman\u0131"
        in text
    )


def test_numeric_followup_ignores_intervening_campaign_turn():

    result = resolve_followup_question(
        (
            "Peki 200.000 TL, 36 ay olursa?"
        ),
        [
            Q_FINANCE,
            (
                "Albaraka T\u00fcrk ile Kuveyt T\u00fcrk'\u00fcn "
                "market kampanyalar\u0131n\u0131 kar\u015f\u0131la\u015ft\u0131r."
            ),
        ],
    )

    text = result.resolved_question

    assert result.used_context is True

    assert (
        "konut finansman\u0131"
        in text
    )

    assert (
        "market"
        not in text.casefold()
    )

    assert (
        "kampanya"
        not in text.casefold()
    )


def test_dunya_variant_question_inherits_amount_and_maturity_only():

    result = resolve_followup_question(
        (
            "D\u00fcnya Kat\u0131l\u0131mda yeni konut ile "
            "ikinci el konut aras\u0131nda sonu\u00e7 fark\u0131 var m\u0131?"
        ),
        [
            Q_FINANCE,
        ],
    )

    assert result.used_context is True

    text = result.resolved_question

    assert (
        "D\u00fcnya Kat\u0131l\u0131m"
        in text
    )

    assert (
        "150000 TL"
        in text
    )

    assert (
        "36 ay"
        in text
    )

    assert (
        "yeni / s\u0131f\u0131r konut"
        in text
    )

    assert (
        "ikinci el konut"
        in text
    )

    # Explicit Dunya question must not inherit Albaraka.
    assert (
        "Albaraka T\u00fcrk"
        not in text
    )


def test_regular_question_still_delegates():

    question = (
        "Kuveyt T\u00fcrk Al\u0131\u015fveri\u015f Finansman\u0131 "
        "en fazla ka\u00e7 ay vadeli?"
    )

    result = resolve_followup_question(
        question,
        [],
    )

    assert (
        "Kuveyt T\u00fcrk"
        in result.resolved_question
    )

    assert (
        "Al\u0131\u015fveri\u015f Finansman\u0131"
        in result.resolved_question
    )
