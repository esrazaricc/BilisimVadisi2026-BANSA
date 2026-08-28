from src.chatbot_finance_renderer import (
    _beautify_finance_text_v1,
)

from src.chatbot_response_service import (
    ask_bansa,
)


def test_finance_visual_formatter_builds_markdown_table():

    text = (
        "Ayn\u0131 tutar ve vade i\u00e7in "
        "birebir do\u011frulanm\u0131\u015f sonu\u00e7lar:\n\n"

        "- Albaraka T\u00fcrk - Konut Finansman\u0131\n"
        "  K\u00e2r pay\u0131 oran\u0131: %3,04\n"
        "  Ayl\u0131k taksit: 4.616,82 TL\n"
        "  Geri \u00f6denecek toplam: 166.205,69 TL\n"
        "  Tahsis \u00fccreti: 500,00 TL\n"
        "  Kaynak: https://example.com\n"
        "  Kontrol tarihi: "
        "2026-08-20T02:37:03.400880+03:00\n\n"

        "Genel de\u011ferlendirme:\n"
        "- Test sonucu."
    )

    rendered = (
        _beautify_finance_text_v1(
            text
        )
    )

    assert (
        "### Ayn\u0131 tutar ve vade i\u00e7in "
        "birebir do\u011frulanm\u0131\u015f sonu\u00e7lar"
        in rendered
    )

    assert (
        "#### Albaraka T\u00fcrk - Konut Finansman\u0131"
        in rendered
    )

    assert (
        "| Kriter | De\u011fer |"
        in rendered
    )

    assert (
        "| K\u00e2r pay\u0131 oran\u0131 | %3,04 |"
        in rendered
    )

    assert (
        "| Ayl\u0131k taksit | 4.616,82 TL |"
        in rendered
    )

    assert (
        "Kaynak: https://example.com"
        in rendered
    )

    assert (
        "Kontrol tarihi: 20 A\u011fustos 2026"
        in rendered
    )

    assert (
        "2026-08-20T02:37"
        not in rendered
    )


def test_non_verified_result_text_is_not_rewritten():

    text = (
        "Bu senaryo i\u00e7in do\u011frulanm\u0131\u015f "
        "ve birebir e\u015fle\u015fen hesaplama sonucu "
        "bulunmad\u0131."
    )

    assert (
        _beautify_finance_text_v1(
            text
        )
        == text
    )


def test_real_finance_e2e_keeps_deterministic_backend():

    response = ask_bansa(
        (
            "100.000 TL 36 ay konut "
            "finansmanlarini karsilastir"
        )
    )

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

    assert (
        response.finance_renderer_used
        is True
    )

    assert (
        "| Kriter | De\u011fer |"
        in response.text
    )

    assert (
        "K\u00e2r pay\u0131 oran\u0131"
        in response.text
    )

    assert (
        "Ayl\u0131k taksit"
        in response.text
    )

    assert (
        "Geri \u00f6denecek toplam"
        in response.text
    )


def test_real_finance_timestamp_is_human_readable():

    response = ask_bansa(
        (
            "100.000 TL 36 ay konut "
            "finansmanlarini karsilastir"
        )
    )

    assert (
        "Kontrol tarihi:"
        in response.text
    )

    # User-facing timestamps should no longer expose
    # ISO T + timezone syntax.
    control_lines = [
        line
        for line
        in response.text.splitlines()
        if line.startswith(
            "Kontrol tarihi:"
        )
    ]

    assert control_lines

    for line in control_lines:

        assert "T" not in line

        assert (
            "+03:00"
            not in line
        )

        assert (
            "+00:00"
            not in line
        )
