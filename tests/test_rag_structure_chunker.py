from src.rag_document_model import (
    GROUNDING_LIVE_ONLY,
    SOURCE_KIND_CAMPAIGN,
    SOURCE_KIND_PRODUCT,
    build_rag_document,
)

from src.rag_structure_chunker import (
    prepare_retrieval_text,
    sectionize_document,
)


def product_document(text):
    return build_rag_document(
        source_kind=SOURCE_KIND_PRODUCT,
        source_id=116,
        bank_name="Albaraka T\u00fcrk",
        title="E\u011fitim Finansman\u0131",
        text=text,
        source_url="https://example.com/product",
        checked_at="2026-08-21T12:00:00+03:00",
        metadata={
            "family":
                "ihtiyac_finansmani"
        },
    )


def campaign_document(text):
    return build_rag_document(
        source_kind=SOURCE_KIND_CAMPAIGN,
        source_id=555,
        bank_name=(
            "T\u00fcrkiye Emlak Kat\u0131l\u0131m"
        ),
        title=(
            "U\u00e7ak Bileti "
            "Kampanyas\u0131"
        ),
        text=text,
        source_url="https://example.com/campaign",
        checked_at="2026-08-21T12:00:00+03:00",
        metadata={
            "campaign_type":
                "points_campaign"
        },
    )


def test_product_sections_are_preserved():
    doc = product_document(
        "E\u011fitim Finansman\u0131 "
        "ile masraflar\u0131n\u0131z\u0131 "
        "kar\u015f\u0131layabilirsiniz. "
        "E\u011fitim Finansman\u0131 Nedir? "
        "Bu finansman e\u011fitim "
        "giderleri i\u00e7indir. "
        "E\u011fitim Finansman\u0131n\u0131n "
        "Avantajlar\u0131 Nelerdir? "
        "12 aya kadar vade bulunabilir. "
        "E\u011fitim Finansman\u0131na "
        "Nas\u0131l Ba\u015fvurulur? "
        "\u015eubeden ba\u015fvurabilirsiniz. "
        "Ba\u015fvuru \u0130\u00e7in "
        "Gerekli Belgeler Nelerdir? "
        "Gelir belgesi gerekir."
    )

    chunks = sectionize_document(
        doc
    )

    types = [
        chunk.section_type
        for chunk in chunks
    ]

    assert "overview" in types
    assert "definition" in types
    assert "benefits" in types
    assert "application" in types
    assert "required_documents" in types


def test_campaign_sections_are_preserved():
    doc = campaign_document(
        "2.000 TL ParafPara avantaj\u0131. "
        "Kampanyaya Nas\u0131l Kat\u0131l\u0131r\u0131m? "
        "BILET yaz\u0131p SMS g\u00f6nderilir. "
        "Kampanya Ko\u015fullar\u0131 "
        "Kampanya 1-31 A\u011fustos 2026 "
        "tarihleri aras\u0131nda ge\u00e7erlidir."
    )

    chunks = sectionize_document(
        doc
    )

    types = [
        chunk.section_type
        for chunk in chunks
    ]

    assert "campaign_participation" in types
    assert "campaign_terms" in types


def test_dynamic_calculator_is_live_only():
    doc = product_document(
        "Konut finansman\u0131 a\u00e7\u0131klamas\u0131. "
        "Finansal Hesaplama "
        "Finansman ihtiyac\u0131n\u0131z TL 1.000 "
        "Vade 36 "
        "Ayl\u0131k Taksit Tutar\u0131 0 TL "
        "Ayl\u0131k K\u00e2r Oran\u0131 %0 "
        "T\u00fcm site ziyaret\u00e7ilerimizi "
        "daha iyi tan\u0131mak i\u00e7in "
        "web sitemizde \u00e7erezler kullan\u0131yoruz."
    )

    chunks = sectionize_document(
        doc
    )

    calculator = [
        chunk
        for chunk in chunks
        if chunk.section_type
        == "dynamic_calculator"
    ]

    assert calculator
    assert (
        calculator[0].grounding_policy
        == GROUNDING_LIVE_ONLY
    )

    combined = " ".join(
        chunk.text
        for chunk in chunks
    )

    assert (
        "\u00e7erezler kullan\u0131yoruz"
        not in combined
    )


def test_long_section_is_flagged_not_blindly_split():
    long_terms = (
        "Kampanya Ko\u015fullar\u0131 "
        + (
            "Bu kampanya i\u00e7in "
            "resmi ko\u015ful metni vard\u0131r. "
            * 150
        )
    )

    doc = campaign_document(
        long_terms
    )

    chunks = sectionize_document(
        doc,
        semantic_split_threshold=500,
    )

    terms = [
        chunk
        for chunk in chunks
        if chunk.section_type
        == "campaign_terms"
    ]

    assert len(terms) == 1
    assert terms[0].requires_semantic_split


def test_document_id_is_stable():
    first = product_document(
        "Ayn\u0131 kaynak metni."
    )

    second = product_document(
        "Ayn\u0131 kaynak metni."
    )

    assert first.doc_id == second.doc_id
    assert first.source_hash == second.source_hash


def test_audio_noise_is_removed():
    prepared = prepare_retrieval_text(
        "Kampanya metni. "
        "\u00d7 Your browser does not support "
        "the audio element."
    )

    assert (
        "does not support"
        not in prepared.text
    )
