from dataclasses import dataclass

import src.chatbot_finance_renderer as renderer


@dataclass(
    frozen=True,
)
class FakeRendered:

    text: str

    numeric_product_ids: tuple

    unresolved_product_ids: tuple


CONDITION = (
    "### Ko\u015fula g\u00f6re "
    "do\u011frulanm\u0131\u015f konut se\u00e7enekleri"
)

OLD_HEADING = (
    "### Hen\u00fcz "
    "do\u011frulanmam\u0131\u015f adaylar"
)

NEW_HEADING = (
    "### Genel s\u0131ralamaya dahil edilmeyen "
    "ko\u015fula \u00f6zel adaylar"
)

OLD_NOTE = (
    "- A\u015fa\u011f\u0131daki adaylar hen\u00fcz "
    "do\u011frulanmad\u0131\u011f\u0131 i\u00e7in bu sonu\u00e7 "
    "t\u00fcm bankalar i\u00e7in kesin birincilik "
    "anlam\u0131na gelmez."
)

NEW_NOTE = (
    "- A\u015fa\u011f\u0131daki adaylar i\u00e7in bu tutar "
    "ve vadede ko\u015fula \u00f6zel sonu\u00e7lar "
    "do\u011frulanm\u0131\u015ft\u0131r; ancak ko\u015ful "
    "belirtilmeden genel s\u0131ralamaya uygun tekil bir "
    "sonu\u00e7 bulunmad\u0131\u011f\u0131ndan bu adaylar "
    "genel s\u0131ralamaya dahil edilmemi\u015ftir."
)


def _base_text():

    return "\n".join(
        (
            CONDITION,
            "",
            "### Kapsam notu",
            OLD_NOTE,
            "",
            OLD_HEADING,
            "- T\u00fcrkiye Finans",
            "- T\u00fcrkiye Emlak Kat\u0131l\u0131m",
        )
    )


def test_condition_only_unresolved_is_relabelled(
    monkeypatch,
):

    base = FakeRendered(
        text=_base_text(),
        numeric_product_ids=(
            67,
            242,
        ),
        unresolved_product_ids=(
            67,
            242,
        ),
    )


    monkeypatch.setattr(
        renderer,
        "_render_finance_answer_before_condition_scope_wording_v2",
        lambda context: base,
    )


    result = (
        renderer.render_finance_answer(
            object()
        )
    )


    assert NEW_HEADING in result.text

    assert NEW_NOTE in result.text

    assert OLD_HEADING not in result.text

    assert OLD_NOTE not in result.text


def test_real_unverified_candidate_keeps_old_wording(
    monkeypatch,
):

    base = FakeRendered(
        text=_base_text(),
        numeric_product_ids=(
            67,
            242,
        ),
        unresolved_product_ids=(
            67,
            242,
            999,
        ),
    )


    monkeypatch.setattr(
        renderer,
        "_render_finance_answer_before_condition_scope_wording_v2",
        lambda context: base,
    )


    result = (
        renderer.render_finance_answer(
            object()
        )
    )


    assert OLD_HEADING in result.text

    assert OLD_NOTE in result.text

    assert NEW_HEADING not in result.text

    assert NEW_NOTE not in result.text


def test_non_housing_answer_is_unchanged(
    monkeypatch,
):

    text = "\n".join(
        (
            "### Kapsam notu",
            OLD_NOTE,
            "",
            OLD_HEADING,
            "- Banka X",
        )
    )


    base = FakeRendered(
        text=text,
        numeric_product_ids=(
            999,
        ),
        unresolved_product_ids=(
            999,
        ),
    )


    monkeypatch.setattr(
        renderer,
        "_render_finance_answer_before_condition_scope_wording_v2",
        lambda context: base,
    )


    result = (
        renderer.render_finance_answer(
            object()
        )
    )


    assert result.text == text
