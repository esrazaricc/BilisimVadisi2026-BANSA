from dataclasses import dataclass

import pytest

from src.chatbot_rag_extractive_renderer import (
    render_extractive_rag_answer,
)


@dataclass(frozen=True)
class Evidence:

    evidence_id: str
    source_kind: str
    bank_name: str
    document_title: str
    section_type: str
    text: str
    source_url: str
    checked_at: str | None


@dataclass(frozen=True)
class Context:

    question: str
    route: str
    evidence: tuple


def test_product_answer_is_extractive():

    context = Context(
        question=(
            "Egitim finansmaninin "
            "avantajlari nelerdir?"
        ),
        route="product_rag",
        evidence=(
            Evidence(
                evidence_id="E1",
                source_kind=(
                    "standard_product"
                ),
                bank_name=(
                    "Albaraka Turk"
                ),
                document_title=(
                    "Egitim Finansmani"
                ),
                section_type="benefits",
                text=(
                    "Egitim masraflarinizi "
                    "12 aya kadar "
                    "taksitlendirebilirsiniz. "
                    "Ogrenci gelir belgesi "
                    "bulunmuyorsa veli "
                    "basvurabilir."
                ),
                source_url=(
                    "https://example.com"
                ),
                checked_at="2026-08-21",
            ),
        ),
    )


    rendered = (
        render_extractive_rag_answer(
            context
        )
    )


    assert (
        "12 aya kadar"
        in rendered.text
    )

    assert (
        "[E1]"
        in rendered.text
    )

    assert (
        rendered.source_kind
        == "standard_product"
    )


def test_campaign_keeps_official_numeric_fact():

    context = Context(
        question=(
            "Ucak bileti kampanyasi "
            "var mi?"
        ),
        route="campaign_rag",
        evidence=(
            Evidence(
                evidence_id="E1",
                source_kind="campaign",
                bank_name="Bank",
                document_title=(
                    "Ucak Bileti Kampanyasi"
                ),
                section_type=(
                    "campaign_terms"
                ),
                text=(
                    "Kampanya 1-31 Agustos "
                    "2026 tarihleri arasinda "
                    "gecerlidir. "
                    "5.000 TL harcamaya "
                    "400 TL odul verilir."
                ),
                source_url=(
                    "https://example.com"
                ),
                checked_at="2026-08-21",
            ),
        ),
    )


    rendered = (
        render_extractive_rag_answer(
            context
        )
    )


    assert "1-31" in rendered.text
    assert "2026" in rendered.text
    assert "5.000 TL" in rendered.text
    assert "400 TL" in rendered.text


def test_renderer_does_not_create_finance_advice():

    context = Context(
        question="hangi banka",
        route="finance_compare",
        evidence=(
            Evidence(
                "E1",
                "campaign",
                "Bank",
                "Campaign",
                "overview",
                "Campaign text.",
                "https://example.com",
                None,
            ),
        ),
    )


    with pytest.raises(
        ValueError
    ):

        render_extractive_rag_answer(
            context
        )


def test_multidocument_uses_at_most_one_sentence_per_doc_first():

    context = Context(
        question=(
            "hangi kampanyalar var?"
        ),
        route="hybrid",
        evidence=(
            Evidence(
                "E1",
                "campaign",
                "Bank",
                "Campaign A",
                "campaign_terms",
                (
                    "Campaign A kosulu. "
                    "Campaign A ikinci bilgi."
                ),
                "https://a.example",
                None,
            ),
            Evidence(
                "E2",
                "campaign",
                "Bank",
                "Campaign B",
                "campaign_terms",
                (
                    "Campaign B kosulu. "
                    "Campaign B ikinci bilgi."
                ),
                "https://b.example",
                None,
            ),
        ),
    )


    rendered = (
        render_extractive_rag_answer(
            context,
            max_sentences=2,
        )
    )


    assert (
        rendered.document_count
        == 2
    )

    assert (
        rendered.sentence_count
        == 2
    )



# EXTRACTIVE_RAG_RENDERER_V1_1_TESTS


def test_heading_noise_is_not_rendered():

    context = Context(
        question=(
            "Egitim finansmaninin "
            "avantajlari nelerdir?"
        ),
        route="product_rag",
        evidence=(
            Evidence(
                "E1",
                "standard_product",
                "Bank",
                "Egitim Finansmani",
                "benefits",
                (
                    "Avantajlari Nelerdir? "
                    "Egitim masraflarinizi "
                    "12 aya kadar "
                    "taksitlendirebilirsiniz."
                ),
                "https://example.com",
                None,
            ),
        ),
    )


    rendered = (
        render_extractive_rag_answer(
            context
        )
    )


    assert (
        "Avantajlari Nelerdir?"
        not in rendered.text
    )


def test_navigation_noise_is_removed():

    context = Context(
        question="Egitim finansmani nedir?",
        route="product_rag",
        evidence=(
            Evidence(
                "E1",
                "standard_product",
                "Bank",
                "Egitim Finansmani",
                "overview",
                (
                    "Anasayfa Bireysel Finansmanlar "
                    "Ihtiyac Finansmani Egitim Finansmani "
                    "Jet Finansman Motosiklet Finansmani "
                    "Konut Finansmani. "
                    "Egitim giderleri icin "
                    "finansman sunulur."
                ),
                "https://example.com",
                None,
            ),
        ),
    )


    rendered = (
        render_extractive_rag_answer(
            context
        )
    )


    assert (
        "Anasayfa"
        not in rendered.text
    )


def test_restricted_campaign_is_blocked_for_generic_user():

    context = Context(
        question=(
            "Ihtiyac finansmani icin "
            "kampanya var mi?"
        ),
        route="hybrid",
        evidence=(
            Evidence(
                "E1",
                "campaign",
                "Bank",
                (
                    "Kamu Calisanlarina Ozel "
                    "Ihtiyac Finansmani"
                ),
                "campaign_terms",
                (
                    "Kamu calisanlarina ozel "
                    "avantajli kosullar sunulur."
                ),
                "https://example.com",
                None,
            ),
        ),
    )


    rendered = (
        render_extractive_rag_answer(
            context
        )
    )


    assert (
        rendered.sentence_count
        == 0
    )

    assert (
        "uygunlugu dogrulanmis"
        in (
            rendered.text
            .encode(
                "ascii",
                errors="ignore"
            )
            .decode(
                "ascii"
            )
            .casefold()
            .replace(
                "\u011f",
                "g"
            )
        )
        or rendered.reasons == (
            "no_eligible_extractive_evidence",
            "fail_closed",
        )
    )


def test_restricted_campaign_allowed_when_user_matches():

    context = Context(
        question=(
            "Kamu calisaniyim, "
            "ihtiyac finansmani kampanyasi var mi?"
        ),
        route="hybrid",
        evidence=(
            Evidence(
                "E1",
                "campaign",
                "Bank",
                (
                    "Kamu Calisanlarina Ozel "
                    "Ihtiyac Finansmani"
                ),
                "campaign_terms",
                (
                    "Kamu calisanlarina ozel "
                    "avantajli kosullar sunulur."
                ),
                "https://example.com",
                None,
            ),
        ),
    )


    rendered = (
        render_extractive_rag_answer(
            context
        )
    )


    assert (
        rendered.sentence_count
        == 1
    )


def test_bank_change_right_is_lower_priority_than_campaign_fact():

    context = Context(
        question="Ucak bileti kampanyasi var mi?",
        route="campaign_rag",
        evidence=(
            Evidence(
                "E1",
                "campaign",
                "Bank",
                "Ucak Bileti Kampanyasi",
                "campaign_terms",
                (
                    "Banka kampanyayi diledigi zaman "
                    "durdurma ve kosullari degistirme "
                    "hakkina sahiptir. "
                    "5.000 TL harcamaya "
                    "400 TL odul verilir."
                ),
                "https://example.com",
                None,
            ),
        ),
    )


    rendered = (
        render_extractive_rag_answer(
            context,
            max_sentences=1,
        )
    )


    assert (
        "400 TL"
        in rendered.text
    )



# EXTRACTIVE_RAG_RENDERER_V1_2_TESTS


def test_turkish_dotless_i_normalization():

    from src.chatbot_rag_extractive_renderer import (
        _normalize,
    )


    assert (
        _normalize(
            "Banka \u00c7al\u0131\u015fanlar\u0131na "
            "\u00d6zel \u0130htiya\u00e7 Finansman\u0131"
        )
        ==
        (
            "banka calisanlarina "
            "ozel ihtiyac finansmani"
        )
    )


    assert (
        _normalize(
            "Kamu \u00c7al\u0131\u015fanlar\u0131na "
            "\u00d6zel"
        )
        ==
        "kamu calisanlarina ozel"
    )


def test_real_turkish_bank_employee_title_is_restricted():

    from src.chatbot_rag_extractive_renderer import (
        _segment_restriction,
        _segment_allowed,
    )


    title = (
        "Banka \u00c7al\u0131\u015fanlar\u0131na "
        "\u00d6zel \u0130htiya\u00e7 Finansman\u0131"
    )


    restriction = (
        _segment_restriction(
            title,
            "",
        )
    )


    assert (
        restriction
        == "banka_calisani"
    )


    assert (
        _segment_allowed(
            question=(
                "Genel ihtiya\u00e7 "
                "finansman\u0131 kampanyas\u0131 "
                "var m\u0131?"
            ),
            title=title,
            sentence=(
                "Banka \u00e7al\u0131\u015fanlar\u0131 "
                "i\u00e7in \u00f6zel kampanyad\u0131r."
            ),
        )
        is False
    )


def test_real_turkish_public_employee_title_is_restricted():

    from src.chatbot_rag_extractive_renderer import (
        _segment_restriction,
        _segment_allowed,
    )


    title = (
        "Kamu \u00c7al\u0131\u015fanlar\u0131na "
        "\u00d6zel \u0130htiya\u00e7 Finansman\u0131"
    )


    assert (
        _segment_restriction(
            title,
            "",
        )
        == "kamu_calisani"
    )


    assert (
        _segment_allowed(
            question=(
                "Genel ihtiya\u00e7 "
                "finansman\u0131 kampanyas\u0131 "
                "var m\u0131?"
            ),
            title=title,
            sentence=(
                "Kamu \u00e7al\u0131\u015fanlar\u0131 "
                "yararlanabilir."
            ),
        )
        is False
    )


def test_public_employee_campaign_allowed_when_declared():

    from src.chatbot_rag_extractive_renderer import (
        _segment_allowed,
    )


    assert (
        _segment_allowed(
            question=(
                "Kamu \u00e7al\u0131\u015fan\u0131y\u0131m, "
                "ihtiya\u00e7 finansman\u0131 "
                "kampanyas\u0131 var m\u0131?"
            ),
            title=(
                "Kamu \u00c7al\u0131\u015fanlar\u0131na "
                "\u00d6zel \u0130htiya\u00e7 Finansman\u0131"
            ),
            sentence=(
                "Kamu \u00e7al\u0131\u015fanlar\u0131 "
                "yararlanabilir."
            ),
        )
        is True
    )


def test_dangling_education_fragment_is_noise():

    from src.chatbot_rag_extractive_renderer import (
        _is_heading_noise,
    )


    assert (
        _is_heading_noise(
            "E\u011fitim Finansman\u0131na"
        )
        is True
    )


    assert (
        _is_heading_noise(
            "E\u011fitim Finansman\u0131"
        )
        is True
    )


def test_legitimate_short_sentence_is_preserved():

    from src.chatbot_rag_extractive_renderer import (
        _is_heading_noise,
    )


    assert (
        _is_heading_noise(
            "Kefil \u015fart\u0131 yok!"
        )
        is False
    )

