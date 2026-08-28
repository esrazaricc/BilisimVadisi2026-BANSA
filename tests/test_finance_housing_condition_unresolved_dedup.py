from src.chatbot_finance_renderer import (
    _hc_remove_condition_verified_unresolved_v13,
)


def _rows():
    return [
        {
            "product_id": 242,
            "bank_name":
                "T\u00fcrkiye Emlak Kat\u0131l\u0131m",
            "product_name":
                "Konut Finansman\u0131",
        }
    ]


def test_condition_verified_product_removed_from_unresolved():

    text = (
        "### Ko\u015fula g\u00f6re "
        "do\u011frulanm\u0131\u015f konut se\u00e7enekleri\n\n"
        "#### T\u00fcrkiye Emlak Kat\u0131l\u0131m "
        "- Konut Finansman\u0131\n\n"
        "### Hen\u00fcz do\u011frulanmam\u0131\u015f adaylar\n"
        "- Kuveyt T\u00fcrk - Konut Finansman\u0131\n"
        "- T\u00fcrkiye Emlak Kat\u0131l\u0131m "
        "- Konut Finansman\u0131\n"
        "- Vak\u0131f Kat\u0131l\u0131m "
        "- Konut Finansman\u0131"
    )

    actual = (
        _hc_remove_condition_verified_unresolved_v13(
            text,
            _rows(),
        )
    )

    assert (
        "#### T\u00fcrkiye Emlak Kat\u0131l\u0131m "
        "- Konut Finansman\u0131"
        in actual
    )

    assert (
        "- T\u00fcrkiye Emlak Kat\u0131l\u0131m "
        "- Konut Finansman\u0131"
        not in actual
    )

    assert (
        "- Kuveyt T\u00fcrk - Konut Finansman\u0131"
        in actual
    )

    assert (
        "- Vak\u0131f Kat\u0131l\u0131m "
        "- Konut Finansman\u0131"
        in actual
    )


def test_same_label_outside_unresolved_is_preserved():

    text = (
        "#### T\u00fcrkiye Emlak Kat\u0131l\u0131m "
        "- Konut Finansman\u0131\n"
        "Ko\u015fula \u00f6zel do\u011frulanm\u0131\u015f sonu\u00e7.\n\n"
        "### Hen\u00fcz do\u011frulanmam\u0131\u015f adaylar\n"
        "- T\u00fcrkiye Emlak Kat\u0131l\u0131m "
        "- Konut Finansman\u0131"
    )

    actual = (
        _hc_remove_condition_verified_unresolved_v13(
            text,
            _rows(),
        )
    )

    assert (
        "#### T\u00fcrkiye Emlak Kat\u0131l\u0131m "
        "- Konut Finansman\u0131"
        in actual
    )

    assert (
        "- T\u00fcrkiye Emlak Kat\u0131l\u0131m "
        "- Konut Finansman\u0131"
        not in actual
    )


def test_other_unresolved_products_are_not_removed():

    text = (
        "### Hen\u00fcz do\u011frulanmam\u0131\u015f adaylar\n"
        "- T\u00fcrkiye Finans - Konut Finansman\u0131\n"
        "- T\u00fcrkiye Emlak Kat\u0131l\u0131m "
        "- Konut Finansman\u0131\n"
        "- Ziraat Kat\u0131l\u0131m "
        "- Konut Finansman\u0131"
    )

    actual = (
        _hc_remove_condition_verified_unresolved_v13(
            text,
            _rows(),
        )
    )

    assert (
        "- T\u00fcrkiye Finans - Konut Finansman\u0131"
        in actual
    )

    assert (
        "- Ziraat Kat\u0131l\u0131m "
        "- Konut Finansman\u0131"
        in actual
    )
