from functools import lru_cache


from src.chatbot_response_service import (
    ask_bansa,
)


@lru_cache(maxsize=1)
def _response():

    return ask_bansa(
        (
            "100.000 TL 36 ay konut "
            "finansmanlarini karsilastir"
        )
    )


def test_route_stays_deterministic():

    response = _response()

    assert (
        response.route
        == "finance_compare"
    )

    assert (
        response.backend
        == "deterministic_finance"
    )

    assert (
        response.qwen_used
        is False
    )


def test_condition_section_exists():

    text = _response().text

    assert (
        "Ko\u015fula g\u00f6re do\u011frulanm\u0131\u015f "
        "konut se\u00e7enekleri"
        in text
    )


def test_vakif_zero_and_second_hand_are_visible():

    text = _response().text

    assert (
        "Vak\u0131f Kat\u0131l\u0131m - "
        "Konut Finansman\u0131"
        in text
    )

    assert (
        "Yeni / s\u0131f\u0131r konut"
        in text
    )

    assert (
        "\u0130kinci el konut"
        in text
    )

    assert (
        "**s\u0131f\u0131r ve ikinci el konut**"
        in text
    )

    assert (
        "do\u011frulanm\u0131\u015f finansal "
        "sonu\u00e7 ayn\u0131d\u0131r"
        in text
    )


def test_turkiye_finans_conditions_are_visible():

    text = _response().text

    expected_values = (
        "\u0130lk konut + sigortal\u0131",
        "\u0130lk konut + sigortas\u0131z",
        (
            "Halihaz\u0131rda konutu bulunan "
            "+ sigortal\u0131"
        ),
        (
            "Halihaz\u0131rda konutu bulunan "
            "+ sigortas\u0131z"
        ),
    )

    for expected in expected_values:

        assert expected in text


def test_emlak_new_housing_is_condition_scoped():

    text = _response().text

    assert (
        "T\u00fcrkiye Emlak Kat\u0131l\u0131m - "
        "Konut Finansman\u0131"
        in text
    )

    assert (
        "yaln\u0131zca "
        "**yeni/s\u0131f\u0131r konut** "
        "ko\u015fulu i\u00e7indir"
        in text
    )

    assert (
        "ikinci el konuta otomatik "
        "olarak genellenmez"
        in text
    )


def test_emlak_condition_numbers_are_not_generic():

    text = _response().text

    marker = (
        "### Ko\u015fula g\u00f6re "
        "do\u011frulanm\u0131\u015f konut "
        "se\u00e7enekleri"
    )

    generic_text = text.split(
        marker,
        1,
    )[0]

    assert (
        "174.627,95 TL"
        not in generic_text
    )


def test_albaraka_historical_values_stay_blocked():

    text = _response().text

    # The historical and current official Albaraka results can share the same rate.
    # Stale leakage is therefore guarded by the old installment and repayment figures.

    assert (
        "4.616,82 TL"
        not in text
    )

    assert (
        "166.205,69 TL"
        not in text
    )


def test_raw_variant_names_do_not_leak():

    text = _response().text.casefold()

    for raw_name in (
        "2el_konut",
        "sifir_konut",
        "yeni_konut",
        "ilk_konut_sigortali",
        "ilk_konut_sigortasiz",
        "mevcut_konut_sigortali",
        "mevcut_konut_sigortasiz",
    ):

        assert raw_name not in text
